"""Telegram handlers: receive audio, statuses, send transcript."""
from __future__ import annotations

import asyncio
import html
import logging
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import NamedTuple

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import (
    BufferedInputFile,
    Message,
    MessageOriginChannel,
    MessageOriginChat,
    MessageOriginHiddenUser,
    MessageOriginUser,
)

from .config import Settings
from .textutil import fmt_duration, split_text
from .transcriber import Progress, Transcriber, Transcript

log = logging.getLogger(__name__)

router = Router(name="voice")

CHUNK_LIMIT = 3600
SEND_AS_FILE_OVER = 8000
PROGRESS_INTERVAL_SEC = 5


class AudioPart(NamedTuple):
    file_id: str
    duration: int | None
    file_name: str | None


def extract_audio(message: Message) -> AudioPart | None:
    """Get audio part from message, if any."""
    if message.voice:
        return AudioPart(message.voice.file_id, message.voice.duration, "voice.oga")
    if message.audio:
        return AudioPart(
            message.audio.file_id, message.audio.duration, message.audio.file_name
        )
    if message.video_note:
        return AudioPart(
            message.video_note.file_id, message.video_note.duration, "note.mp4"
        )
    if message.video:
        return AudioPart(message.video.file_id, message.video.duration, "video.mp4")
    doc = message.document
    if doc and doc.mime_type and doc.mime_type.split("/")[0] in ("audio", "video"):
        return AudioPart(doc.file_id, None, doc.file_name)
    return None


def sender_name(message: Message) -> str | None:
    """Author name of the forwarded message, or None if not a forward.

    Telegram provides forward attribution differently in four cases: regular user,
    user with forward privacy enabled (only name as string, no profile), group, and channel.
    """

    origin = message.forward_origin
    if origin is None:
        return None
    if isinstance(origin, MessageOriginUser):
        return origin.sender_user.full_name
    if isinstance(origin, MessageOriginHiddenUser):
        return origin.sender_user_name
    if isinstance(origin, MessageOriginChat):
        return origin.author_signature or origin.sender_chat.title
    if isinstance(origin, MessageOriginChannel):
        return origin.author_signature or origin.chat.title
    return None


def _allowed(message: Message, settings: Settings) -> bool:
    if not settings.allowed_user_ids:
        return True
    user = message.from_user  # None on channel posts and anonymous admins
    if user is not None and user.id in settings.allowed_user_ids:
        return True
    log.warning("blocked: user_id=%s", user.id if user else "no from_user")
    return False


async def _tick_progress(bot: Bot, status: Message, progress: Progress) -> None:
    """Refresh the status message and the typing indicator while recognition runs."""
    while True:
        await asyncio.sleep(PROGRESS_INTERVAL_SEC)
        tail = (
            f" {fmt_duration(progress.done)} / {fmt_duration(progress.total)}"
            if progress.total
            else ""
        )
        with suppress(TelegramBadRequest):
            await status.edit_text(f"🧠 Recognizing…{tail}")
        # The typing indicator expires after ~5 seconds — send it again.
        await bot.send_chat_action(status.chat.id, ChatAction.TYPING)


async def _transcribe_with_status(
    bot: Bot,
    status: Message,
    transcriber: Transcriber,
    path: Path,
    duration: int | None,
) -> Transcript | None:
    """Queue → recognition, with live status. None — error, already shown."""
    progress = Progress(total=float(duration) if duration else None)
    ticker: asyncio.Task[None] | None = None

    async def on_locked() -> None:
        nonlocal ticker
        await bot.send_chat_action(status.chat.id, ChatAction.TYPING)
        with suppress(TelegramBadRequest):
            await status.edit_text("🧠 Recognizing…")
        ticker = asyncio.create_task(_tick_progress(bot, status, progress))

    if transcriber.busy:
        with suppress(TelegramBadRequest):
            await status.edit_text("⏳ Busy with another message, you're in the queue…")

    try:
        return await transcriber.transcribe(path, progress, on_locked=on_locked)
    except Exception:
        log.exception("Transcription failed")
        with suppress(TelegramBadRequest):
            await status.edit_text("💥 Cannot recognize — see logs.")
        return None
    finally:
        if ticker is not None:
            ticker.cancel()
            with suppress(asyncio.CancelledError):
                await ticker


async def _reply_transcript(
    message: Message, status: Message, transcript: Transcript, name: str | None
) -> None:
    meta = (
        f"{fmt_duration(transcript.duration)}, {transcript.language}, "
        f"{len(transcript.text)} characters"
    )

    if len(transcript.text) > SEND_AS_FILE_OVER:
        await status.delete()
        header = f"Name: {name}\n\n" if name else ""
        await message.reply_document(
            BufferedInputFile(
                (header + transcript.text).encode("utf-8"),
                filename="transcript.txt",
            ),
            caption=f"📄 {name + ', ' if name else ''}{meta}",
            parse_mode=None,
        )
        return

    chunks = split_text(transcript.text, CHUNK_LIMIT)
    first = html.escape(chunks[0])
    if name:
        first = f"<b>Name:</b> {html.escape(name)}\n{first}"

    await status.edit_text(first)
    for chunk in chunks[1:]:
        await message.answer(html.escape(chunk))


@router.message(CommandStart())
async def on_start(message: Message, settings: Settings) -> None:
    await message.answer(
        "Send or forward a voice message — I will reply with text.\n"
        "For forwarded messages, the first line will be the author's name.\n\n"
        "I also understand audio files, video notes, and video. "
        f"Model: <code>{settings.model_name}</code>, "
        f"language: <code>{settings.language or 'auto-detect'}</code>"
    )


@router.message(F.voice | F.audio | F.video_note | F.video | F.document)
async def on_audio(
    message: Message, bot: Bot, settings: Settings, transcriber: Transcriber
) -> None:
    if not _allowed(message, settings):
        return

    part = extract_audio(message)
    if part is None:
        await message.reply("This is not an audio message — send a voice message or audio file.")
        return

    if (
        settings.max_duration_sec
        and part.duration
        and part.duration > settings.max_duration_sec
    ):
        await message.reply(
            f"Too long: {fmt_duration(part.duration)}, "
            f"limit {fmt_duration(settings.max_duration_sec)}."
        )
        return

    hint = f" ({fmt_duration(part.duration)})" if part.duration else ""
    status = await message.reply(f"🎧 Downloading{hint}…")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / (Path(part.file_name or "audio").name or "audio")
        try:
            file = await bot.get_file(part.file_id)
            await bot.download_file(file.file_path, destination=path)
        except TelegramBadRequest as exc:
            # The Bot API only serves files up to 20 MB.
            await status.edit_text(
                f"Couldn't fetch the file: {exc.message}", parse_mode=None
            )
            return

        transcript = await _transcribe_with_status(
            bot, status, transcriber, path, part.duration
        )

    if transcript is None:
        return
    if not transcript.text:
        await status.edit_text("🤷 No speech found — sounds like silence.")
        return

    log.info(
        "done: %s, %s, %d chars",
        fmt_duration(transcript.duration),
        transcript.language,
        len(transcript.text),
    )
    await _reply_transcript(message, status, transcript, sender_name(message))
