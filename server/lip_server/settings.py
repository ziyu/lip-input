import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

MODEL_NAME = "mpc001-vsr-multilingual"
UPSTREAM_REVISION = "5e1405db0ae816509fb312f9a578724c2e0de0c7"
LANGUAGES = {"en": "English", "zh": "Mandarin Chinese"}


@dataclass(frozen=True)
class Settings:
    max_upload_bytes: int = 20 * 1024 * 1024
    max_duration_seconds: float = 15.0
    min_duration_seconds: float = 1.0
    max_dimension: int = 1920
    max_pixels: int = 1920 * 1080
    max_concurrency: int = 1
    request_timeout_seconds: float = 120.0
    upload_timeout_seconds: float = 30.0
    process_timeout_seconds: float = 30.0
    temp_dir: Path | None = None
    upstream_root: Path | None = None
    runtime_python: str = sys.executable
    configs: dict[str, Path] = field(default_factory=dict)
    enable_upstream: bool = False
    license_acknowledged: bool = False
    device: str = "cpu"

    def __post_init__(self):
        if not 1 <= self.max_concurrency <= 4:
            raise ValueError("max_concurrency must be between 1 and 4")
        if not 1 <= self.min_duration_seconds <= self.max_duration_seconds <= 15:
            raise ValueError("duration bounds must be within 1–15 seconds")
        if self.max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        for value in (self.request_timeout_seconds, self.upload_timeout_seconds,
                      self.process_timeout_seconds):
            if value <= 0:
                raise ValueError("timeouts must be positive")

    @classmethod
    def from_env(cls):
        root = os.getenv("LIP_UPSTREAM_ROOT")
        configs = {}
        for language in LANGUAGES:
            config = os.getenv(f"LIP_CONFIG_{language.upper()}")
            if config:
                configs[language] = Path(config).expanduser().resolve()
        temp = os.getenv("LIP_TEMP_DIR")
        return cls(
            upstream_root=Path(root).expanduser().resolve() if root else None,
            runtime_python=os.getenv("LIP_RUNTIME_PYTHON", sys.executable),
            configs=configs,
            enable_upstream=os.getenv("LIP_ENABLE_UPSTREAM") == "1",
            license_acknowledged=os.getenv("LIP_LICENSE_ACK") == "I_HAVE_VERIFIED_MY_RIGHTS",
            device=os.getenv("LIP_DEVICE", "cpu"),
            temp_dir=Path(temp).expanduser().resolve() if temp else None,
        )
