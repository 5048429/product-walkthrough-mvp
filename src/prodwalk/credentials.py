from __future__ import annotations

import argparse
import base64
import ctypes
import ctypes.wintypes
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .models import slugify, utc_now


class CredentialStoreError(RuntimeError):
    pass


@dataclass(slots=True)
class StoredCredential:
    ref: str
    site: str
    host: str
    username: str
    password: str
    notes: str = ""

    @property
    def placeholders(self) -> dict[str, str]:
        normalized = normalize_ref(self.ref)
        return {
            "username": f"{normalized}_username",
            "password": f"{normalized}_password",
        }

    @property
    def sensitive_values(self) -> dict[str, str]:
        placeholders = self.placeholders
        return {
            placeholders["username"]: self.username,
            placeholders["password"]: self.password,
        }

    @property
    def domains(self) -> list[str]:
        domains = [self.host]
        parts = self.host.split(".")
        if len(parts) >= 2:
            parent_domain = ".".join(parts[-2:])
            wildcard = f"*.{parent_domain}"
            if wildcard not in domains:
                domains.append(wildcard)
        return domains


def normalize_ref(ref: str) -> str:
    return slugify(ref).replace("-", "_")


def default_credential_store_path() -> Path:
    configured = os.getenv("PRODWALK_CREDENTIAL_STORE")
    if configured:
        return Path(configured)
    return Path(".prodwalk") / "credentials.json"


class CredentialStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else default_credential_store_path()

    def set(
        self,
        ref: str,
        site: str,
        username: str,
        password: str,
        notes: str = "",
    ) -> None:
        ref = ref.strip()
        site = site.strip()
        username = username.strip()
        if not ref:
            raise CredentialStoreError("Credential ref is required.")
        if not site:
            raise CredentialStoreError("Credential site is required.")
        if not username:
            raise CredentialStoreError("Credential username is required.")
        if not password:
            raise CredentialStoreError("Credential password is required.")

        payload = self._load()
        credentials = payload.setdefault("credentials", {})
        existing = credentials.get(ref, {})
        now = utc_now()
        credentials[ref] = {
            "ref": ref,
            "site": site,
            "host": host_from_site(site),
            "username": protect_text(username),
            "password": protect_text(password),
            "notes": notes,
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "encryption": "windows-dpapi",
        }
        self._save(payload)

    def get(self, ref: str) -> StoredCredential | None:
        record = self._load().get("credentials", {}).get(ref)
        if not isinstance(record, dict):
            return None
        return StoredCredential(
            ref=str(record.get("ref") or ref),
            site=str(record.get("site") or ""),
            host=str(record.get("host") or host_from_site(str(record.get("site") or ""))),
            username=unprotect_text(str(record.get("username") or "")),
            password=unprotect_text(str(record.get("password") or "")),
            notes=str(record.get("notes") or ""),
        )

    def delete(self, ref: str) -> bool:
        payload = self._load()
        credentials = payload.setdefault("credentials", {})
        if ref not in credentials:
            return False
        del credentials[ref]
        self._save(payload)
        return True

    def list(self) -> list[dict[str, Any]]:
        credentials = self._load().get("credentials", {})
        if not isinstance(credentials, dict):
            return []
        rows: list[dict[str, Any]] = []
        for ref, record in sorted(credentials.items()):
            if not isinstance(record, dict):
                continue
            rows.append(
                {
                    "ref": ref,
                    "site": record.get("site", ""),
                    "host": record.get("host", ""),
                    "notes": record.get("notes", ""),
                    "created_at": record.get("created_at", ""),
                    "updated_at": record.get("updated_at", ""),
                    "has_username": bool(record.get("username")),
                    "has_password": bool(record.get("password")),
                }
            )
        return rows

    def sensitive_data_for_ref(self, ref: str) -> dict[str, dict[str, str]]:
        credential = self.get(ref)
        if credential is None:
            return {}
        values = credential.sensitive_values
        return {domain: dict(values) for domain in credential.domains}

    def placeholders_for_ref(self, ref: str) -> dict[str, str] | None:
        if self.get(ref) is None:
            return None
        normalized = normalize_ref(ref)
        return {
            "username": f"{normalized}_username",
            "password": f"{normalized}_password",
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "credentials": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CredentialStoreError(f"Credential store is not valid JSON: {self.path}") from exc
        if not isinstance(payload, dict):
            raise CredentialStoreError(f"Credential store must be a JSON object: {self.path}")
        payload.setdefault("version", 1)
        payload.setdefault("credentials", {})
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def host_from_site(site: str) -> str:
    parsed = urlparse(site if "://" in site else f"https://{site}")
    host = parsed.netloc or parsed.path
    return host.strip("/")


def protect_text(value: str) -> str:
    data = value.encode("utf-8")
    protected = _dpapi_protect(data)
    return base64.b64encode(protected).decode("ascii")


def unprotect_text(value: str) -> str:
    if not value:
        return ""
    data = base64.b64decode(value.encode("ascii"))
    return _dpapi_unprotect(data).decode("utf-8")


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("Local credential encryption currently requires Windows DPAPI.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in, buffer = _blob_from_bytes(data)
    blob_out = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    _ = buffer
    if not ok:
        raise CredentialStoreError("Windows DPAPI failed to encrypt credential data.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise CredentialStoreError("Local credential decryption currently requires Windows DPAPI.")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_in, buffer = _blob_from_bytes(data)
    blob_out = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(blob_out),
    )
    _ = buffer
    if not ok:
        raise CredentialStoreError("Windows DPAPI failed to decrypt credential data.")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def add_credential_subcommands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("credentials", help="Manage local encrypted credentials")
    parser.add_argument("--store", default=None, help="Credential store path. Defaults to .prodwalk/credentials.json")
    credential_subparsers = parser.add_subparsers(dest="credentials_command", required=True)

    set_parser = credential_subparsers.add_parser("set", help="Store or update a credential")
    set_parser.add_argument("--ref", required=True, help="Credential reference used by research plans")
    set_parser.add_argument("--site", required=True, help="Website or base URL this credential is scoped to")
    set_parser.add_argument("--username", required=True, help="Login username or email")
    set_parser.add_argument("--password", default=None, help="Password. Omit to enter it securely.")
    set_parser.add_argument("--notes", default="", help="Optional notes")

    credential_subparsers.add_parser("list", help="List stored credential refs without revealing secrets")

    delete_parser = credential_subparsers.add_parser("delete", help="Delete a stored credential")
    delete_parser.add_argument("--ref", required=True, help="Credential reference to delete")


def handle_credential_command(args: argparse.Namespace) -> None:
    import getpass

    store = CredentialStore(path=args.store)
    if args.credentials_command == "set":
        password = args.password
        if password is None:
            password = getpass.getpass("Password: ")
        store.set(
            ref=args.ref,
            site=args.site,
            username=args.username,
            password=password,
            notes=args.notes,
        )
        print(f"Stored credential ref: {args.ref}")
        print(f"Store: {store.path}")
        return

    if args.credentials_command == "list":
        rows = store.list()
        if not rows:
            print("No credentials stored.")
            return
        for row in rows:
            print(f"{row['ref']}\t{row['site']}\tupdated={row['updated_at']}")
        return

    if args.credentials_command == "delete":
        deleted = store.delete(args.ref)
        print(f"Deleted credential ref: {args.ref}" if deleted else f"Credential ref not found: {args.ref}")
        return

    raise CredentialStoreError(f"Unsupported credentials command: {args.credentials_command}")
