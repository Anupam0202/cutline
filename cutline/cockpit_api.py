from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, Request

from cutline.api import create_app
from cutline.cockpit import new_custom_project, project_summary
from cutline.domain import DomainError, snapshot
from cutline.models import CreateProjectRequest
from cutline.security import SessionContext


def attach_cockpit_routes(app: FastAPI) -> FastAPI:
    settings = app.state.settings
    store = app.state.store
    sessions = app.state.sessions

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
        x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
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

    @app.get("/api/project-summaries")
    async def list_project_summaries(
        session: SessionContext = Depends(session_from_request),
    ) -> dict[str, Any]:
        projects = await asyncio.to_thread(store.list, session.owner_hash)
        return {"projects": [project_summary(project) for project in projects]}

    @app.post("/api/custom-projects", status_code=201)
    async def create_custom_project(
        body: CreateProjectRequest,
        session: SessionContext = Depends(mutating_session),
    ) -> dict[str, Any]:
        if body.title is None or body.cues is None:
            raise DomainError("INVALID_PROJECT", "Custom projects require a title and cues.", 422)
        count = await asyncio.to_thread(store.count, session.owner_hash)
        if count >= settings.max_projects_per_session:
            raise DomainError("PROJECT_LIMIT", "Delete an existing project before creating another.", 429)
        project = new_custom_project(
            session.owner_hash,
            settings.mode,
            settings.project_ttl_hours,
            body.title,
            [cue.model_dump() for cue in body.cues],
        )
        created = await asyncio.to_thread(store.create, project)
        return snapshot(created)

    return app


def create_cockpit_app() -> FastAPI:
    return attach_cockpit_routes(create_app())
