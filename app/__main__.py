import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import ConfigError, Settings
from .handlers import router
from .transcriber import Transcriber

log = logging.getLogger("voice2text")


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        raise SystemExit(f"config: {exc}") from None

    log.info("loading model %s (%s)…", settings.model_name, settings.compute_type)
    transcriber = await asyncio.to_thread(Transcriber, settings)
    log.info("model ready")

    dp = Dispatcher(settings=settings, transcriber=transcriber)
    dp.include_router(router)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    log.info("running as @%s", me.username)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
