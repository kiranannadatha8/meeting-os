"""Linear MCP tool — creates Linear issues from action items.

We wrap Linear's GraphQL API directly. One `issueCreate` mutation per
action item gives us per-item error granularity: a single broken item
shouldn't poison the whole dispatch batch.

Linear accepts the personal API key *directly* in the Authorization
header (no "Bearer" prefix) — see
https://developers.linear.app/docs/graphql/working-with-the-graphql-api
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

_GRAPHQL_PATH = "/graphql"
_DEFAULT_BASE_URL = "https://api.linear.app"

_CREATE_ISSUE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue {
      id
      identifier
      url
    }
  }
}
""".strip()


class LinearError(Exception):
    """Raised when the Linear API call fails in a way that makes the
    whole batch unsafe to continue (transport failures, unexpected
    responses). Per-item logical errors land in ``DispatchResult.errors``
    instead."""


class LinearAuthError(LinearError):
    """401 from Linear — the API key is wrong or revoked. Abort the
    batch rather than hammering with a bad credential."""


@dataclass(frozen=True)
class ActionItemInput:
    title: str
    description: str | None = None


@dataclass(frozen=True)
class LinearIssue:
    id: str
    identifier: str
    url: str


@dataclass(frozen=True)
class DispatchError:
    action_item_title: str
    message: str


@dataclass(frozen=True)
class DispatchResult:
    created: list[LinearIssue] = field(default_factory=list)
    errors: list[DispatchError] = field(default_factory=list)


class LinearClient:
    def __init__(
        self,
        api_key: str,
        http: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._http = http or httpx.Client(base_url=_DEFAULT_BASE_URL, timeout=15.0)

    def create_issues(
        self,
        items: list[ActionItemInput],
        *,
        team_id: str,
    ) -> DispatchResult:
        created: list[LinearIssue] = []
        errors: list[DispatchError] = []

        for item in items:
            issue, error = self._create_one(item, team_id=team_id)
            if issue is not None:
                created.append(issue)
            if error is not None:
                errors.append(error)

        return DispatchResult(created=created, errors=errors)

    def _create_one(
        self,
        item: ActionItemInput,
        *,
        team_id: str,
    ) -> tuple[LinearIssue | None, DispatchError | None]:
        payload = {
            "query": _CREATE_ISSUE_MUTATION,
            "variables": {
                "input": {
                    "teamId": team_id,
                    "title": item.title,
                    "description": item.description,
                }
            },
        }
        headers = {
            "authorization": self._api_key,
            "content-type": "application/json",
        }

        try:
            response = self._http.post(_GRAPHQL_PATH, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LinearError(f"Linear request failed: {exc}") from exc

        if response.status_code == 401:
            raise LinearAuthError("Linear rejected the API key (401)")

        if response.status_code >= 400:
            raise LinearError(
                f"Linear returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise LinearError(f"Linear returned non-JSON: {exc}") from exc

        graphql_errors = body.get("errors") or []
        data = body.get("data") or {}
        issue_create = data.get("issueCreate") or {}

        if graphql_errors or not issue_create.get("success"):
            message = (
                graphql_errors[0]["message"]
                if graphql_errors
                else "Linear reported success: false"
            )
            return None, DispatchError(action_item_title=item.title, message=message)

        issue_blob = issue_create.get("issue") or {}
        issue = LinearIssue(
            id=issue_blob["id"],
            identifier=issue_blob["identifier"],
            url=issue_blob["url"],
        )
        return issue, None
