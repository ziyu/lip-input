import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse

from .backend import Backend, MPCBackend
from .errors import ServiceError
from .media import normalize_video
from .settings import LANGUAGES, MODEL_NAME, Settings


class UploadGuard:
    """Bound concurrency and the raw body *before* multipart parsing/spooling.

    At most one 20 MiB upload plus framing is held in memory by default. This
    protects against chunked uploads, duplicate parts, and lying Content-Length.
    Run one ASGI worker; use authenticated proxy admission/rate limits as well.
    """
    def __init__(self, app, settings: Settings):
        self.app, self.settings, self.active = app, settings, 0

    async def __call__(self, scope, receive, send):
        async def private_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]
            await send(message)
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["method"] != "POST" or scope["path"] != "/v1/transcriptions":
            return await self.app(scope, receive, private_send)
        if self.active >= self.settings.max_concurrency:
            return await JSONResponse(ServiceError(429, "busy", "The server is busy. Wait and try again.").detail(), 429,
                                      headers={"Retry-After": "3"})(scope, receive, private_send)
        self.active += 1
        try:
            headers = dict(scope.get("headers", []))
            if not headers.get(b"content-type", b"").lower().startswith(b"multipart/form-data;"):
                raise ServiceError(415, "invalid_request", "Use multipart/form-data with video and language fields.")
            limit = self.settings.max_upload_bytes + 64 * 1024
            if b"content-length" in headers:
                try:
                    length = int(headers[b"content-length"])
                    if length < 0:
                        raise ValueError
                except ValueError:
                    raise ServiceError(400, "invalid_request", "Invalid Content-Length header.") from None
                if length > limit:
                    raise ServiceError(413, "upload_too_large", "Video upload exceeds the 20 MiB limit.")

            async def read_body():
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        raise ClientDisconnect()
                    if message["type"] != "http.request":
                        continue
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > limit:
                        raise ServiceError(413, "upload_too_large", "Video upload exceeds the 20 MiB limit.")
                    body.extend(chunk)
                    if not message.get("more_body", False):
                        return bytes(body)
            try:
                body = await asyncio.wait_for(read_body(), self.settings.upload_timeout_seconds)
            except asyncio.TimeoutError:
                raise ServiceError(408, "upload_timeout", "The upload timed out. Check your connection.") from None
            delivered = False

            async def buffered_receive():
                nonlocal delivered, body
                if not delivered:
                    delivered = True
                    message = {"type": "http.request", "body": body, "more_body": False}
                    body = b""
                    return message
                return await receive()
            await self.app(scope, buffered_receive, private_send)
        except ServiceError as exc:
            await JSONResponse(exc.detail(), exc.status)(scope, receive, private_send)
        except ClientDisconnect:
            # The client is gone. Cleanup occurs in inner context managers.
            return
        finally:
            self.active -= 1


async def while_connected(request: Request, awaitable, timeout: float):
    """Cancel and await work when the client leaves; don't leave a GPU orphan."""
    work = asyncio.create_task(awaitable)

    async def disconnected():
        while True:
            message = await request.receive()
            if message["type"] == "http.disconnect":
                return
            await asyncio.sleep(0)

    watcher = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait({work, watcher}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if work in done:
            return work.result()
        if watcher in done:
            raise ServiceError(499, "cancelled", "The client disconnected.")
        raise ServiceError(504, "inference_timeout", "Processing timed out. Try a shorter clip.")
    finally:
        for task in (work, watcher):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)


def create_app(settings: Settings | None = None, backend: Backend | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    backend = backend or MPCBackend(settings)

    @asynccontextmanager
    async def lifespan(app):
        await backend.initialize()
        yield

    app = FastAPI(title="Lip Input visual speech API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(UploadGuard, settings=settings)
    app.state.backend = backend
    app.state.settings = settings

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(exc.detail(), status_code=exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(ServiceError(exc.status_code, "invalid_request", "The request is invalid or the endpoint does not exist.").detail(), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(ServiceError(400, "invalid_request", "Check the request fields.").detail(), 400)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        # Do not return paths, stack traces, uploaded data, or generated text.
        return JSONResponse(ServiceError(500, "internal_error", "Processing failed. Ask the server operator.").detail(), 500)

    @app.get("/v1/capabilities")
    async def capabilities():
        return {
            "languages": [
                {"code": code, "label": label, "available": backend.reason(code) is None,
                 "reason": backend.reason(code)} for code, label in LANGUAGES.items()
            ],
            "model": MODEL_NAME,
            "max_duration_seconds": settings.max_duration_seconds,
        }

    @app.post("/v1/transcriptions")
    async def transcribe(request: Request):
        async with request.form(max_files=1, max_fields=1, max_part_size=1024) as form:
            if set(form) != {"video", "language"} or len(form.multi_items()) != 2:
                raise ServiceError(400, "invalid_request", "Provide exactly one video and one language field.")
            video, language = form["video"], form["language"]
            if not isinstance(video, UploadFile) or not isinstance(language, str):
                raise ServiceError(400, "invalid_request", "video must be a file and language must be text.")
            if language not in LANGUAGES:
                raise ServiceError(400, "unsupported_language", "Choose en (English) or zh (Mandarin Chinese).")
            if video.size is not None and video.size > settings.max_upload_bytes:
                raise ServiceError(413, "upload_too_large", "Video upload exceeds the 20 MiB limit.")
            reason = backend.reason(language)
            if reason:
                raise ServiceError(503, "model_unavailable", reason)
            with tempfile.TemporaryDirectory(prefix="lip-input-", dir=settings.temp_dir) as directory:
                # Random 0700 private directory; never use the client filename.
                source, normalized = Path(directory) / "source.bin", Path(directory) / "silent.mp4"
                size = 0
                with source.open("xb") as destination:
                    source.chmod(0o600)
                    while chunk := await video.read(64 * 1024):
                        size += len(chunk)
                        if size > settings.max_upload_bytes:
                            raise ServiceError(413, "upload_too_large", "Video upload exceeds the 20 MiB limit.")
                        destination.write(chunk)
                if not size:
                    raise ServiceError(415, "invalid_video", "The video file is empty.")

                async def infer():
                    await normalize_video(source, normalized, settings)
                    normalized.chmod(0o600)
                    text = await backend.transcribe(normalized, language)
                    if not isinstance(text, str) or not text.strip() or len(text) > 16_384:
                        raise ServiceError(503, "invalid_model_result", "The model returned an invalid result.")
                    return {"text": text.strip(), "language": language, "model": f"{MODEL_NAME}:{language}"}
                return await while_connected(request, infer(), settings.request_timeout_seconds)

    return app


app = create_app()
