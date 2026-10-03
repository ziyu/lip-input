"""Transport/safety tests, NOT model-quality validation.

Video bytes are genuinely encoded and decoded by FFmpeg. Model text and no-face
outcomes are explicitly injected; no weights or upstream source are executed.
"""
import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from server.lip_server.app import create_app, while_connected
from server.lip_server.backend import MPCBackend, validate_config
from server.lip_server.errors import ServiceError
from server.lip_server.media import normalize_video, probe_video
from server.lip_server.process import run_process
from server.lip_server.settings import Settings


class InjectedBackend:
    """Test-only inference double; never selectable in production settings."""
    def __init__(self, *, error=None, block=False):
        self.error, self.block = error, block
        self.seen = []
        self.started, self.cancelled = asyncio.Event(), asyncio.Event()

    async def initialize(self):
        pass

    def reason(self, language):
        return None

    async def transcribe(self, path, language):
        info = await probe_video(path, Settings())
        assert not info.has_audio
        assert path.name == "silent.mp4"
        self.seen.append((path, language, info))
        self.started.set()
        if self.block:
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()
        if self.error:
            raise self.error
        return "INJECTED TEST RESULT"


def make_clip(path, duration=1.2, audio=False, size="160x120"):
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s={size}:r=25"]
    if audio:
        args += ["-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono"]
    else:
        args += ["-an"]
    args += ["-t", str(duration), "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return path.read_bytes()


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class ServiceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = tempfile.TemporaryDirectory()
        root = Path(cls.fixtures.name)
        cls.silent = make_clip(root / "silent.mp4")
        cls.short = make_clip(root / "short.mp4", 0.4)
        cls.long = make_clip(root / "long.mp4", 15.2)
        cls.audio = make_clip(root / "audio.mp4", audio=True)

    @classmethod
    def tearDownClass(cls):
        cls.fixtures.cleanup()

    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp.name)
        self.settings = Settings(temp_dir=self.temp_path)
        self.backend = InjectedBackend()
        self.app = create_app(self.settings, self.backend)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.assertEqual(list(self.temp_path.iterdir()), [], "request temp files were not removed")
        self.temp.cleanup()

    async def post(self, clip=None, language="en", filename="clip.mp4"):
        return await self.client.post("/v1/transcriptions", data={"language": language},
                                      files={"video": (filename, self.silent if clip is None else clip, "video/mp4")})

    async def test_valid_genuinely_silent_clip_and_repeated_requests(self):
        for language in ("en", "zh", "en"):
            response = await self.post(language=language, filename="../../private.mp4")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {"text": "INJECTED TEST RESULT", "language": language,
                                               "model": f"mpc001-vsr-multilingual:{language}"})
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(list(self.temp_path.iterdir()), [])
        self.assertEqual(len(self.backend.seen), 3)
        self.assertTrue(all(not info.has_audio and info.frames >= 25 for _, _, info in self.backend.seen))
        self.assertEqual(len(set(path.parent for path, _, _ in self.backend.seen)), 3)

    async def test_audio_stream_is_removed_before_model(self):
        response = await self.post(self.audio)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.backend.seen[0][2].has_audio)

    async def test_too_short(self):
        response = await self.post(self.short)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"]["code"], "too_short")
        self.assertFalse(self.backend.seen)

    async def test_too_long(self):
        response = await self.post(self.long)
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"]["code"], "too_long")

    async def test_no_face_is_explicit_injected_inference_error(self):
        self.backend.error = ServiceError(422, "no_face", "No visible face.")
        response = await self.post()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "no_face")
        self.assertEqual(len(self.backend.seen), 1)

    async def test_corrupt_and_empty_video(self):
        for clip in (b"not-a-video", b""):
            response = await self.post(clip)
            self.assertEqual(response.status_code, 415, response.text)
            self.assertEqual(response.json()["detail"]["code"], "invalid_video")
        self.assertFalse(self.backend.seen)

    async def test_unknown_language_and_missing_field(self):
        response = await self.post(language="auto")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"]["code"], "unsupported_language")
        response = await self.client.post("/v1/transcriptions", files={"video": ("x.mp4", self.silent)})
        self.assertEqual(response.status_code, 400)

    async def test_unavailable_models_are_not_mocked(self):
        real = MPCBackend(self.settings)
        await real.initialize()
        app = create_app(self.settings, real)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/v1/capabilities")
            data = response.json()
            self.assertEqual(data["max_duration_seconds"], 15)
            self.assertEqual([row["code"] for row in data["languages"]], ["en", "zh"])
            self.assertTrue(all(not row["available"] and row["reason"] for row in data["languages"]))
            response = await client.post("/v1/transcriptions", data={"language": "en"}, files={"video": ("x.mp4", self.silent)})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"]["code"], "model_unavailable")
            self.assertNotIn("text", response.json())

    async def test_parallel_request_is_rejected_and_task_cancel_cleans_up(self):
        self.backend.block = True
        first = asyncio.create_task(self.post())
        await asyncio.wait_for(self.backend.started.wait(), 5)
        response = await self.post()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "3")
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        self.assertTrue(self.backend.cancelled.is_set())
        self.assertEqual(list(self.temp_path.iterdir()), [])
        self.backend.block = False
        self.assertEqual((await self.post()).status_code, 200)

    async def test_client_disconnect_cancels_inference_and_cleans_up(self):
        self.backend.block = True
        boundary = b"test-boundary"
        body = (b"--" + boundary + b'\r\nContent-Disposition: form-data; name="language"\r\n\r\nen\r\n'
                + b"--" + boundary + b'\r\nContent-Disposition: form-data; name="video"; filename="clip.mp4"\r\nContent-Type: video/mp4\r\n\r\n'
                + self.silent + b"\r\n--" + boundary + b"--\r\n")
        queue = asyncio.Queue()
        queue.put_nowait({"type": "http.request", "body": body, "more_body": False})
        messages = []
        async def send(message):
            messages.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "method": "POST",
                 "path": "/v1/transcriptions", "raw_path": b"/v1/transcriptions", "query_string": b"",
                 "headers": [(b"content-type", b"multipart/form-data; boundary=" + boundary)],
                 "scheme": "http", "server": ("test", 80), "client": ("test", 123), "root_path": ""}
        task = asyncio.create_task(self.app(scope, queue.get, send))
        await asyncio.wait_for(self.backend.started.wait(), 5)
        queue.put_nowait({"type": "http.disconnect"})
        await asyncio.wait_for(task, 3)
        self.assertTrue(self.backend.cancelled.is_set())
        self.assertEqual(list(self.temp_path.iterdir()), [])
        self.assertEqual(messages[0]["status"], 499)

    async def test_oversized_declared_and_chunked_upload_before_parser(self):
        app = create_app(Settings(max_upload_bytes=1024, temp_dir=self.temp_path), self.backend)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/v1/transcriptions", content=b"x", headers={
                "Content-Type": "multipart/form-data; boundary=x", "Content-Length": "100000"})
            self.assertEqual(response.status_code, 413)
            async def chunks():
                for _ in range(80):
                    yield b"x" * 1024
            response = await client.post("/v1/transcriptions", content=chunks(), headers={
                "Content-Type": "multipart/form-data; boundary=x"})
            self.assertEqual(response.status_code, 413)
        self.assertFalse(self.backend.seen)

    async def test_duplicate_parts_and_invalid_content_type(self):
        response = await self.client.post("/v1/transcriptions", files=[
            ("language", (None, "en")), ("video", ("a.mp4", self.silent)), ("video", ("b.mp4", self.silent))])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()["detail"]), {"code", "message"})
        response = await self.client.post("/v1/transcriptions", json={"video": "url"})
        self.assertEqual(response.status_code, 415)


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_kills_actual_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "pid"
            script = "import os,time; open(__import__('sys').argv[1],'w').write(str(os.getpid())); time.sleep(60)"
            with self.assertRaises(ServiceError) as result:
                await run_process([sys.executable, "-c", script, str(pid_file)], timeout=0.3)
            self.assertEqual(result.exception.code, "inference_timeout")
            pid = int(pid_file.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    async def test_cancellation_kills_actual_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "pid"
            script = "import os,time; open(__import__('sys').argv[1],'w').write(str(os.getpid())); time.sleep(60)"
            task = asyncio.create_task(run_process([sys.executable, "-c", script, str(pid_file)], timeout=60))
            for _ in range(100):
                if pid_file.exists():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(pid_file.exists())
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_file.read_text()), 0)

    @unittest.skipUnless(os.name == "posix", "process groups require POSIX")
    async def test_timeout_kills_descendant_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = Path(directory) / "descendant-pid"
            child = "import os,time; open(__import__('sys').argv[1], 'w').write(str(os.getpid())); time.sleep(60)"
            leader = "import subprocess,sys; subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]])"
            with self.assertRaises(ServiceError):
                await run_process([sys.executable, "-c", leader, child, str(pid_file)], timeout=0.4)
            pid = int(pid_file.read_text())
            # An adopted child can briefly remain a zombie awaiting PID 1 reap;
            # that state is terminated and owns no descriptors/GPU resources.
            state = Path(f"/proc/{pid}/stat")
            for _ in range(100):
                if not state.exists() or state.read_text().split()[2] == "Z":
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(not state.exists() or state.read_text().split()[2] == "Z")

    async def test_exited_leader_cleanup_does_not_leak_transport_at_loop_close(self):
        script = r"""
import asyncio, sys
from server.lip_server.process import run_process
from server.lip_server.errors import ServiceError
async def main():
    try:
        await run_process([sys.executable, '-c', 'import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])'], timeout=.2)
    except ServiceError:
        pass
asyncio.run(main())
"""
        process = await asyncio.create_subprocess_exec(sys.executable, "-Werror", "-c", script,
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(), 5)
        self.assertEqual(process.returncode, 0, stderr.decode())
        self.assertNotIn(b"Event loop is closed", stderr)
        self.assertNotIn(b"unclosed transport", stderr)
        self.assertNotIn(b"Exception ignored", stderr)

    async def test_clip_error_does_not_poison_model_capability(self):
        backend = MPCBackend(Settings(configs={"en": Path("operator-config.ini")}))
        backend.reasons["en"] = None
        backend._worker = AsyncMock(side_effect=[
            ServiceError(503, "inference_failed", "This clip failed."), {"text": "INJECTED RETRY"}])
        with self.assertRaises(ServiceError):
            await backend.transcribe(Path("test.mp4"), "en")
        self.assertIsNone(backend.reason("en"))
        self.assertEqual(await backend.transcribe(Path("test.mp4"), "en"), "INJECTED RETRY")

    async def test_output_limit(self):
        with self.assertRaises(ServiceError) as result:
            await run_process([sys.executable, "-c", "print('x'*20000)"], timeout=3, output_limit=100)
        self.assertEqual(result.exception.code, "runtime_output_limit")

    async def test_work_timeout_awaits_cancel(self):
        class Request:
            async def receive(self):
                await asyncio.Event().wait()
        cancelled = asyncio.Event()
        async def slow():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        with self.assertRaises(ServiceError) as result:
            await while_connected(Request(), slow(), 0.03)
        self.assertEqual(result.exception.code, "inference_timeout")
        self.assertTrue(cancelled.is_set())


class ConfigurationTests(unittest.TestCase):
    def test_reject_audio_or_wrong_frame_rate_configs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "model.ini"
            config.write_text("[input]\nmodality=audiovisual\nv_fps=25\n[model]\nv_fps=25\n")
            self.assertIn("visual-only", validate_config(config, root))
            config.write_text("[input]\nmodality=video\nv_fps=30\n[model]\nv_fps=25\n")
            self.assertIn("v_fps=25", validate_config(config, root))

    def test_missing_models_are_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "model.ini"
            config.write_text("[input]\nmodality=video\nv_fps=25\n[model]\nv_fps=25\nmodel_path=absent.pth\n")
            self.assertIn("model_path", validate_config(config, root))

    def test_invalid_settings_fail_closed(self):
        with self.assertRaises(ValueError):
            Settings(max_concurrency=0)
        with self.assertRaises(ValueError):
            Settings(max_duration_seconds=3600)


if __name__ == "__main__":
    unittest.main()
