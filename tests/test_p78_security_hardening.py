"""P78 — hardening sin RBAC avanzado."""

import re
from pathlib import Path


def test_gitignore_blocks_env_not_examples():
    gi = (Path(__file__).resolve().parent.parent / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gi
    assert "!.env.example" in gi
    assert "!.env.staging.example" in gi


def test_env_examples_no_real_telegram_tokens():
    root = Path(__file__).resolve().parent.parent
    for name in (".env.example", ".env.staging.example"):
        text = (root / name).read_text(encoding="utf-8")
        assert "your_telegram_bot_token_here" in text
        assert not re.search(r"\d{8,}:[A-Za-z0-9_-]{30,}", text)


def test_p78_doc_mentions_no_advanced_rbac():
    doc = Path(__file__).resolve().parent.parent / "docs" / "P78_SECURITY_HARDENING.md"
    text = doc.read_text(encoding="utf-8").lower()
    assert "rbac" in text
    assert "avanzad" in text or "matriz" in text
