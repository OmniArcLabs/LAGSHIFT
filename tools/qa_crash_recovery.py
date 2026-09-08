"""Exercise an actual abrupt child exit and verify local encrypted recovery."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    with tempfile.TemporaryDirectory(prefix="lagshift-crash-qa-") as folder:
        environment = os.environ.copy()
        environment["APPDATA"] = folder
        environment["LOCALAPPDATA"] = folder
        environment["PYTHONPATH"] = str(root)
        child = (
            "import os; from app.services import crash_service; "
            "crash_service.initialize(True); "
            "crash_service.add_breadcrumb('qa','before abrupt exit'); os._exit(23)"
        )
        result = subprocess.run([sys.executable, "-c", child], env=environment, timeout=15)
        if result.returncode != 23:
            raise SystemExit("Abrupt child scenario did not run")
        old_appdata, old_local = os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")
        try:
            os.environ["APPDATA"] = folder
            os.environ["LOCALAPPDATA"] = folder
            from app.services import crash_service
            if not crash_service.initialize(True):
                raise SystemExit("Unclean session was not detected")
            preview = crash_service.preview_pending()
            if not any(row.get("kind") == "unclean_shutdown" for row in preview["reports"]):
                raise SystemExit("Unclean shutdown report was not queued")
            queue = crash_service._queue_folder()
            (queue / "corrupt.lsc").write_text("not-a-valid-envelope", encoding="ascii")
            preview = crash_service.preview_pending()
            if preview["report_count"] < 1:
                raise SystemExit("A corrupt queue item hid healthy offline reports")
            crash_service.mark_clean_shutdown()
        finally:
            if old_appdata is None: os.environ.pop("APPDATA", None)
            else: os.environ["APPDATA"] = old_appdata
            if old_local is None: os.environ.pop("LOCALAPPDATA", None)
            else: os.environ["LOCALAPPDATA"] = old_local
    print("Crash recovery QA passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
