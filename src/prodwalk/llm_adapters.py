from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, AsyncIterable, TypeVar, overload

import httpx
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from browser_use.llm.exceptions import ModelProviderError, ModelRateLimitError
from browser_use.llm.messages import BaseMessage, SystemMessage
from browser_use.llm.openai.responses_serializer import ResponsesAPIMessageSerializer
from browser_use.llm.schema import SchemaOptimizer
from browser_use.llm.views import ChatInvokeCompletion, ChatInvokeUsage


T = TypeVar("T", bound=BaseModel)


@dataclass
class OpenAIResponsesChatModel:
    """browser-use BaseChatModel adapter backed by the OpenAI Responses API."""

    model: str
    api_key: str
    base_url: str | httpx.URL | None = None
    organization: str | None = None
    project: str | None = None
    timeout: float | httpx.Timeout | None = None
    max_retries: int = 5
    default_headers: Mapping[str, str] | None = None
    default_query: Mapping[str, object] | None = None
    http_client: httpx.AsyncClient | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None

    @property
    def provider(self) -> str:
        return "openai-responses"

    @property
    def name(self) -> str:
        return self.model

    @property
    def model_name(self) -> str:
        return self.model

    def get_client(self) -> AsyncOpenAI:
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "organization": self.organization,
            "project": self.project,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "default_headers": self.default_headers,
            "default_query": self.default_query,
            "http_client": self.http_client,
        }
        return AsyncOpenAI(**{key: value for key, value in params.items() if value is not None})

    @overload
    async def ainvoke(
        self,
        messages: list[BaseMessage],
        output_format: None = None,
        **kwargs: Any,
    ) -> ChatInvokeCompletion[str]: ...

    @overload
    async def ainvoke(
        self,
        messages: list[BaseMessage],
        output_format: type[T],
        **kwargs: Any,
    ) -> ChatInvokeCompletion[T]: ...

    async def ainvoke(
        self,
        messages: list[BaseMessage],
        output_format: type[T] | None = None,
        **kwargs: Any,
    ) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
        instructions, input_messages = self._split_instructions(messages)
        response_input = ResponsesAPIMessageSerializer.serialize_messages(input_messages)
        model_params = self._model_params(output_format)

        try:
            stream = await self.get_client().responses.create(
                model=self.model,
                input=response_input,
                instructions=instructions,
                store=False,
                stream=True,
                **model_params,
            )
            output_text, usage, stop_reason = await self._collect_stream(stream)

            if output_format is None:
                return ChatInvokeCompletion(completion=output_text, usage=usage, stop_reason=stop_reason)

            if not output_text:
                raise ModelProviderError(
                    message="Invalid OpenAI Responses response: missing output_text.",
                    status_code=502,
                    model=self.name,
                )
            try:
                parsed = output_format.model_validate_json(output_text)
            except ValidationError:
                parsed = output_format.model_validate_json(self._first_json_object(output_text))
            return ChatInvokeCompletion(completion=parsed, usage=usage, stop_reason=stop_reason)
        except ModelProviderError:
            raise
        except RateLimitError as exc:
            raise ModelRateLimitError(message=exc.message, model=self.name) from exc
        except APIConnectionError as exc:
            raise ModelProviderError(message=str(exc), model=self.name) from exc
        except APIStatusError as exc:
            raise ModelProviderError(message=exc.message, status_code=exc.status_code, model=self.name) from exc
        except Exception as exc:
            raise ModelProviderError(message=str(exc), model=self.name) from exc

    async def _collect_stream(
        self,
        stream: AsyncIterable[Any],
    ) -> tuple[str, ChatInvokeUsage | None, str | None]:
        output_parts: list[str] = []
        final_response: Any = None
        async for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                output_parts.append(str(getattr(event, "delta", "") or ""))
            elif event_type == "response.completed":
                final_response = getattr(event, "response", None)
            elif event_type == "response.failed":
                response = getattr(event, "response", None)
                error = getattr(response, "error", None)
                message = getattr(error, "message", None) or "OpenAI Responses stream failed."
                raise ModelProviderError(message=message, status_code=502, model=self.name)
            elif event_type == "response.incomplete":
                final_response = getattr(event, "response", None)
            elif event_type == "error":
                message = getattr(event, "message", None) or "OpenAI Responses stream error."
                raise ModelProviderError(message=message, status_code=502, model=self.name)

        output_text = "".join(output_parts)
        if not output_text and final_response is not None:
            output_text = getattr(final_response, "output_text", "") or ""
        usage = self._get_usage(final_response) if final_response is not None else None
        stop_reason = getattr(final_response, "status", None) if final_response is not None else None
        return output_text, usage, stop_reason

    def _model_params(self, output_format: type[BaseModel] | None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.max_output_tokens is not None:
            params["max_output_tokens"] = self.max_output_tokens
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if self.reasoning_effort:
            params["reasoning"] = {"effort": self.reasoning_effort}
        if output_format is not None:
            schema = SchemaOptimizer.create_optimized_json_schema(output_format)
            params["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "agent_output",
                    "schema": schema,
                    "strict": True,
                }
            }
        return params

    def _split_instructions(self, messages: list[BaseMessage]) -> tuple[str, list[BaseMessage]]:
        instructions: list[str] = []
        input_messages: list[BaseMessage] = []
        for message in messages:
            if isinstance(message, SystemMessage):
                instructions.append(self._system_content_to_text(message.content))
            else:
                input_messages.append(message)

        instruction_text = "\n\n".join(item for item in instructions if item.strip())
        if not instruction_text:
            instruction_text = "You are a helpful assistant."
        return instruction_text, input_messages

    def _first_json_object(self, text: str) -> str:
        start = text.find("{")
        if start < 0:
            return text

        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        return text

    def _system_content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return str(content)
        parts: list[str] = []
        for part in content:
            if getattr(part, "type", None) == "text":
                parts.append(str(getattr(part, "text", "")))
        return "\n".join(parts)

    def _get_usage(self, response: Any) -> ChatInvokeUsage | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0)
        return ChatInvokeUsage(
            prompt_tokens=prompt_tokens,
            prompt_cached_tokens=self._cached_input_tokens(usage),
            prompt_cache_creation_tokens=None,
            prompt_image_tokens=None,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _cached_input_tokens(self, usage: Any) -> int | None:
        details = getattr(usage, "input_tokens_details", None)
        if details is None:
            return None
        cached = getattr(details, "cached_tokens", None)
        return int(cached) if cached is not None else None
