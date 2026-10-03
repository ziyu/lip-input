"""Explicit adapter for mpc001 multilingual VSR; no sample or fallback transcript."""
import configparser
import json
import shutil
from pathlib import Path
from typing import Protocol

from .errors import ServiceError
from .process import run_process
from .settings import LANGUAGES, MODEL_NAME, UPSTREAM_REVISION, Settings


class Backend(Protocol):
    async def initialize(self) -> None: ...
    def reason(self, language: str) -> str | None: ...
    async def transcribe(self, video: Path, language: str) -> str: ...


def validate_config(config_path: Path, root: Path) -> str | None:
    try:
        config = configparser.ConfigParser()
        if not config.read(config_path):
            return "Language config is missing."
        if config.get("input", "modality") != "video":
            return "Only visual-only configs (modality=video) are permitted."
        if config.getfloat("input", "v_fps") != 25 or config.getfloat("model", "v_fps") != 25:
            return "This adapter requires input/model v_fps=25."
        for key in ("model_path", "model_conf", "rnnlm", "rnnlm_conf"):
            value = config.get("model", key)
            if not value or not (root / value).is_file():
                return f"Required configured model asset is missing: {key}."
        for key in ("penalty", "ctc_weight", "lm_weight"):
            config.getfloat("decode", key)
        if not 1 <= config.getint("decode", "beam_size") <= 100:
            return "Decoder beam_size must be between 1 and 100."
    except (OSError, ValueError, configparser.Error):
        return "Language config is invalid. Use the documented upstream visual-only config."
    return None


class MPCBackend:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.reasons = {lang: "Model runtime has not been initialized." for lang in LANGUAGES}
        self.worker = Path(__file__).with_name("mpc_worker.py").resolve()

    def reason(self, language: str) -> str | None:
        return self.reasons.get(language, "Unsupported language.")

    async def initialize(self):
        s = self.settings
        common = None
        if not s.enable_upstream or not s.license_acknowledged:
            common = "The operator must verify model/code licensing, provision weights, and explicitly enable the upstream runtime. See server/README.md."
        elif not s.upstream_root or not (s.upstream_root / "pipelines/pipeline.py").is_file():
            common = "LIP_UPSTREAM_ROOT must identify the operator's reviewed upstream checkout."
        elif not shutil.which(s.runtime_python):
            common = "LIP_RUNTIME_PYTHON is not executable."
        elif not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            common = "Install FFmpeg and ffprobe in the server runtime."
        if common:
            self.reasons = dict.fromkeys(LANGUAGES, common)
            return
        # Pin the researched interface; no fetching, installing, or accepting terms.
        try:
            code, revision = await run_process(["git", "-C", str(s.upstream_root), "rev-parse", "HEAD"], timeout=5)
            if code != 0 or revision.decode().strip() != UPSTREAM_REVISION:
                self.reasons = dict.fromkeys(LANGUAGES, f"Use reviewed upstream revision {UPSTREAM_REVISION}.")
                return
        except ServiceError:
            self.reasons = dict.fromkeys(LANGUAGES, "Could not verify the upstream checkout revision.")
            return
        for lang in LANGUAGES:
            config = s.configs.get(lang)
            if config is None:
                self.reasons[lang] = f"Set LIP_CONFIG_{lang.upper()} to this language's visual-only model config."
                continue
            self.reasons[lang] = validate_config(config, s.upstream_root)
            if self.reasons[lang]:
                continue
            try:
                # Real model load + detector construction; no fake availability.
                await self._worker(config, check=True)
            except ServiceError as exc:
                self.reasons[lang] = exc.message

    async def _worker(self, config: Path, *, check: bool = False, video: Path | None = None) -> dict:
        s = self.settings
        args = [s.runtime_python, str(self.worker), "--root", str(s.upstream_root),
                "--config", str(config), "--device", s.device]
        args += ["--check"] if check else ["--video", str(video)]
        code, output = await run_process(args, timeout=s.request_timeout_seconds, cwd=s.upstream_root, output_limit=64 * 1024)
        try:
            # Upstream libraries may print diagnostics; worker uses a final marker.
            line = next(line for line in reversed(output.decode("utf-8").splitlines()) if line.startswith("LIP_RESULT:"))
            result = json.loads(line[len("LIP_RESULT:"):])
            if not isinstance(result, dict):
                raise ValueError("invalid result")
        except (StopIteration, UnicodeError, ValueError) as exc:
            raise ServiceError(503, "model_unavailable", "Model runtime failed. Ask the operator to check dependencies and licensed assets.") from exc
        if "error" in result:
            errors = {
                "no_face": (422, "No consistently visible face was found. Face the camera in good light."),
                "no_speech": (422, "The visual model produced no text. Record a new clip."),
                "model_unavailable": (503, "Model loading failed. Check the documented runtime, device, configs, and licensed weights."),
                "inference_failed": (503, "Visual inference failed. Ask the operator to validate the installed runtime."),
            }
            key = result["error"] if result["error"] in errors else "inference_failed"
            status, message = errors[key]
            raise ServiceError(status, key, message)
        if code != 0 or (check and result.get("ready") is not True):
            raise ServiceError(503, "model_unavailable", "Model runtime is not ready.")
        return result

    async def transcribe(self, video: Path, language: str) -> str:
        reason = self.reason(language)
        if reason:
            raise ServiceError(503, "model_unavailable", reason)
        try:
            result = await self._worker(self.settings.configs[language], video=video)
        except ServiceError as exc:
            # A clip-specific decoder failure must not permanently poison
            # this language's readiness. Only proven runtime/model loss does.
            if exc.code in {"model_unavailable", "runtime_unavailable"}:
                self.reasons[language] = exc.message
            raise
        text = result.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 16_384:
            raise ServiceError(503, "invalid_model_result", "The model returned an invalid result.")
        return text.strip()
