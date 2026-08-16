from __future__ import annotations

from typing import Any, Mapping

from .artifacts import load_result_from_zip, select_artifact
from .core import Decision, hold, ignored, incomplete, validate_result
from .github_api import GithubApiError


def _full_name(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    name = value.get("full_name")
    return name if isinstance(name, str) and name else None


def evaluate_hardened(
    event: object,
    client: Any,
    *,
    repository: str,
    expected_workflow_name: str = "PRWitness Free",
) -> Decision:
    """Evaluate a completed workflow_run without checking out or executing PR code."""

    if not isinstance(event, dict):
        return incomplete("MALFORMED_EVENT")
    if event.get("action") != "completed":
        return ignored("EVENT_NOT_COMPLETED")

    workflow_run = event.get("workflow_run")
    if not isinstance(workflow_run, dict):
        return incomplete("MISSING_WORKFLOW_RUN")
    if workflow_run.get("name") != expected_workflow_name:
        return ignored("WORKFLOW_NOT_TARGET")
    if workflow_run.get("event") != "pull_request":
        return ignored("EVENT_NOT_PULL_REQUEST")
    if workflow_run.get("status") != "completed":
        return incomplete("RUN_NOT_COMPLETED")

    run_id = workflow_run.get("id")
    head_sha = workflow_run.get("head_sha")
    if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
        return incomplete("INVALID_RUN_ID")
    if not isinstance(head_sha, str) or len(head_sha) != 40:
        return incomplete("INVALID_HEAD_SHA")

    event_repository = _full_name(event.get("repository"))
    run_repository = _full_name(workflow_run.get("repository"))
    if event_repository != repository or run_repository != repository:
        return hold("REPOSITORY_CONFLICT")

    pull_requests = workflow_run.get("pull_requests")
    if not isinstance(pull_requests, list) or not pull_requests:
        return incomplete("MISSING_PULL_REQUEST")
    if len(pull_requests) != 1:
        return hold("AMBIGUOUS_PULL_REQUEST", count=len(pull_requests))
    pull_request = pull_requests[0]
    if not isinstance(pull_request, dict):
        return incomplete("MALFORMED_PULL_REQUEST")
    pr_head = pull_request.get("head")
    pr_base = pull_request.get("base")
    pr_head_sha = pr_head.get("sha") if isinstance(pr_head, dict) else None
    pr_base_sha = pr_base.get("sha") if isinstance(pr_base, dict) else None
    if not isinstance(pr_head_sha, str) or not isinstance(pr_base_sha, str):
        return incomplete("MISSING_PR_SHA")
    if pr_head_sha.lower() != head_sha.lower():
        return hold("SHA_CONFLICT")

    run_head_repository = _full_name(workflow_run.get("head_repository"))
    pr_head_repository = _full_name(pr_head.get("repo")) if isinstance(pr_head, dict) else None
    if run_head_repository and pr_head_repository and run_head_repository != pr_head_repository:
        return hold("HEAD_REPOSITORY_CONFLICT")

    conclusion = workflow_run.get("conclusion")
    if conclusion != "success":
        return hold("RUN_CONCLUSION_NOT_SUCCESS", conclusion=conclusion)

    expected_name = f"prwitness-{run_id}"
    try:
        artifacts = client.list_run_artifacts(repository, run_id)
    except (GithubApiError, OSError, TimeoutError):
        return incomplete("API_FAILURE")
    selection = select_artifact(
        artifacts,
        expected_name=expected_name,
        expected_run_id=run_id,
        expected_head_sha=head_sha,
    )
    if selection.decision is not None:
        return selection.decision
    metadata = selection.metadata
    if metadata is None:
        return incomplete("MISSING_ARTIFACT")

    try:
        archive = client.download_artifact(repository, metadata["id"])
    except (GithubApiError, OSError, TimeoutError):
        return incomplete("API_FAILURE")
    loaded = load_result_from_zip(archive, metadata=metadata, require_digest=True)
    if loaded.decision is not None:
        return loaded.decision
    return validate_result(
        loaded.payload,
        expected_head_sha=head_sha,
        expected_base_sha=pr_base_sha,
        expected_run_id=run_id,
        expected_artifact_name=expected_name,
    )
