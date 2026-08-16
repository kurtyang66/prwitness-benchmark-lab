from __future__ import annotations

import copy
import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from diy.artifacts import MAX_ARCHIVE_BYTES, archive_digest, evaluate_artifact, load_result_from_zip
from diy.core import DIY_SCHEMA, State, validate_result
from diy.github_api import GithubApiError
from diy.hardened import evaluate_hardened


HEAD = "a" * 40
BASE = "b" * 40
REPOSITORY = "acme/example"
RUN_ID = 9001


def result_payload(result: str = "PASS") -> dict[str, object]:
    return {
        "schema": DIY_SCHEMA,
        "flow": "checkout",
        "result": result,
        "run_id": RUN_ID,
        "head_sha": HEAD,
        "base_sha": BASE,
        "artifact_name": f"prwitness-{RUN_ID}",
        "evidence": {"before": True, "after": True, "diff": True},
        "visual_change": "detected",
    }


def make_zip(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def valid_zip(payload: dict[str, object] | None = None) -> bytes:
    body = json.dumps(payload or result_payload(), sort_keys=True).encode("utf-8")
    return make_zip({"free-result.json": body, "report.html": b"<p>evidence</p>"})


def metadata(archive: bytes, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "id": 7001,
        "name": f"prwitness-{RUN_ID}",
        "expired": False,
        "size_in_bytes": len(archive),
        "digest": archive_digest(archive),
        "workflow_run": {"id": RUN_ID, "head_sha": HEAD},
    }
    value.update(overrides)
    return value


def event() -> dict[str, object]:
    return {
        "action": "completed",
        "repository": {"full_name": REPOSITORY},
        "workflow_run": {
            "id": RUN_ID,
            "name": "PRWitness Free",
            "event": "pull_request",
            "status": "completed",
            "conclusion": "success",
            "head_sha": HEAD,
            "head_branch": "attacker-controlled-name",
            "repository": {"full_name": REPOSITORY},
            "head_repository": {"full_name": "fork/example"},
            "pull_requests": [
                {
                    "number": 42,
                    "head": {"sha": HEAD, "repo": {"full_name": "fork/example"}},
                    "base": {"sha": BASE, "repo": {"full_name": REPOSITORY}},
                }
            ],
        },
    }


class FakeClient:
    def __init__(self, artifacts: list[dict[str, object]], archive: bytes, *, fail_list: bool = False, fail_download: bool = False):
        self.artifacts = artifacts
        self.archive = archive
        self.fail_list = fail_list
        self.fail_download = fail_download
        self.downloaded = False

    def list_run_artifacts(self, repository: str, run_id: int) -> list[dict[str, object]]:
        if self.fail_list:
            raise GithubApiError("synthetic API failure")
        return self.artifacts

    def download_artifact(self, repository: str, artifact_id: int) -> bytes:
        if self.fail_download:
            raise GithubApiError("synthetic API failure")
        self.downloaded = True
        return self.archive


def run_case(
    *,
    event_value: dict[str, object] | None = None,
    archive: bytes | None = None,
    artifacts: list[dict[str, object]] | None = None,
    fail_list: bool = False,
    fail_download: bool = False,
) -> tuple[object, FakeClient]:
    archive_value = archive or valid_zip()
    client = FakeClient(
        artifacts if artifacts is not None else [metadata(archive_value)],
        archive_value,
        fail_list=fail_list,
        fail_download=fail_download,
    )
    return evaluate_hardened(event_value or event(), client, repository=REPOSITORY), client


class ScenarioMatrixTests(unittest.TestCase):
    """The local matrix is intentionally adversarial and synthetic."""

    def test_same_scenario_matrix(self) -> None:
        ready_decision, _ = run_case()
        hold_decision, _ = run_case(archive=valid_zip(result_payload("FAIL")))

        incomplete_event = event()
        incomplete_event["workflow_run"] = copy.deepcopy(incomplete_event["workflow_run"])
        incomplete_event["workflow_run"]["status"] = "in_progress"  # type: ignore[index]

        ignored_event = event()
        ignored_event["workflow_run"] = copy.deepcopy(ignored_event["workflow_run"])
        ignored_event["workflow_run"]["event"] = "push"  # type: ignore[index]

        malformed_archive = make_zip({"free-result.json": b"{not-json"})
        missing_archive = valid_zip()

        sha_event = event()
        sha_event["workflow_run"] = copy.deepcopy(sha_event["workflow_run"])
        sha_event["workflow_run"]["head_sha"] = "c" * 40  # type: ignore[index]

        duplicate_archive = valid_zip()
        duplicate_metadata = metadata(duplicate_archive, id=7002)

        unsafe_archive = make_zip({"../escape.txt": b"no execution", "free-result.json": json.dumps(result_payload()).encode()})
        oversize_archive = valid_zip()
        oversize_metadata = metadata(oversize_archive, size_in_bytes=MAX_ARCHIVE_BYTES + 1)

        cases = [
            ("READY", ready_decision, State.READY),
            ("HOLD", hold_decision, State.HOLD),
            ("INCOMPLETE", run_case(event_value=incomplete_event)[0], State.INCOMPLETE),
            ("IGNORED", run_case(event_value=ignored_event)[0], State.IGNORED),
            ("malformed", run_case(archive=malformed_archive)[0], State.INCOMPLETE),
            ("missing", run_case(artifacts=[])[0], State.INCOMPLETE),
            ("SHA conflict", run_case(event_value=sha_event)[0], State.HOLD),
            ("duplicate", run_case(artifacts=[metadata(duplicate_archive), duplicate_metadata])[0], State.HOLD),
            ("zip safety", run_case(archive=unsafe_archive)[0], State.INCOMPLETE),
            ("API failure", run_case(fail_list=True)[0], State.INCOMPLETE),
            ("oversize", run_case(archive=oversize_archive, artifacts=[oversize_metadata])[0], State.INCOMPLETE),
        ]
        for name, decision, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(decision.state, expected)

    def test_basic_variant_is_fail_closed(self) -> None:
        self.assertEqual(validate_result(result_payload()).state, State.READY)
        self.assertEqual(validate_result(result_payload("FAIL")).state, State.HOLD)
        self.assertEqual(validate_result({}).state, State.INCOMPLETE)
        self.assertEqual(validate_result(result_payload(), expected_head_sha="c" * 40).state, State.HOLD)

    def test_artifact_digest_and_size_are_checked(self) -> None:
        archive = valid_zip()
        good = metadata(archive)
        self.assertEqual(evaluate_artifact(archive, good).state, State.READY)
        bad_digest = dict(good, digest="sha256:" + "0" * 64)
        self.assertEqual(evaluate_artifact(archive, bad_digest).reason, "DIGEST_CONFLICT")
        bad_size = dict(good, size_in_bytes=len(archive) + 1)
        self.assertEqual(evaluate_artifact(archive, bad_size).reason, "SIZE_CONFLICT")
        malformed = dict(good, workflow_run={"id": RUN_ID, "head_sha": [HEAD]})
        self.assertEqual(evaluate_artifact(archive, malformed).reason, "MALFORMED_ARTIFACT_METADATA")

    def test_symlink_and_traversal_are_rejected(self) -> None:
        symlink_output = io.BytesIO()
        with zipfile.ZipFile(symlink_output, "w") as archive:
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"free-result.json")
        symlink_result = load_result_from_zip(
            symlink_output.getvalue(),
            metadata=metadata(symlink_output.getvalue()),
        )
        self.assertEqual(symlink_result.decision.reason, "SYMLINK_ZIP_MEMBER")  # type: ignore[union-attr]

        traversal = load_result_from_zip(
            make_zip({"a/../../free-result.json": b"{}"}),
            metadata=metadata(make_zip({"a/../../free-result.json": b"{}"})),
        )
        self.assertEqual(traversal.decision.reason, "UNSAFE_ZIP_MEMBER")  # type: ignore[union-attr]

    def test_artifact_script_is_never_executed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "should-not-exist"
            script = f"from pathlib import Path; Path({str(marker)!r}).write_text('executed')"
            archive = valid_zip()
            archive = make_zip(
                {
                    "free-result.json": json.dumps(result_payload()).encode(),
                    "evil.py": script.encode(),
                }
            )
            decision, _ = run_case(archive=archive)
            self.assertEqual(decision.state, State.READY)
            self.assertFalse(marker.exists())

    def test_download_failure_is_incomplete(self) -> None:
        decision, client = run_case(fail_download=True)
        self.assertEqual(decision.state, State.INCOMPLETE)
        self.assertEqual(decision.reason, "API_FAILURE")
        self.assertFalse(client.downloaded)


class APIShapeTests(unittest.TestCase):
    def test_pagination_is_not_truncated_to_first_page(self) -> None:
        from diy.github_api import GitHubActionsClient

        class StubClient(GitHubActionsClient):
            def __init__(self) -> None:
                self.pages = [
                    {"total_count": 101, "artifacts": [{"id": i} for i in range(100)]},
                    {"total_count": 101, "artifacts": [{"id": 100}]},
                ]
                self.calls = []

            def _request_json(self, path: str) -> dict[str, object]:
                self.calls.append(path)
                return self.pages.pop(0)

        client = StubClient()
        artifacts = client.list_run_artifacts(REPOSITORY, RUN_ID)
        self.assertEqual(len(artifacts), 101)
        self.assertEqual(len(client.calls), 2)


if __name__ == "__main__":
    unittest.main()
