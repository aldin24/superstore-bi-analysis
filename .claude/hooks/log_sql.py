#!/usr/bin/env python3
"""
PostToolUse hook — appends every mcp__postgres__ call to logs/agent_audit.log.
Reads the Claude Code hook payload from stdin (JSON).
Always exits 0; never writes to stdout.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

def main() -> None:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"raw": raw}

    project_dir = Path(
        os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).parent.parent.parent)
    )
    log_path = project_dir / "logs" / "agent_audit.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "tool_name":     payload.get("tool_name", ""),
        "tool_input":    payload.get("tool_input", {}),
        "tool_response": payload.get("tool_response", {}),
    }

    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # never surface errors to Claude Code; hook must be silent
    sys.exit(0)
