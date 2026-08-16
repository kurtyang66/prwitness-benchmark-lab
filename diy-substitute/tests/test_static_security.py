from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StaticSecurityTests(unittest.TestCase):
    def test_hardened_workflow_uses_only_trusted_default_branch(self) -> None:
        workflow = (ROOT / "workflows" / "diy-hardened.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertNotIn("pull_request_target", workflow)
        self.assertRegex(workflow, r"actions/checkout@[0-9a-f]{40}")
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", workflow)
        self.assertNotIn("github.event.workflow_run.head_sha", workflow.split("actions/checkout", 1)[1].split("- name:", 1)[0])
        self.assertIn("persist-credentials: false", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("actions: write", workflow)
        self.assertNotIn("secrets.", workflow)

    def test_all_workflows_are_read_only_and_do_not_run_artifact_scripts(self) -> None:
        for path in sorted((ROOT / "workflows").glob("*.yml")):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("pull_request_target", text, path.name)
            self.assertRegex(text, r"actions/checkout@[0-9a-f]{40}", path.name)
            self.assertNotIn("contents: write", text, path.name)
            self.assertNotIn("actions: write", text, path.name)
            self.assertNotIn("pull-requests: write", text, path.name)
            self.assertNotRegex(text, r"\b(?:npm|pnpm|yarn)\s+(?:install|run|exec)", path.name)
            self.assertNotIn("secrets.", text, path.name)

    def test_python_implementation_has_no_execution_primitive(self) -> None:
        forbidden = [r"\bsubprocess\b", r"\bos\.system\b", r"\bshell\s*=", r"\beval\s*\(", r"\bexec\s*\("]
        for path in sorted((ROOT / "diy").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden:
                self.assertIsNone(re.search(pattern, text), f"{pattern} in {path.name}")

    def test_hardened_workflow_has_least_permissions_and_no_pr_ref(self) -> None:
        text = (ROOT / "workflows" / "diy-hardened.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("actions: read", text)
        self.assertNotIn("github.event.pull_request.head.sha", text)
        self.assertNotIn("github.event.pull_request.head.ref", text)


if __name__ == "__main__":
    unittest.main()
