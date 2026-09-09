import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from cutline.config import ConfigurationError, Settings
from cutline.domain import (
    DomainError,
    apply_proposal,
    apply_research,
    edit_cue,
    export_csv,
    export_handoff,
    export_text,
    new_project,
    review_claim,
    signoff_recipes,
    snapshot,
)
from cutline.models import ApplyRequest, CreateProjectRequest, CueUpdateRequest, RevisionRequest
from cutline.providers import FixtureResearchService, LiveResearchService, ProviderError, ResearchService
from cutline.security import SessionContext, SessionManager
from cutline.store import FirestoreProjectStore, MemoryProjectStore, ProjectStore

LOGGER = logging.getLogger("cutline.api")
STATIC_ROOT = Path(__file__).resolve().parent.parent / "static"


def _error(code: str, message: str, status: int, request_id: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(body, status_code=status)


def _store(settings: Settings) -> ProjectStore:
    if settings.data_backend == "firestore":
        return FirestoreProjectStore(settings.google_cloud_project)
    return MemoryProjectStore()


def _research_service(settings: Settings) -> ResearchService:
    if settings.mode == "live":
        return LiveResearchService(settings)
    return FixtureResearchService()


def create_app(
    settings: Settings | None = None,
    store: ProjectStore | None = None,
    research_service: ResearchService | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or _store(settings)
    research_service = research_service or _research_service(settings)
    sessions = SessionManager(settings.session_secret)

    app = FastAPI(
        title="CUTLINE",
        version="1.0.0",
        docs_url="/api/docs" if settings.mode == "fixture" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.mode == "fixture" else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    app.state.settings = settings
    app.state.store = store
    app.state.research_service = research_service
    app.state.sessions = sessions
    app.state.adk_agent = None
    if settings.mode == "live":
        from cutline.agents.claim_research import root_agent

        app.state.adk_agent = root_agent

    @app.middleware("http")
    async def production_boundary(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "")
        if not (8 <= len(request_id) <= 128 and all(ch.isalnum() or ch in "-_." for ch in request_id)):
            request_id = secrets.token_hex(12)
        request.state.request_id = request_id

        if request.method in {"POST", "PATCH", "PUT"}:
            length = request.headers.get("content-length")
            if length:
                try:
                    if int(length) > settings.max_body_bytes:
                        return _error("BODY_TOO_LARGE", "Request body is too large.", 413, request_id)
                except ValueError:
                    return _error("INVALID_CONTENT_LENGTH", "Content-Length is invalid.", 400, request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception("unhandled_request_error", extra={"request_id": request_id})
            response = _error("INTERNAL_ERROR", "The request could not be completed.", 500, request_id)
        duration_ms = round((time.perf_counter() - started) * 1_000)
        LOGGER.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
            "form-action 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self'"
        )
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return _error(exc.code, exc.message, exc.status, request.state.request_id)

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError):
        status = 503 if exc.retryable else 502
        return _error(exc.code, exc.message, status, request.state.request_id)

    @app.exception_handler(ConfigurationError)
    async def configuration_error(request: Request, exc: ConfigurationError):
        return _error("CONFIGURATION_ERROR", str(exc), 503, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        del exc
        return _error("INVALID_INPUT", "Request fields are invalid.", 422, request.state.request_id)

    def session_from_request(request: Request) -> SessionContext:
        token = request.cookies.get(sessions.cookie_name)
        try:
            return sessions.context(token)
        except ValueError as exc:
            raise DomainError(
                "SESSION_REQUIRED", "Refresh the application to start a secure session.", 401
            ) from exc

    def mutating_session(
        request: Request,
        x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> SessionContext:
        context = session_from_request(request)
        if not sessions.csrf_valid(context, x_csrf_token):
            raise DomainError("CSRF_REJECTED", "Refresh the application and try again.", 403)
        origin = request.headers.get("origin")
        if origin:
            parsed = urlparse(origin)
            expected_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
            if parsed.scheme not in {"https", "http"} or parsed.netloc != expected_host:
                raise DomainError("ORIGIN_REJECTED", "Cross-origin changes are not allowed.", 403)
        return context

    ReadSession = Annotated[SessionContext, Depends(session_from_request)]
    WriteSession = Annotated[SessionContext, Depends(mutating_session)]

    @app.get("/health/live", include_in_schema=False)
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def readiness() -> JSONResponse:
        ready = await asyncio.to_thread(store.ready)
        return JSONResponse({"status": "ready" if ready else "not_ready"}, status_code=200 if ready else 503)

    @app.get("/api/capabilities")
    async def capabilities(request: Request, response: Response) -> dict[str, Any]:
        token = request.cookies.get(sessions.cookie_name)
        try:
            context = sessions.context(token)
        except ValueError:
            token, context = sessions.issue()
            response.set_cookie(
                sessions.cookie_name,
                token,
                max_age=settings.project_ttl_hours * 3_600,
                httponly=True,
                secure=settings.cookie_secure,
                samesite="strict",
                path="/",
            )
        return {
            "mode": settings.mode.upper(),
            "live_ready": settings.live_ready,
            "csrf": context.csrf_token,
            "integrations": {
                "google": "Gemini on Vertex AI" if settings.mode == "live" else "Synthetic fixture",
                "partner": "Parallel Search" if settings.mode == "live" else "Synthetic fixture",
            },
            "limits": {
                "body_bytes": settings.max_body_bytes,
                "projects_per_session": settings.max_projects_per_session,
                "retention_hours": settings.project_ttl_hours,
            },
        }

    @app.post("/api/projects", status_code=201)
    async def create_project(body: CreateProjectRequest, session: WriteSession) -> dict[str, Any]:
        del body
        count = await asyncio.to_thread(store.count, session.owner_hash)
        if count >= settings.max_projects_per_session:
            raise DomainError("PROJECT_LIMIT", "Delete an existing project before creating another.", 429)
        project = new_project(session.owner_hash, settings.mode, settings.project_ttl_hours)
        created = await asyncio.to_thread(store.create, project)
        return snapshot(created)

    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str, session: ReadSession) -> dict[str, Any]:
        project = await asyncio.to_thread(store.get, session.owner_hash, project_id)
        return snapshot(project)

    @app.patch("/api/projects/{project_id}/cues/{cue_id}")
    async def update_cue(
        project_id: str,
        cue_id: str,
        body: CueUpdateRequest,
        session: WriteSession,
    ) -> dict[str, Any]:
        updated = await asyncio.to_thread(
            store.mutate,
            session.owner_hash,
            project_id,
            body.expected_revision,
            lambda project: edit_cue(project, cue_id, body.text),
        )
        return snapshot(updated)

    @app.post("/api/projects/{project_id}/cues/{cue_id}/research")
    async def research_cue(
        project_id: str,
        cue_id: str,
        body: RevisionRequest,
        session: WriteSession,
    ) -> dict[str, Any]:
        project = await asyncio.to_thread(store.get, session.owner_hash, project_id)
        if project["revision"] != body.expected_revision:
            raise DomainError("REVISION_CONFLICT", "Reload the current revision and retry.", 409)
        cue = project["cues"].get(cue_id)
        if cue is None:
            raise DomainError("NOT_FOUND", "Cue not found.", 404)
        if cue["kind"] == "QUOTATION":
            raise DomainError("QUOTATION_IMMUTABLE", "Quoted material is not rewritten.", 403)
        outcome = await research_service.research(dict(cue))
        updated = await asyncio.to_thread(
            store.mutate,
            session.owner_hash,
            project_id,
            body.expected_revision,
            lambda current: apply_research(current, cue_id, outcome),
        )
        return snapshot(updated)

    @app.post("/api/projects/{project_id}/cues/{cue_id}/review")
    async def approve_claim(
        project_id: str,
        cue_id: str,
        body: RevisionRequest,
        session: WriteSession,
    ) -> dict[str, Any]:
        updated = await asyncio.to_thread(
            store.mutate,
            session.owner_hash,
            project_id,
            body.expected_revision,
            lambda project: review_claim(project, cue_id),
        )
        return snapshot(updated)

    @app.post("/api/projects/{project_id}/cues/{cue_id}/apply")
    async def apply_claim_proposal(
        project_id: str,
        cue_id: str,
        body: ApplyRequest,
        session: WriteSession,
    ) -> dict[str, Any]:
        updated = await asyncio.to_thread(
            store.mutate,
            session.owner_hash,
            project_id,
            body.expected_revision,
            lambda project: apply_proposal(project, cue_id, body.confirmed),
        )
        return snapshot(updated)

    @app.post("/api/projects/{project_id}/signoff")
    async def signoff(
        project_id: str,
        body: RevisionRequest,
        session: WriteSession,
    ) -> dict[str, Any]:
        updated = await asyncio.to_thread(
            store.mutate,
            session.owner_hash,
            project_id,
            body.expected_revision,
            signoff_recipes,
        )
        return snapshot(updated)

    @app.get("/api/projects/{project_id}/export")
    async def export_project(
        project_id: str,
        session: ReadSession,
        format: Annotated[str, Query(pattern="^(json|csv|text)$")] = "json",
    ) -> Response:
        project = await asyncio.to_thread(store.get, session.owner_hash, project_id)
        handoff = export_handoff(project)
        if format == "csv":
            return PlainTextResponse(
                export_csv(handoff),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="cutline-handoff.csv"'},
            )
        if format == "text":
            return PlainTextResponse(
                export_text(handoff),
                media_type="text/plain",
                headers={"Content-Disposition": 'attachment; filename="cutline-handoff.txt"'},
            )
        return Response(
            json.dumps(handoff, indent=2, ensure_ascii=False),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="cutline-handoff.json"'},
        )

    @app.delete("/api/projects/{project_id}", status_code=204)
    async def delete_project(project_id: str, session: WriteSession) -> Response:
        await asyncio.to_thread(store.delete, session.owner_hash, project_id)
        return Response(status_code=204)

    app.mount("/assets", StaticFiles(directory=STATIC_ROOT), name="assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html", media_type="text/html")

    return app
