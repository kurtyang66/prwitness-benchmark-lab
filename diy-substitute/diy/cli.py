from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .artifacts import evaluate_artifact, load_result_from_zip
from .core import Decision, State, incomplete, parse_json_bytes, validate_result
from .github_api import GitHubActionsClient, GithubApiError, token_from_env
from .hardened import evaluate_hardened


MAX_INPUT_BYTES = 2 * 1024 * 1024


def _read_bytes(path: str, limit: int) -> bytes:
    file_path = Path(path)
    size = file_path.stat().st_size
    if size > limit:
        raise ValueError("input oversize")
    return file_path.read_bytes()


def _read_json(path: str) -> tuple[dict[str, Any] | None, Decision | None]:
    try:
        data = _read_bytes(path, MAX_INPUT_BYTES)
    except (OSError, ValueError):
        return None, incomplete("INPUT_READ_FAILURE")
    return parse_json_bytes(data)


class OfflineClient:
    def __init__(self, artifacts: list[dict[str, Any]], archive: bytes) -> None:
        self.artifacts = artifacts
        self.archive = archive

    def list_run_artifacts(self, repository: str, run_id: int) -> list[dict[str, Any]]:
        return self.artifacts

    def download_artifact(self, repository: str, artifact_id: int) -> bytes:
        return self.archive


def _emit(decision: Decision, output: str | None) -> int:
    serialized = json.dumps(decision.as_dict(), ensure_ascii=False, sort_keys=True)
    print(serialized)
    if output:
        try:
            Path(output).write_text(serialized + "\n", encoding="utf-8")
        except OSError:
            return 2
    return 0 if decision.state in {State.READY, State.IGNORED} else 2


def _basic(args: argparse.Namespace) -> Decision:
    payload, parse_decision = _read_json(args.input)
    if parse_decision is not None:
        return parse_decision
    return validate_result(payload, expected_head_sha=args.expected_head_sha)


def _artifact(args: argparse.Namespace) -> Decision:
    payload, metadata_decision = _read_json(args.metadata)
    if metadata_decision is not None or payload is None:
        return metadata_decision or incomplete("MALFORMED_ARTIFACT_METADATA")
    try:
        archive = _read_bytes(args.zip, 8 * 1024 * 1024)
    except (OSError, ValueError):
        return incomplete("INPUT_READ_FAILURE")
    return evaluate_artifact(
        archive,
        payload,
        expected_head_sha=args.expected_head_sha,
        expected_base_sha=args.expected_base_sha,
        expected_run_id=args.expected_run_id,
    )


def _hardened(args: argparse.Namespace) -> Decision:
    event, event_decision = _read_json(args.event)
    if event_decision is not None or event is None:
        return event_decision or incomplete("MALFORMED_EVENT")
    repository = args.repository or os.environ.get("GITHUB_REPOSITORY", "")
    if not repository:
        return incomplete("REPOSITORY_REQUIRED")

    if args.metadata and args.zip:
        metadata, metadata_decision = _read_json(args.metadata)
        if metadata_decision is not None or metadata is None:
            return metadata_decision or incomplete("MALFORMED_ARTIFACT_METADATA")
        try:
            archive = _read_bytes(args.zip, 8 * 1024 * 1024)
        except (OSError, ValueError):
            return incomplete("INPUT_READ_FAILURE")
        client: Any = OfflineClient([metadata], archive)
    else:
        try:
            client = GitHubActionsClient(
                token_from_env(args.token_env),
                api_base=args.api_base,
            )
        except GithubApiError:
            return incomplete("API_FAILURE")
    return evaluate_hardened(
        event,
        client,
        repository=repository,
        expected_workflow_name=args.workflow,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Customer-owned PRWitness DIY red-team evaluator")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    basic = subparsers.add_parser("basic", help="validate one local DIY free-result.json")
    basic.add_argument("--input", required=True)
    basic.add_argument("--expected-head-sha")
    basic.add_argument("--output")
    basic.set_defaults(handler=_basic)

    artifact = subparsers.add_parser("artifact", help="validate one GitHub-shaped artifact ZIP")
    artifact.add_argument("--metadata", required=True)
    artifact.add_argument("--zip", required=True)
    artifact.add_argument("--expected-head-sha")
    artifact.add_argument("--expected-base-sha")
    artifact.add_argument("--expected-run-id", type=int)
    artifact.add_argument("--output")
    artifact.set_defaults(handler=_artifact)

    hardened = subparsers.add_parser("hardened", help="evaluate a completed workflow_run fail-closed")
    hardened.add_argument("--event", required=True)
    hardened.add_argument("--repository")
    hardened.add_argument("--workflow", default="PRWitness Free")
    hardened.add_argument("--metadata", help="offline metadata JSON; pair with --zip")
    hardened.add_argument("--zip", help="offline artifact ZIP; pair with --metadata")
    hardened.add_argument("--token-env", default="GH_TOKEN")
    hardened.add_argument("--api-base", default="https://api.github.com")
    hardened.add_argument("--output")
    hardened.set_defaults(handler=_hardened)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.mode == "hardened") and bool(args.metadata) != bool(args.zip):
        parser.error("--metadata and --zip must be provided together")
    decision = args.handler(args)
    return _emit(decision, args.output)


if __name__ == "__main__":
    sys.exit(main())
