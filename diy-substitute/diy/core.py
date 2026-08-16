from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


DIY_SCHEMA = "prwitness-diy-free-result/v1"
MAX_RESULT_BYTES = 256 * 1024
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
ARTIFACT_RE = re.compile(r"^prwitness-[1-9][0-9]*$")


class State(str, Enum):
    READY = "READY"
    HOLD = "HOLD"
    INCOMPLETE = "INCOMPLETE"
    IGNORED = "IGNORED"


@dataclass(frozen=True)
class Decision:
    state: State
    reason: str
    details: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "details": dict(self.details),
        }


def ready(reason: str = "PASS_EVIDENCE", **details: Any) -> Decision:
    return Decision(State.READY, reason, details)


def hold(reason: str, **details: Any) -> Decision:
    return Decision(State.HOLD, reason, details)


def incomplete(reason: str, **details: Any) -> Decision:
    return Decision(State.INCOMPLETE, reason, details)


def ignored(reason: str, **details: Any) -> Decision:
    return Decision(State.IGNORED, reason, details)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA_RE.fullmatch(value) is not None


def parse_json_bytes(data: bytes) -> tuple[dict[str, Any] | None, Decision | None]:
    """Parse only bounded JSON; callers never execute content from an artifact."""

    if not isinstance(data, bytes):
        return None, incomplete("MALFORMED_JSON", detail="result is not bytes")
    if len(data) > MAX_RESULT_BYTES:
        return None, incomplete("OVERSIZE_RESULT", bytes=len(data))
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, incomplete("MALFORMED_JSON")
    if not isinstance(value, dict):
        return None, incomplete("MALFORMED_RESULT", detail="top-level JSON is not an object")
    return value, None


def validate_result(
    payload: object,
    *,
    expected_head_sha: str | None = None,
    expected_base_sha: str | None = None,
    expected_run_id: int | None = None,
    expected_artifact_name: str | None = None,
) -> Decision:
    """Validate the explicit DIY adapter contract and derive a fail-closed state.

    The public Free Action documentation names ``free-result.json`` and its
    PASS/FAIL result, but does not publish a complete JSON schema.  This
    function therefore validates a deliberately small customer-owned schema
    instead of pretending to know a private or undocumented implementation.
    """

    if not isinstance(payload, dict):
        return incomplete("MALFORMED_RESULT")

    required = ("schema", "flow", "result", "run_id", "head_sha", "base_sha", "artifact_name", "evidence")
    missing = [key for key in required if key not in payload]
    if missing:
        return incomplete("MISSING_RESULT_FIELD", fields=missing)

    if payload.get("schema") != DIY_SCHEMA:
        return incomplete("INVALID_SCHEMA")

    flow = payload.get("flow")
    if not isinstance(flow, str) or not flow.strip() or len(flow) > 200:
        return incomplete("INVALID_FLOW")

    result = payload.get("result")
    if result not in {"PASS", "FAIL"}:
        return incomplete("INVALID_RESULT")

    run_id = payload.get("run_id")
    if not _is_int(run_id) or run_id <= 0:
        return incomplete("INVALID_RUN_ID")

    head_sha = payload.get("head_sha")
    base_sha = payload.get("base_sha")
    if not _is_sha(head_sha) or not _is_sha(base_sha):
        return incomplete("INVALID_SHA")

    artifact_name = payload.get("artifact_name")
    if not isinstance(artifact_name, str) or ARTIFACT_RE.fullmatch(artifact_name) is None:
        return incomplete("INVALID_ARTIFACT_NAME")
    if artifact_name != f"prwitness-{run_id}":
        return hold("ARTIFACT_NAME_CONFLICT")

    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        return incomplete("MALFORMED_EVIDENCE")
    missing_evidence = [key for key in ("before", "after", "diff") if key not in evidence]
    if missing_evidence:
        return incomplete("MISSING_EVIDENCE", fields=missing_evidence)
    if any(evidence.get(key) is not True for key in ("before", "after", "diff")):
        return incomplete("EVIDENCE_INCOMPLETE")

    if expected_head_sha is not None and head_sha.lower() != expected_head_sha.lower():
        return hold("SHA_CONFLICT", expected=expected_head_sha, observed=head_sha)
    if expected_base_sha is not None and base_sha.lower() != expected_base_sha.lower():
        return hold("BASE_SHA_CONFLICT", expected=expected_base_sha, observed=base_sha)
    if expected_run_id is not None and run_id != expected_run_id:
        return hold("RUN_ID_CONFLICT", expected=expected_run_id, observed=run_id)
    if expected_artifact_name is not None and artifact_name != expected_artifact_name:
        return hold("ARTIFACT_NAME_CONFLICT")

    details = {
        "flow": flow,
        "run_id": run_id,
        "head_sha": head_sha,
        "base_sha": base_sha,
        "visual_change": payload.get("visual_change", "unspecified"),
    }
    if result == "FAIL":
        return hold("PROOF_FAILED", **details)
    return ready(**details)
