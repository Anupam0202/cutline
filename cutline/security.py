from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionContext:
    session_id: str
    owner_hash: str
    csrf_token: str


class SessionManager:
    cookie_name = "cutline_session"

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def _sign(self, purpose: str, value: str) -> str:
        payload = f"{purpose}:{value}".encode("utf-8")
        signature = hmac.new(self._secret, payload, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")

    def issue(self) -> tuple[str, SessionContext]:
        session_id = secrets.token_urlsafe(32)
        token = f"{session_id}.{self._sign('session', session_id)}"
        return token, self.context(token)

    def context(self, token: str | None) -> SessionContext:
        if not token or "." not in token:
            raise ValueError("missing session")
        session_id, signature = token.rsplit(".", 1)
        if not 20 <= len(session_id) <= 128:
            raise ValueError("invalid session")
        expected = self._sign("session", session_id)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid session")
        return SessionContext(
            session_id=session_id,
            owner_hash=self._sign("owner", session_id),
            csrf_token=self._sign("csrf", session_id),
        )

    @staticmethod
    def csrf_valid(context: SessionContext, candidate: str | None) -> bool:
        return bool(candidate) and hmac.compare_digest(context.csrf_token, candidate)
