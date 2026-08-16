from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]


def loc(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            count += 1
    return count


def paths(pattern: str) -> list[Path]:
    return sorted(path for path in ROOT.glob(pattern) if path.is_file())


def action_refs(workflow_files: Iterable[Path]) -> list[str]:
    refs: set[str] = set()
    for path in workflow_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.search(r"\buses:\s*([^\s#]+)", line)
            if match:
                refs.add(match.group(1))
    return sorted(refs)


def permission_summary(workflow_files: Iterable[Path]) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {}
    for path in workflow_files:
        values: list[str] = []
        in_permissions = False
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("permissions:"):
                in_permissions = True
                continue
            if in_permissions and line and not line.startswith(" "):
                in_permissions = False
            if in_permissions and line.strip() and ":" in line:
                values.append(line.strip())
        summary[str(path.relative_to(ROOT))] = values
    return summary


def build_metrics() -> dict[str, object]:
    implementation = [path for path in paths("diy/*.py") if path.name != "metrics.py"]
    metric_tool = paths("diy/metrics.py")
    workflow_files = paths("workflows/*.yml")
    test_files = paths("tests/*.py")
    docs = paths("*.md") + paths("fixtures/*.md")
    negative_cases = [
        "malformed",
        "missing",
        "SHA conflict",
        "duplicate",
        "zip safety",
        "API failure",
        "oversize",
        "digest conflict",
        "size conflict",
        "artifact script never executed",
        "pagination truncation",
    ]
    return {
        "loc": {
            "source": sum(loc(path) for path in implementation),
            "source_files": {str(path.relative_to(ROOT)): loc(path) for path in implementation},
            "metrics_tool": sum(loc(path) for path in metric_tool),
            "workflows": sum(loc(path) for path in workflow_files),
            "workflow_files": {str(path.relative_to(ROOT)): loc(path) for path in workflow_files},
            "tests": sum(loc(path) for path in test_files),
            "test_files": {str(path.relative_to(ROOT)): loc(path) for path in test_files},
            "documentation": sum(loc(path) for path in docs),
        },
        "dependencies": {
            "runtime_third_party": [],
            "test_third_party": [],
            "stdlib_modules": ["argparse", "dataclasses", "enum", "hashlib", "io", "json", "pathlib", "re", "stat", "typing", "urllib", "zipfile"],
            "external_actions": action_refs(workflow_files),
            "setup": ["Python 3.11+", "No package installation", "No Node/pnpm/Playwright/FFmpeg required by evaluator"],
        },
        "permissions": permission_summary(workflow_files),
        "negative_cases": negative_cases,
        "maintenance_surface": {
            "implementation_files": len(implementation),
            "workflow_files": len(workflow_files),
            "test_files": len(test_files),
            "documentation_files": len(docs),
            "external_action_refs": len(action_refs(workflow_files)),
            "github_api_endpoints": 2,
            "state_values": ["READY", "HOLD", "INCOMPLETE", "IGNORED"],
            "configuration_knobs": ["expected_workflow_name", "repository", "API base URL", "artifact/archive/result size limits"],
            "duplicated_validation_logic": "none between local evaluator and workflow; workflow invokes trusted default-branch evaluator",
            "unverified_external_dependencies": ["customer producer emits compatible artifact", "GitHub token/repository policy", "hosted runner Python availability"],
        },
        "measurement_definition": {
            "loc": "nonblank, non-comment physical lines; YAML counted as workflow LOC",
            "source_scope": "diy/*.py excluding diy/metrics.py",
            "test_scope": "tests/*.py",
            "workflow_scope": "workflows/*.yml",
            "dependencies": "runtime/test packages plus workflow action references; no network install performed",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure DIY red-team engineering surface")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a short human summary")
    args = parser.parse_args()
    value = build_metrics()
    if args.json:
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        loc_values = value["loc"]
        print(f"source_loc={loc_values['source']}")
        print(f"workflow_loc={loc_values['workflows']}")
        print(f"test_loc={loc_values['tests']}")
        print(f"negative_cases={len(value['negative_cases'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
