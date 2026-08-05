# Security policy

## Reporting a vulnerability

Please report security issues privately through
[GitHub Security Advisories](https://github.com/stder/telegram-voice-to-text-bot/security/advisories/new)
rather than opening a public issue. Expect a first reply within a week.

## Scope notes

The bot processes audio entirely on the machine it runs on and sends nothing to any
third-party service other than Telegram itself. Downloaded audio lives in a temporary
directory and is deleted as soon as the transcript is produced.

Two things are worth knowing when you deploy it:

- **`BOT_TOKEN` grants full control of the bot.** It is read from `.env`, which is
  excluded from git and from the Docker build context. Anyone with the token can receive
  the messages people send to your bot.
- **An empty `ALLOWED_USER_IDS` leaves the bot open to anyone** who discovers its
  username. Transcription is CPU-heavy, so an open bot is a usable denial-of-service
  target. Set the variable on any public deployment.
