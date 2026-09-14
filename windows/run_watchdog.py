"""Task Scheduler entry: log start/end, then run the watchdog."""
from __future__ import annotations

import runpy
import sys
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "logs" / "task-run.log"
SCRIPT = ROOT / "oci_workflow_watchdog.py"


def _log(message: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(f"{stamp} {message}\n")


def main() -> int:
    _log(f"start python={sys.executable}")
    try:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    except SystemExit as exc:
        code = exc.code
        if code is None:
            code = 0
        if not isinstance(code, int):
            _log(f"sys.exit {code!r}")
            return 1
        _log(f"exit {code}")
        return code
    except Exception:
        _log(traceback.format_exc())
        return 1
    _log("exit 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
