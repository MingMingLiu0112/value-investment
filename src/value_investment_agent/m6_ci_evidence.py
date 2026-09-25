"""Read-only GitHub CI evidence for the M6 restore *mechanism* gate."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import shlex
import subprocess
from urllib.request import Request, urlopen
import yaml


_API = "https://api.github.com/repos/MingMingLiu0112/value-investment"
_WORKFLOW = ".github/workflows/core-research-gates.yml"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REPOSITORY_ID = 1353634539


def _get_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/vnd.github+json",
                                    "User-Agent": "value-investment-m6-preflight"})
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise ValueError(f"GitHub API returned HTTP {response.status}")
        return json.load(response)


def _head(root: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                            capture_output=True, encoding="utf-8", check=True)
    head = result.stdout.strip().lower()
    if not _SHA.fullmatch(head):
        raise ValueError("Invalid local commit SHA")
    return head


def verify_restore_ci(root: Path) -> dict:
    """Bind an exact clean commit to a successful GitHub restore test and artifact.

    The result is never evidence of a real source-backup restore or Shadow run.
    """
    head = _head(root)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True,
                            capture_output=True, encoding="utf-8", check=True)
    if status.stdout.strip():
        raise ValueError("CI binding requires a clean worktree")
    workflow = root / _WORKFLOW
    source = workflow.read_bytes()
    parsed = yaml.safe_load(source)
    steps = parsed.get("jobs", {}).get("postgres-integration", {}).get("steps", [])
    test_steps = [step for step in steps
                  if step.get("name") == "Verify disposable PostgreSQL research repository"]
    upload_steps = [step for step in steps
                    if step.get("name") == "Retain synthetic isolated restore evidence"]
    test_command = shlex.split(test_steps[0].get("run", "")) if len(test_steps) == 1 else []
    if (len(test_steps) != 1 or len(upload_steps) != 1
            or test_command[:3] != ["python", "-m", "pytest"]
            or "tests/test_m6_restore_integration.py" not in test_command
            or upload_steps[0].get("with", {}).get("name") != "m6-synthetic-restore-evidence"):
        raise ValueError("Current workflow does not run and retain restore evidence")

    runs = _get_json(f"{_API}/actions/runs?head_sha={head}&per_page=100")
    matches = [run for run in runs.get("workflow_runs", [])
               if run.get("head_sha") == head
               and run.get("repository", {}).get("id") == _REPOSITORY_ID
               and run.get("path") == _WORKFLOW
               and run.get("event") == "push"
               and run.get("head_branch") == "main"
               and run.get("status") == "completed"
               and run.get("run_attempt") == 1
               and run.get("conclusion") == "success"]
    if len(matches) != 1:
        raise ValueError("Expected one successful main-push CI run for exact HEAD")
    run = matches[0]
    run_id = run.get("id")
    if not isinstance(run_id, int) or run_id <= 0:
        raise ValueError("CI run has no stable ID")
    jobs = _get_json(f"{_API}/actions/runs/{run_id}/jobs?per_page=100").get("jobs", [])
    postgres = [job for job in jobs if job.get("name") == "postgres-integration"
                and job.get("run_id") == run_id and job.get("run_attempt") == 1
                and job.get("status") == "completed" and job.get("conclusion") == "success"]
    if len(postgres) != 1:
        raise ValueError("PostgreSQL integration job did not succeed exactly once")
    required_steps = ("Verify disposable PostgreSQL research repository",
                      "Retain synthetic isolated restore evidence")
    for name in required_steps:
        steps = [step for step in postgres[0].get("steps", []) if step.get("name") == name]
        if (len(steps) != 1 or steps[0].get("status") != "completed"
                or steps[0].get("conclusion") != "success"):
            raise ValueError(f"Required CI step did not pass: {name}")
    artifacts = _get_json(f"{_API}/actions/runs/{run_id}/artifacts?per_page=100").get(
        "artifacts", [])
    retained = [item for item in artifacts
                if item.get("name") == "m6-synthetic-restore-evidence"
                and item.get("workflow_run", {}).get("id") == run_id
                and item.get("workflow_run", {}).get("repository_id") == _REPOSITORY_ID
                and item.get("workflow_run", {}).get("head_sha") == head
                and not item.get("expired") and item.get("size_in_bytes", 0) > 0
                and _DIGEST.fullmatch(str(item.get("digest", "")))]
    if len(retained) != 1:
        raise ValueError("Synthetic restore artifact is absent, expired or unbound")
    return {
        "source": "live_github_api",
        "commit_sha": head,
        "workflow_path": _WORKFLOW,
        "workflow_sha256": hashlib.sha256(source).hexdigest(),
        "run_id": run_id,
        "run_attempt": 1,
        "run_url": run.get("html_url"),
        "job_id": postgres[0].get("id"),
        "artifact_id": retained[0].get("id"),
        "artifact_digest": retained[0]["digest"],
        "artifact_size_bytes": retained[0]["size_in_bytes"],
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
