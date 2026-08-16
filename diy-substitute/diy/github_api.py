from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from .artifacts import MAX_ARCHIVE_BYTES


class GithubApiError(RuntimeError):
    """Safe-to-display API error without response bodies or credentials."""


def _bounded_read(response: Any, limit: int) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise GithubApiError("API_RESPONSE_OVERSIZE")
    return data


class GitHubActionsClient:
    """Minimal read-only Actions client using Python stdlib only."""

    def __init__(
        self,
        token: str | None,
        *,
        api_base: str = "https://api.github.com",
        timeout: float = 20.0,
        api_version: str = "2022-11-28",
    ) -> None:
        if not token:
            raise GithubApiError("API_TOKEN_MISSING")
        self._token = token
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout
        self._api_version = api_version

    def _request(self, path: str, *, limit: int) -> bytes:
        request = Request(
            f"{self._api_base}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "X-GitHub-Api-Version": self._api_version,
                "User-Agent": "prwitness-diy-redteam/1",
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return _bounded_read(response, limit)
        except HTTPError as exc:
            raise GithubApiError(f"API_HTTP_{exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise GithubApiError("API_NETWORK_FAILURE") from None

    def _request_json(self, path: str) -> dict[str, Any]:
        try:
            value = json.loads(self._request(path, limit=2 * 1024 * 1024).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GithubApiError("API_MALFORMED_JSON") from None
        if not isinstance(value, dict):
            raise GithubApiError("API_MALFORMED_JSON")
        return value

    def list_run_artifacts(self, repository: str, run_id: int) -> list[dict[str, Any]]:
        """Fetch all pages; no top-1 inference is permitted."""

        owner, repo = repository.split("/", 1) if "/" in repository else ("", "")
        if not owner or not repo or not isinstance(run_id, int) or run_id <= 0:
            raise GithubApiError("API_INVALID_TARGET")
        artifacts: list[dict[str, Any]] = []
        page = 1
        per_page = 100
        while page <= 100:
            query = urlencode({"per_page": per_page, "page": page})
            data = self._request_json(
                f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/actions/runs/{run_id}/artifacts?{query}"
            )
            page_items = data.get("artifacts")
            if not isinstance(page_items, list) or any(not isinstance(item, dict) for item in page_items):
                raise GithubApiError("API_MALFORMED_ARTIFACTS")
            artifacts.extend(page_items)
            total = data.get("total_count")
            if isinstance(total, int) and len(artifacts) >= total:
                return artifacts
            if len(page_items) < per_page:
                return artifacts
            page += 1
        raise GithubApiError("API_PAGINATION_LIMIT")

    def download_artifact(self, repository: str, artifact_id: int) -> bytes:
        owner, repo = repository.split("/", 1) if "/" in repository else ("", "")
        if not owner or not repo or not isinstance(artifact_id, int) or artifact_id <= 0:
            raise GithubApiError("API_INVALID_TARGET")
        return self._request(
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}/actions/artifacts/{artifact_id}/zip",
            limit=MAX_ARCHIVE_BYTES,
        )


def token_from_env(name: str = "GH_TOKEN") -> str | None:
    return os.environ.get(name)
