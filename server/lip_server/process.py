"""Bounded, cancellable child processes; never invoke a shell."""
import asyncio
import os
import signal
from pathlib import Path

from .errors import ServiceError


async def _stop(process: asyncio.subprocess.Process):
    # Killing the process group also stops FFmpeg/model child processes on Linux.
    # The leader may already have exited while a descendant still owns its
    # stdout pipe or GPU resources. Kill the group even in that case.
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            process.kill()
    except ProcessLookupError:
        pass
    await process.wait()
    # A reaped leader does not imply its pipe transport has observed EOF.
    # Drain without retaining output so event-loop shutdown cannot strand it.
    async def drain():
        if process.stdout is not None:
            while await process.stdout.read(8192):
                pass
    try:
        await asyncio.wait_for(drain(), 2.0)
    except asyncio.TimeoutError:
        # Public Process APIs do not expose pipe close. Only needed if an
        # operator-owned runtime escaped its process group and retained stdout.
        process._transport.close()


async def run_process(args: list[str], *, timeout: float, cwd: Path | None = None,
                      output_limit: int = 256 * 1024) -> tuple[int, bytes]:
    try:
        process = await asyncio.create_subprocess_exec(
            *args, cwd=cwd, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            start_new_session=os.name == "posix",
        )
    except (FileNotFoundError, PermissionError, OSError) as exc:
        raise ServiceError(503, "runtime_unavailable", "Required runtime executable is unavailable; ask the server operator.") from exc

    async def collect():
        output = bytearray()
        while chunk := await process.stdout.read(8192):
            output.extend(chunk)
            if len(output) > output_limit:
                raise ServiceError(503, "runtime_output_limit", "Runtime output exceeded its safety limit.")
        return await process.wait(), bytes(output)

    try:
        return await asyncio.wait_for(collect(), timeout)
    except asyncio.TimeoutError as exc:
        raise ServiceError(504, "inference_timeout", "Processing timed out. Try a shorter clip.") from exc
    finally:
        # Runs on errors, client cancellation, timeout, and successful completion.
        await _stop(process)
