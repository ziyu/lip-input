"""API-contract injection tests of our adapter, not real upstream inference."""
import contextlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from server.lip_server import mpc_worker


class AdapterContractTests(unittest.TestCase):
    def run_worker(self, *, landmarks=None, detector_error=None, text="INJECTED", check=False):
        calls = []
        torch = types.ModuleType("torch")
        torch.device = lambda device: device
        torch.no_grad = contextlib.nullcontext
        upstream = types.ModuleType("pipelines.pipeline")

        class Pipeline:
            def __init__(self, config, detector, face_track, device):
                calls.append((config, detector, face_track, device))
                self.modality = "video"
                self.dataloader = types.SimpleNamespace(load_data=self.load_data)
                self.model = types.SimpleNamespace(infer=self.infer)
            def process_landmarks(self, video, landmark_file):
                calls.append(("landmarks", video, landmark_file))
                if detector_error:
                    raise detector_error
                return landmarks
            def load_data(self, video, landmarks):
                calls.append(("load", video))
                return "injected-tensor"
            def infer(self, data):
                calls.append(("infer", data))
                return text

        upstream.InferencePipeline = Pipeline
        with tempfile.TemporaryDirectory() as directory:
            argv = ["worker", "--root", directory, "--config", "model.ini", "--device", "cpu"]
            argv += ["--check"] if check else ["--video", "silent.mp4"]
            # Our worker normally lives in a fresh process; restore global state
            # because this unit test calls it in-process with fake modules.
            import os
            cwd, path = os.getcwd(), list(sys.path)
            try:
                with patch.object(sys, "argv", argv), patch.dict(sys.modules, {"torch": torch, "pipelines.pipeline": upstream}):
                    result = mpc_worker.main()
            finally:
                os.chdir(cwd)
                sys.path[:] = path
        return result, calls

    def test_exact_visual_pipeline_sequence(self):
        result, calls = self.run_worker(landmarks=[object()] * 30)
        self.assertEqual(result, {"text": "INJECTED"})
        self.assertEqual(calls, [("model.ini", "mediapipe", True, "cpu"),
                                 ("landmarks", "silent.mp4", None), ("load", "silent.mp4"),
                                 ("infer", "injected-tensor")])

    def test_upstream_no_face_assertion_is_mapped(self):
        result, calls = self.run_worker(detector_error=AssertionError("Cannot detect any frames in the video"))
        self.assertEqual(result, {"error": "no_face"})
        self.assertEqual(len(calls), 2)

    def test_inadequate_face_coverage_is_rejected(self):
        for landmarks in (None, [], [None] * 30, [object()] * 10 + [None] * 20):
            result, calls = self.run_worker(landmarks=landmarks)
            self.assertEqual(result, {"error": "no_face"})
            self.assertEqual(len(calls), 2)

    def test_empty_transcript_is_not_fabricated(self):
        result, _ = self.run_worker(landmarks=[object()] * 30, text="  ")
        self.assertEqual(result, {"error": "no_speech"})

    def test_check_loads_pipeline_without_transcribing(self):
        result, calls = self.run_worker(check=True)
        self.assertEqual(result, {"ready": True})
        self.assertEqual(len(calls), 1)
