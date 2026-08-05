# Telegram voice-to-text bot

[![tests](https://github.com/stder/telegram-voice-to-text-bot/actions/workflows/tests.yml/badge.svg)](https://github.com/stder/telegram-voice-to-text-bot/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Forward a Telegram voice message to this bot and get the text back. It transcribes voice
messages, audio files and video notes **locally, on your own machine** — the audio never
goes to a cloud speech-to-text service, and there are no API keys to pay for.

Speech recognition runs on the CPU through
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI's Whisper model), so
a cheap VPS without a GPU is enough. Setup is one `docker compose` command.

## Quick start

Nothing to clone and nothing to build — the image is published to GHCR for both x86-64
and arm64. You need Docker and about five minutes.

1. Create a bot with [@BotFather](https://t.me/BotFather) (send it `/newbot`) and copy
   the token it gives you.
2. Get your numeric user id from [@userinfobot](https://t.me/userinfobot).
3. Download two files into an empty folder and fill in those two values:

```sh
curl -O https://raw.githubusercontent.com/stder/telegram-voice-to-text-bot/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/stder/telegram-voice-to-text-bot/main/.env.example
nano .env      # BOT_TOKEN=... and ALLOWED_USER_IDS=...
```

4. Start it:

```sh
docker compose up -d
docker compose logs -f
```

The first start downloads the model weights (`large-v3-turbo` ≈ 1.6 GB), which takes a
minute or two. They are stored in a Docker volume and reused on every later start.

Once the log says `running as @yourbotname`, send the bot a voice message.

## Updating

Docker never updates anything on its own — `latest` is just a label, and the daemon keeps
running the image it already pulled. From the folder holding your `docker-compose.yml`:

```sh
docker compose pull
docker compose up -d
```

The model weights live in a separate volume, so nothing is downloaded again and `.env` is
left alone. The replaced image stays on disk until you run `docker image prune -f`.

`latest` follows the `main` branch, so it can be ahead of the newest release. To stay on a
version you chose, pin it in `docker-compose.yml` and bump it deliberately:

```yaml
image: ghcr.io/stder/telegram-voice-to-text-bot:0.2.0
```

Published tags are listed on the
[releases page](https://github.com/stder/telegram-voice-to-text-bot/releases).

## What it accepts

Voice messages, audio files, video notes, video, and documents with an audio/video
mime type — both sent directly and forwarded. It replies to the original message.
Transcripts longer than 8000 characters arrive as a `transcript.txt` file.

Forwarded messages get a `Name: <author>` first line, which helps when transcripts from
several people pile up in the same chat. Where the name comes from:

| forward source | what you get |
|---|---|
| regular user | full name from their profile |
| forward privacy enabled | name as plain text, no profile link |
| group / channel | author signature, otherwise the chat title |
| your own recording (not a forward) | no name line |

## Configuration

Everything is set through `.env` — see `.env.example` for the full list.

| variable | default | notes |
|---|---|---|
| `BOT_TOKEN` | — | required, from [@BotFather](https://t.me/BotFather) |
| `ALLOWED_USER_IDS` | empty | comma-separated ids. Empty means anyone can use the bot |
| `WHISPER_MODEL` | `large-v3-turbo` | see the model table below |
| `WHISPER_COMPUTE_TYPE` | `int8` | `float32` is more accurate but 2-3x slower |
| `WHISPER_LANGUAGE` | empty | empty = auto-detect |
| `WHISPER_BEAM_SIZE` | `5` | `1` is roughly twice as fast on multi-core, slightly less accurate |
| `WHISPER_CPU_THREADS` | `0` | `0` = every core available to the container |
| `MAX_DURATION_SEC` | `0` | reject longer audio. `0` = no limit |
| `HF_TOKEN` | empty | optional, only for the model download — see below |

Three settings worth a second look:

**`HF_TOKEN`.** The model weights are downloaded from Hugging Face on first start.
Anonymous downloads work but share a low per-IP rate limit, and the hub prints
`You are sending unauthenticated requests to the HF Hub` on every start. A free read
token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) fixes
both — put it in `.env` and restart. It is never used for anything except fetching the
model.

**`WHISPER_LANGUAGE`.** If the language is always the same, set it explicitly. This skips
auto-detection and stops the model from drifting to another language on noisy passages.

**`WHISPER_CPU_THREADS` together with a `cpus` limit.** If you set `cpus: N` in
`docker-compose.yml` on a multi-core machine, you must also set `WHISPER_CPU_THREADS=N`.
Otherwise CTranslate2 spawns one thread per **host** core and they burn the quota
spinning on OpenMP barriers: measured at `--cpus=1`, 68 seconds versus 8 seconds for the
same audio with a single thread — an 8x difference. On a plain single-core host there is
nothing to configure; `cpu_count()` returns 1 and the bot takes one thread on its own.

## Choosing a model

The bot is hardcoded to `device=cpu`. CTranslate2 does support CUDA, but it has no Metal
backend, so on Apple Silicon the CPU is the only option regardless.

Measured with 10 threads, int8, beam=5, on a 42-second sample:

| model | size | speed | accuracy |
|---|---|---|---|
| `small` | 0.5 GB | 8.1x realtime | garbles terms and inflections |
| `medium` | 1.5 GB | 3.0x realtime | nearly clean, but slower than turbo — no reason to pick it |
| `large-v3-turbo` | 1.6 GB | 4.5x realtime | one error per 90 words ← the default |
| `large-v3` | 3 GB | not measured | the reference, but noticeably slower |

"4.5x realtime" means a one-minute voice message takes about 13 seconds. Loading the
model into memory (~2 s) happens once at startup, not per message.

Speed scales **strongly sublinearly** with cores — on turbo, 1 thread gives 1.6x realtime
and 10 threads only 4.5x. Single-core numbers, same 42-second sample:

| model | beam | speed | one-minute voice message |
|---|---|---|---|
| `base` | 1 | 14.1x | ~4 s |
| `small` | 1 | 5.1x | ~12 s |
| `large-v3-turbo` | 1 | 1.6x | ~38 s |
| `large-v3-turbo` | 5 | 1.5x | ~40 s |

A hosted vCPU is usually about twice as slow — double these numbers. On a single core
`beam` makes no difference (1.6x vs 1.5x): `WHISPER_BEAM_SIZE=1` only pays off when there
are spare cores.

## Hardware requirements

Measured on the running bot with `large-v3-turbo` (int8): **1.2 GB RAM** at idle, 710 MB
image. The peak during recognition is barely above idle — weights load once at startup
and the audio itself is small (10 minutes of speech ≈ 38 MB) — so budget +300 MB.

| model | container RAM | disk (image + weights) |
|---|---|---|
| `small` | ~0.6 GB | 1.2 GB |
| `large-v3-turbo` | 1.2 GB (measured) | 2.2 GB |
| `large-v3` | ~2 GB | 3.6 GB |

Any 64-bit CPU works, x86-64 or arm64; no GPU is needed. 32-bit ARM will not run: there
are no CTranslate2 or onnxruntime wheels for armv7.

One core is enough for voice messages a minute or two long — memory is the real limit.
A 1 GB host handles `small`; 2 GB handles turbo, but tightly enough that a 2 GB swap file
is worth adding, or the peak during model loading meets the OOM killer. On Docker
Desktop, give the container at least 4 GB for `large-v3` (Settings → Resources).

## Troubleshooting

**The bot doesn't reply at all.** Look at `docker compose logs`.

- `config: BOT_TOKEN is empty` — `.env` was not picked up. It must sit in the same folder
  as `docker-compose.yml` and be named exactly `.env`.
- The log stops at `running as @yourbotname` and nothing happens when you write to the
  bot — your id is most likely missing from `ALLOWED_USER_IDS`. Rejected senders appear in
  the log as `blocked: user_id=...`; copy that number into the variable, or clear the
  variable entirely to allow everyone.
- Nothing in the log at all after sending a voice message — you are probably writing to a
  different bot than the one whose token is in `.env`.

**The container restarts in a loop, or dies during startup.** Almost always memory. The
default model needs about 1.5 GB while loading; if the host has 2 GB and no swap, the
kernel kills the process. Either add a 2 GB swap file, or switch to a smaller model:

```sh
echo "WHISPER_MODEL=small" >> .env && docker compose up -d
```

**The weights download on every restart.** The `models` volume is missing from your
`docker-compose.yml`, or you are running `docker compose down -v`, which deletes volumes.
Use plain `docker compose down`.

**Recognized as the wrong language.** Auto-detection works from the audio itself and can
slip on short or noisy recordings. If your voice messages are always in one language, set
it explicitly — this is both more accurate and slightly faster:

```sh
echo "WHISPER_LANGUAGE=en" >> .env && docker compose up -d
```

**"Couldn't fetch the file: file is too big".** A Telegram Bot API limit, not a bot
setting: bots may download files up to 20 MB. Voice messages are far below that, but a
forwarded uncompressed recording can exceed it.

**Transcription is very slow.** Check how many cores the container actually gets. A single
core takes about 38 seconds per minute of audio on the default model; `small` brings that
down to roughly 12 seconds with a modest accuracy loss. See
[Choosing a model](#choosing-a-model).

## Limitations

- The Bot API serves files **up to 20 MB**. For voice messages that is hours of audio,
  but a forwarded wav podcast may not fit — the bot replies with a clear error.
- Transcriptions run one at a time: while one is being processed the rest wait in a
  queue (running several in parallel would just eat every core and end up slower).
- An empty `ALLOWED_USER_IDS` means anyone who finds the bot's name can use it and load
  your CPU. Better to fill it in.

## Development

```
app/
  config.py       — Settings from env, validation with readable errors
  transcriber.py  — faster-whisper wrapper: the model plus its queue
  textutil.py     — pure functions: text splitting, duration formatting
  handlers.py     — Telegram handlers (Router, dependencies via DI)
  __main__.py     — wiring and startup: python -m app
tests/            — unit tests for the pure functions
```

Build and run from this checkout instead of the published image:

```sh
git clone https://github.com/stder/telegram-voice-to-text-bot.git
cd telegram-voice-to-text-bot
cp .env.example .env && $EDITOR .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Tests and linter:

```sh
python3 -m unittest
uvx ruff check .
```

Running without Docker:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
set -a && . ./.env && set +a
python -m app
```
