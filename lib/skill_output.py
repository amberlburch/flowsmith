"""
Structured skill output and execution logging for Claude Code skills.

Usage from any skill script:
    from skill_output import SkillRun

    run = SkillRun("morning-coffee")
    run.log("Scanning Slack for @mentions")
    run.log("Found 3 messages", level="info")
    run.set_result({"actions": [...], "fyi": [...]})
    run.complete()  # writes result + log files

Or for simple one-shot results (no logging needed):
    from skill_output import save_result
    save_result("blueprint", {"client": "Acme", "proposal_url": "..."})
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

AWST = timezone(timedelta(hours=8))
RESULTS_DIR = Path.home() / ".claude" / "results"
LOGS_DIR = Path.home() / ".claude" / "logs"


def _timestamp() -> str:
    """Current time in AWST as ISO string."""
    return datetime.now(AWST).isoformat(timespec="seconds")


def _date_prefix() -> str:
    """YYMMDD-HHMM for file naming."""
    return datetime.now(AWST).strftime("%y%m%d-%H%M")


def save_result(skill_name: str, data: dict[str, Any]) -> Path:
    """Write a skill result to ~/.claude/results/{skill}/{timestamp}.json"""
    skill_dir = RESULTS_DIR / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "skill": skill_name,
        "timestamp": _timestamp(),
        "data": data,
    }

    filepath = skill_dir / f"{_date_prefix()}.json"
    filepath.write_text(json.dumps(result, indent=2, default=str))
    return filepath


class SkillRun:
    """Tracks a single skill execution with structured output and logging."""

    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        self.started_at = _timestamp()
        self.entries: list[dict[str, str]] = []
        self.costs: list[dict[str, Any]] = []
        self.result: dict[str, Any] | None = None
        self.status = "running"

    def log(self, message: str, level: str = "info") -> None:
        """Append a log entry. Levels: debug, info, warn, error."""
        self.entries.append({
            "time": _timestamp(),
            "level": level,
            "message": message,
        })

    def record_cost(
        self,
        provider: str,
        model: str,
        usd: float,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        units: float | None = None,
        unit_kind: str | None = None,
        note: str | None = None,
    ) -> None:
        """Record a cost event for this run. Read by lib/cost_rollup.py."""
        entry: dict[str, Any] = {
            "time": _timestamp(),
            "provider": provider,
            "model": model,
            "usd": round(float(usd), 6),
        }
        if input_tokens is not None:
            entry["input_tokens"] = int(input_tokens)
        if output_tokens is not None:
            entry["output_tokens"] = int(output_tokens)
        if units is not None:
            entry["units"] = float(units)
        if unit_kind is not None:
            entry["unit_kind"] = unit_kind
        if note is not None:
            entry["note"] = note
        self.costs.append(entry)

    def set_result(self, data: dict[str, Any]) -> None:
        """Set the structured result data for this run."""
        self.result = data

    def fail(self, error: str) -> Path:
        """Mark run as failed and write log."""
        self.status = "failed"
        self.log(error, level="error")
        return self._write()

    def complete(self) -> Path:
        """Mark run as complete. Writes result + log files. Returns log path."""
        self.status = "completed"

        if self.result is not None:
            save_result(self.skill_name, self.result)

        return self._write()

    def _write(self) -> Path:
        """Write the execution log to ~/.claude/logs/{skill}/{timestamp}.json"""
        log_dir = LOGS_DIR / self.skill_name
        log_dir.mkdir(parents=True, exist_ok=True)

        completed_at = _timestamp()
        cost_total = round(sum(c["usd"] for c in self.costs), 6)
        log_data = {
            "skill": self.skill_name,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": completed_at,
            "entries": self.entries,
            "entry_count": len(self.entries),
            "costs": self.costs,
            "cost_total_usd": cost_total,
        }

        filepath = log_dir / f"{_date_prefix()}.json"
        filepath.write_text(json.dumps(log_data, indent=2, default=str))

        self._emit_span(completed_at, cost_total)
        return filepath

    def _emit_span(self, completed_at: str, cost_total: float) -> None:
        """Emit one OTel-GenAI span summarising the run. Best-effort: a telemetry
        failure (or a missing trace module) must never break a skill run."""
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).parent))
            from trace import emit_span

            in_tok = sum(int(c.get("input_tokens") or 0) for c in self.costs) or None
            out_tok = sum(int(c.get("output_tokens") or 0) for c in self.costs) or None
            model = next((c.get("model") for c in self.costs if c.get("model")), None)
            provider = next((c.get("provider") for c in self.costs if c.get("provider")), None)
            try:
                start = datetime.fromisoformat(self.started_at)
                end = datetime.fromisoformat(completed_at)
                duration_ms = int((end - start).total_seconds() * 1000)
            except (ValueError, TypeError):
                duration_ms = None

            emit_span(
                f"skill.{self.skill_name}",
                op="skill",
                skill=self.skill_name,
                provider=provider,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                cost_usd=cost_total or None,
                duration_ms=duration_ms,
                status="ok" if self.status == "completed" else "error",
            )
        except Exception:  # noqa: BLE001
            pass


def latest_result(skill_name: str) -> dict[str, Any] | None:
    """Read the most recent result for a skill. Returns None if no results exist or all are unreadable."""
    skill_dir = RESULTS_DIR / skill_name
    if not skill_dir.exists():
        return None

    for f in sorted(skill_dir.glob("*.json"), reverse=True):
        try:
            return json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
    return None


def recent_logs(skill_name: str, count: int = 5) -> list[dict[str, Any]]:
    """Read the N most recent execution logs for a skill. Skips unreadable files."""
    log_dir = LOGS_DIR / skill_name
    if not log_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for f in sorted(log_dir.glob("*.json"), reverse=True)[:count]:
        try:
            results.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return results
