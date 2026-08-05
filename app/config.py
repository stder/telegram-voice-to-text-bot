"""Configuration from environment variables (.env is picked up by docker compose)."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(Exception):
    """Invalid environment value — fail on startup with a clear message."""


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} — must be an integer") from None


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration snapshot taken at startup; frozen so nothing mutates it later."""

    bot_token: str
    model_name: str
    compute_type: str
    language: str | None
    cpu_threads: int
    beam_size: int
    max_duration_sec: int
    allowed_user_ids: frozenset[int]

    @classmethod
    def from_env(cls) -> Settings:
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ConfigError(
                "BOT_TOKEN is empty — get a token from @BotFather and put it in .env"
            )

        raw_ids = os.getenv("ALLOWED_USER_IDS", "").replace(" ", "")
        try:
            allowed = frozenset(int(x) for x in raw_ids.split(",") if x)
        except ValueError:
            raise ConfigError(
                f"ALLOWED_USER_IDS={raw_ids!r} — must be comma-separated integer ids"
            ) from None

        return cls(
            bot_token=token,
            model_name=os.getenv("WHISPER_MODEL", "large-v3-turbo"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            language=os.getenv("WHISPER_LANGUAGE") or None,
            cpu_threads=_int_env("WHISPER_CPU_THREADS", 0),
            beam_size=_int_env("WHISPER_BEAM_SIZE", 5),
            max_duration_sec=_int_env("MAX_DURATION_SEC", 0),
            allowed_user_ids=allowed,
        )
