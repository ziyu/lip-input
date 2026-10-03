"""Runs only in the operator-provisioned upstream environment (Python 3.8+).

No vendored upstream implementation, downloads, microphone, or audio inference.
The pipeline sequence follows upstream pipelines/pipeline.py at the pinned SHA.
"""
import argparse
import contextlib
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--video")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    os.chdir(args.root)
    sys.path.insert(0, args.root)
    # Avoid logging model-generated text or video metadata to the API log.
    with open(os.devnull, "w") as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        try:
            import torch
            from pipelines.pipeline import InferencePipeline
            pipeline = InferencePipeline(
                args.config, detector="mediapipe", face_track=True,
                device=torch.device(args.device),
            )
            if pipeline.modality != "video":
                return {"error": "model_unavailable"}
        except Exception:
            return {"error": "model_unavailable"}
        if args.check:
            return {"ready": True}
        try:
            # Splitting upstream forward allows rejecting missing face tracks
            # before its interpolation can hide long gaps. No pickle upload API.
            try:
                landmarks = pipeline.process_landmarks(args.video, None)
            except AssertionError as exc:
                if "Cannot detect any frames" in str(exc):
                    return {"error": "no_face"}
                raise
            if landmarks is None or not len(landmarks):
                return {"error": "no_face"}
            if sum(item is not None for item in landmarks) / len(landmarks) < 0.8:
                return {"error": "no_face"}
            with torch.no_grad():
                data = pipeline.dataloader.load_data(args.video, landmarks)
                text = pipeline.model.infer(data)
            if not isinstance(text, str) or not text.strip():
                return {"error": "no_speech"}
            return {"text": text.strip()}
        except Exception:
            return {"error": "inference_failed"}


if __name__ == "__main__":
    print("LIP_RESULT:" + json.dumps(main(), ensure_ascii=False))
