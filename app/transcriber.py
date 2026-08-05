"""Wrapper around faster-whisper.

Model is loaded once per process and protected by a queue: CPU has no reserve
for parallel transcriptions — the second will only slow down the first.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

from .config import Settings


@dataclass(slots=True)
class Progress:
    """Written from the worker thread, read by the status ticker.

    Atomicity is not needed — these are just numbers for the progress bar.
    """

    done: float = 0.0
    total: float | None = None


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str
    duration: float


class Transcriber:
    """Owns the model and the queue in front of it."""

    def __init__(self, settings: Settings) -> None:
        self._language = settings.language
        self._beam_size = settings.beam_size
        self._model = WhisperModel(
            settings.model_name,
            device="cpu",
            compute_type=settings.compute_type,
            cpu_threads=settings.cpu_threads,
        )
        self._lock = asyncio.Lock()

    @property
    def busy(self) -> bool:
        return self._lock.locked()

    async def transcribe(
        self,
        path: Path,
        progress: Progress,
        on_locked: Callable[[], Awaitable[None]] | None = None,
    ) -> Transcript:
        """Waits its turn and transcribes in a worker thread.

        ``on_locked`` is called when the queue is reached — the handler switches
        the status from "in queue" to "transcribing".
        """

        async with self._lock:
            if on_locked is not None:
                await on_locked()
            return await asyncio.to_thread(self._run, path, progress)

    def _run(self, path: Path, progress: Progress) -> Transcript:
        segments, info = self._model.transcribe(
            str(path),
            language=self._language,
            beam_size=self._beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        progress.total = info.duration

        parts: list[str] = []
        for segment in segments:
            if text := segment.text.strip():
                parts.append(text)
            progress.done = segment.end

        return Transcript(" ".join(parts), info.language, info.duration)
