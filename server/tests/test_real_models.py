"""Opt-in REAL model acceptance tests. Never enabled by ordinary CI.

Requires operator authorization/licensed assets and two consented, human-labeled,
truly audio-free videos. These checks prove execution, not transcription accuracy.
"""
import os
import tempfile
import unittest
from pathlib import Path

from server.lip_server.backend import MPCBackend
from server.lip_server.errors import ServiceError
from server.lip_server.media import normalize_video, probe_video
from server.lip_server.settings import Settings
from server.tests.test_service import make_clip


@unittest.skipUnless(os.getenv("LIP_RUN_REAL_MODEL_TESTS") == "1", "Real weights/runtime not provisioned; explicitly opt in")
class RealModelAcceptanceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = Settings.from_env()
        self.backend = MPCBackend(self.settings)
        await self.backend.initialize()
        for language in ("en", "zh"):
            self.assertIsNone(self.backend.reason(language), f"{language}: {self.backend.reason(language)}")

    async def test_real_detector_rejects_silent_no_face_clip(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "black.mp4", Path(directory) / "silent.mp4"
            make_clip(source)
            await normalize_video(source, target, self.settings)
            with self.assertRaises(ServiceError) as result:
                await self.backend.transcribe(target, "en")
            self.assertEqual(result.exception.code, "no_face")

    async def test_real_english_and_mandarin_execute_on_silent_video(self):
        for language in ("en", "zh"):
            variable = f"LIP_REAL_{language.upper()}_VIDEO"
            self.assertIn(variable, os.environ, f"Supply a consented audio-free clip via {variable}")
            source = Path(os.environ[variable]).resolve()
            info = await probe_video(source, self.settings)
            self.assertFalse(info.has_audio, "Acceptance input must genuinely contain no audio track")
            with tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "silent.mp4"
                await normalize_video(source, target, self.settings)
                text = await self.backend.transcribe(target, language)
                self.assertIsInstance(text, str)
                self.assertGreater(len(text.strip()), 0)
                self.assertLessEqual(len(text), 16_384)
