import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import ConfigError, Settings
from .handlers import router
from .transcriber import Transcriber

log = logging.getLogger("voice2text")

HEARTBEAT_FILE = Path(os.getenv("HEARTBEAT_FILE", "/tmp/heartbeat"))
HEARTBEAT_INTERVAL_SEC = 30


async def _heartbeat() -> None:
    """Touch a file so the container HEALTHCHECK can see the event loop is alive.

    This catches a wedged or crashed loop inside a process that is still running.
    It says nothing about Telegram reachability — aiogram reconnects on its own.
    """
    while True:
        HEARTBEAT_FILE.touch()
        await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        raise SystemExit(f"config: {exc}") from None

    # huggingface_hub reads HF_TOKEN from the environment on its own; we only surface
    # its absence, because that is what the "unauthenticated requests" warning means.
    if not os.getenv("HF_TOKEN"):
        log.info("no HF_TOKEN set — model downloads use anonymous Hugging Face limits")

    log.info("loading model %s (%s)…", settings.model_name, settings.compute_type)
    transcriber = await asyncio.to_thread(Transcriber, settings)
    log.info("model ready")

    dp = Dispatcher(settings=settings, transcriber=transcriber)
    dp.include_router(router)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    log.info("running as @%s", me.username)

    heartbeat = asyncio.create_task(_heartbeat())
    try:
        await dp.start_polling(bot)
    finally:
        heartbeat.cancel()


if __name__ == "__main__":
    asyncio.run(main())
