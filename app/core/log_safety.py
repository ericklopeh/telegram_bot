"""P69 — sanitización de logs (sin secretos, tokens ni RFC completos)."""

from __future__ import annotations

import logging
import re

# Patrones sensibles (no loguear valores completos)
_TOKEN_RE = re.compile(
    r"(?i)(token|password|secret|api[_-]?key|authorization)\s*[=:]\s*\S+"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9._\-]+", re.I)
_RFC_RE = re.compile(r"\bRFC[A-Z&]{3,4}\d{10,13}\b", re.I)
_RFC_PLAIN_RE = re.compile(r"\b[A-Z&]{3,4}\d{10,13}\b")


class SecretScrubFilter(logging.Filter):
    """Redacta fragmentos sensibles antes de escribir handlers."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            msg = record.msg
        else:
            try:
                msg = record.getMessage()
            except Exception:
                return True
        scrubbed = self.scrub_text(msg)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = ()
        return True

    @staticmethod
    def scrub_text(text: str) -> str:
        if not text:
            return text
        def _redact(m: re.Match[str]) -> str:
            sep = "=" if "=" in m.group(0) else ":"
            key = m.group(0).split(sep)[0]
            return f"{key}{sep}***"

        out = _TOKEN_RE.sub(_redact, text)
        out = _BEARER_RE.sub("Bearer ***", out)
        out = _RFC_RE.sub("RFC***", out)
        out = _RFC_PLAIN_RE.sub(lambda m: m.group(0)[:4] + "***", out)
        return out
