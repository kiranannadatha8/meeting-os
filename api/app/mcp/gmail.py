"""Gmail MCP tool — creates draft follow-up emails.

This is a *draft-only* wrapper: we never call `users.messages.send`.
Phase 3's approval flow is "create the draft, let the user review it in
Gmail, they click Send." Keeps MeetingOS from ever surprising a user
with a sent message.

OAuth flow:
1. User grants offline access in NextAuth → we store `refresh_token`
   encrypted in `integrations.encrypted_key`.
2. Each `create_draft` call refreshes → access_token (stateless — no
   caching, since access tokens expire in ~1h and drafts are rare).
3. POST the RFC 2822 MIME message base64url-encoded.

Refs:
- https://developers.google.com/identity/protocols/oauth2/web-server#offline
- https://developers.google.com/gmail/api/reference/rest/v1/users.drafts/create
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DRAFTS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"


class GmailError(Exception):
    """Transport or 5xx-style failure — worth retrying."""


class GmailAuthError(GmailError):
    """Refresh token is no good or Gmail returned 401. The UI should
    prompt the user to reconnect Gmail."""


@dataclass(frozen=True)
class DraftResult:
    draft_id: str
    message_id: str
    thread_id: str


class GmailClient:
    def __init__(
        self,
        *,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        http: httpx.Client | None = None,
    ) -> None:
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http or httpx.Client(timeout=15.0)

    def create_draft(
        self,
        *,
        to: list[str],
        subject: str,
        body_text: str,
    ) -> DraftResult:
        if not to:
            raise ValueError("`to` must contain at least one recipient")

        access_token = self._refresh_access_token()
        raw = self._build_raw_message(to=to, subject=subject, body_text=body_text)

        try:
            response = self._http.post(
                _DRAFTS_URL,
                json={"message": {"raw": raw}},
                headers={"authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            raise GmailError(f"Gmail request failed: {exc}") from exc

        if response.status_code == 401:
            raise GmailAuthError("Gmail rejected the access token (401)")
        if response.status_code >= 400:
            raise GmailError(
                f"Gmail returned HTTP {response.status_code}: {response.text[:200]}"
            )

        body = response.json()
        message = body.get("message") or {}
        return DraftResult(
            draft_id=body["id"],
            message_id=message.get("id", ""),
            thread_id=message.get("threadId", ""),
        )

    def _refresh_access_token(self) -> str:
        try:
            response = self._http.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
        except httpx.HTTPError as exc:
            raise GmailError(f"Token refresh failed: {exc}") from exc

        if response.status_code == 400:
            # Google returns 400 w/ `invalid_grant` for revoked/expired
            # refresh tokens — treat as auth error, not transport.
            raise GmailAuthError(
                f"Refresh token rejected by Google: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise GmailError(
                f"Token refresh returned HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

        return response.json()["access_token"]

    @staticmethod
    def _build_raw_message(
        *,
        to: list[str],
        subject: str,
        body_text: str,
    ) -> str:
        msg = EmailMessage()
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        msg.set_content(body_text)
        # Gmail wants base64url with `=` padding stripped per RFC 4648 §5.
        return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")
