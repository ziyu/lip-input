import json
import math
from dataclasses import dataclass
from pathlib import Path

from .errors import ServiceError
from .process import run_process
from .settings import Settings


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    frames: int | None
    has_audio: bool


async def probe_video(path: Path, settings: Settings) -> VideoInfo:
    code, output = await run_process([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
        "-format_whitelist", "mov,matroska,webm,avi", "-show_streams",
        "-show_format", "-of", "json", str(path),
    ], timeout=settings.process_timeout_seconds)
    try:
        payload = json.loads(output)
        streams = payload["streams"]
        video = [s for s in streams if s.get("codec_type") == "video"]
        if code != 0 or len(video) != 1:
            raise ValueError("one video stream required")
        stream = video[0]
        duration = float(stream.get("duration", payload.get("format", {}).get("duration", "nan")))
        width, height = int(stream["width"]), int(stream["height"])
        frames = int(stream["nb_frames"]) if stream.get("nb_frames", "").isdigit() else None
        if not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
            raise ValueError("invalid dimensions/duration")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ServiceError(415, "invalid_video", "Upload one valid MP4, MOV, WebM, or AVI video.") from exc
    if max(width, height) > settings.max_dimension or width * height > settings.max_pixels:
        raise ServiceError(422, "video_dimensions", "Use a video no larger than 1920×1080 (portrait is supported).")
    if duration < settings.min_duration_seconds:
        raise ServiceError(422, "too_short", f"Record at least {settings.min_duration_seconds:g} second of video.")
    if duration > settings.max_duration_seconds + 0.05:
        raise ServiceError(422, "too_long", f"Record no more than {settings.max_duration_seconds:g} seconds.")
    return VideoInfo(duration, width, height, frames, any(s.get("codec_type") == "audio" for s in streams))


async def normalize_video(source: Path, destination: Path, settings: Settings) -> VideoInfo:
    await probe_video(source, settings)
    # Only a local video stream is decoded. No audio/subtitle/data stream survives.
    # FFmpeg applies rotation metadata before scaling. Limit decoded size and time.
    code, _ = await run_process([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-protocol_whitelist", "file,pipe", "-format_whitelist", "mov,matroska,webm,avi",
        "-threads", "1", "-i", str(source), "-map", "0:v:0", "-an", "-sn", "-dn",
        "-map_metadata", "-1", "-vf", "fps=25,scale=640:640:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
        "-t", str(settings.max_duration_seconds + 0.08), "-frames:v", "377",
        "-c:v", "libx264", "-threads", "1", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(destination),
    ], timeout=settings.process_timeout_seconds)
    if code != 0 or not destination.is_file():
        raise ServiceError(415, "invalid_video", "The video could not be decoded. Record a new clip.")
    info = await probe_video(destination, settings)
    if info.has_audio:
        raise ServiceError(500, "normalization_failed", "Audio-free video normalization failed.")
    if info.frames is None or info.frames < int(settings.min_duration_seconds * 25):
        raise ServiceError(422, "too_short", "The video contains too few decodable frames.")
    return info
