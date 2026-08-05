"""Unit tests for pure functions: python -m unittest.

Covers only config and textutil on purpose — they have no dependencies,
can be run anywhere without aiogram and faster-whisper.
"""

import os
import unittest
from unittest import mock

from app.config import ConfigError, Settings
from app.textutil import fmt_duration, split_text


class FmtDuration(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(fmt_duration(5), "0:05")

    def test_minutes(self):
        self.assertEqual(fmt_duration(65), "1:05")

    def test_hours(self):
        self.assertEqual(fmt_duration(3665), "1:01:05")


class SplitText(unittest.TestCase):
    def test_short_returns_as_is(self):
        self.assertEqual(split_text("Hello", 100), ["Hello"])

    def test_prefers_sentence_boundary(self):
        # Limit must be under the text length (43), or nothing gets split at all.
        text = "First sentence is so long. Second is short."
        chunks = split_text(text, 30)
        self.assertEqual(chunks, ["First sentence is so long.", "Second is short."])

    def test_falls_back_to_word_boundary(self):
        text = ("word " * 20).strip()
        for chunk in split_text(text, 25):
            self.assertLessEqual(len(chunk), 25)
            self.assertTrue(chunk)

    def test_hard_cut_without_spaces(self):
        chunks = split_text("a" * 100, 30)
        self.assertEqual([len(c) for c in chunks], [30, 30, 30, 10])

    def test_nothing_lost(self):
        text = ("Sentense number one. " * 40).strip()
        self.assertEqual(" ".join(split_text(text, 100)), text)


class SettingsFromEnv(unittest.TestCase):
    def test_defaults(self):
        with mock.patch.dict(os.environ, {"BOT_TOKEN": "123:abc"}, clear=True):
            s = Settings.from_env()
        self.assertEqual(s.model_name, "large-v3-turbo")
        self.assertEqual(s.beam_size, 5)
        self.assertIsNone(s.language)
        self.assertEqual(s.allowed_user_ids, frozenset())

    def test_allowed_ids_with_spaces(self):
        env = {"BOT_TOKEN": "x", "ALLOWED_USER_IDS": "1, 22 ,333"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                Settings.from_env().allowed_user_ids, frozenset({1, 22, 333})
            )

    def test_missing_token(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env()

    def test_bad_int(self):
        env = {"BOT_TOKEN": "x", "WHISPER_BEAM_SIZE": "five"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env()
