export function evidenceElementId(evidenceId: string): string {
  const safeId = evidenceId.replace(/[^a-zA-Z0-9_-]/g, "-");
  return `evidence-item-${safeId}`;
}

export function scrollEvidenceIntoView(evidenceId: string): void {
  window.requestAnimationFrame(() => {
    document.getElementById(evidenceElementId(evidenceId))?.scrollIntoView({
      block: "nearest",
      behavior: "smooth",
    });
  });
}
