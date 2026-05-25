"""P72 — validación del workflow de deploy staging."""

from __future__ import annotations

import re
from pathlib import Path


def _workflow_text() -> str:
    path = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "deploy-staging.yml"
    return path.read_text(encoding="utf-8")


def test_workflow_dispatch_only_manual():
    text = _workflow_text()
    assert "workflow_dispatch:" in text
    assert "push:" not in text.split("on:")[1].split("jobs:")[0]


def test_workflow_uses_github_secrets_not_hardcoded():
    text = _workflow_text()
    assert "secrets.STAGING_SSH_HOST" in text
    assert "secrets.STAGING_URL" in text
    assert "ci_validate_staging_deploy.sh" in text
    assert "gh_deploy_staging_remote.sh" in text
    assert "smoke_health.sh" in text
    # Sin tokens Telegram reales ni patrones BotFather
    assert not re.search(r"\d{8,}:[A-Za-z0-9_-]{30,}", text)


def test_workflow_runs_pytest_before_deploy():
    text = _workflow_text()
    assert "pytest -q" in text
    deploy_pos = text.find("deploy-staging:")
    test_pos = text.find("validate-and-test:")
    assert test_pos < deploy_pos
    assert "needs: validate-and-test" in text


def test_validate_staging_secrets_script_exists():
    script = Path(__file__).resolve().parent.parent / "scripts" / "ci_validate_staging_deploy.sh"
    assert script.is_file()


def test_p72_doc_exists():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P72_STAGING_DEPLOY_AUTOMATION.md"
    assert doc.is_file()
    content = doc.read_text(encoding="utf-8")
    assert "STAGING_SSH_HOST" in content
    assert "workflow_dispatch" in content
    assert "rollback" in content.lower()
