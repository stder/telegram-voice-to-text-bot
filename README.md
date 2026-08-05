# Telegram voice-to-text bot

[![tests](https://github.com/ТВОЙ_ЛОГИН/telegram-voice-to-text-bot/actions/workflows/tests.yml/badge.svg)](https://github.com/ТВОЙ_ЛОГИН/telegram-voice-to-text-bot/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Forward a Telegram voice message to this bot and get the text back. It transcribes voice
messages, audio files and video notes **locally, on your own machine** — the audio never
goes to a cloud speech-to-text service, and there are no API keys to pay for.

Speech recognition runs on the CPU through
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) (OpenAI's Whisper model), so
a cheap VPS without a GPU is enough. Setup is one `docker compose` command.

## Getting started

1. Get a token from [@BotFather](https://t.me/BotFather) (`/newbot`).
2. Look up your user id with [@userinfobot](https://t.me/userinfobot).
3. Fill in `.env`:

```sh
cp .env.example .env
$EDITOR .env   # BOT_TOKEN + ALLOWED_USER_IDS
```

4. Bring it up:

```sh
docker compose up -d --build
docker compose logs -f
```

The first start downloads the model weights (`large-v3-turbo` ≈ 1.6 GB) into `./models`,
which takes a minute or two. After that they come from the cache.

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

Two settings worth a second look:

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

Tests:

```sh
python3 -m unittest
```

Running without Docker:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
set -a && . ./.env && set +a
python -m app
```
