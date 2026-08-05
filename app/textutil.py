"""Pure text helpers — no dependencies, covered by tests."""

from __future__ import annotations


def fmt_duration(seconds: float) -> str:
    """65 → «1:05», 3665 → «1:01:05»."""
    total = int(seconds)
    if total >= 3600:
        return f"{total // 3600}:{total // 60 % 60:02d}:{total % 60:02d}"
    return f"{total // 60}:{total % 60:02d}"


def split_text(text: str, limit: int) -> list[str]:
    """Cut text into chunks no longer than ``limit``.

    Tries to cut at sentence boundaries first, then at word boundaries;
    if there are no spaces at all — cuts hard at the limit.
    """

    chunks: list[str] = []
    while len(text) > limit:
        window = text[:limit]
        cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        else:
            cut += 1
        chunks.append(text[:cut].strip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks
