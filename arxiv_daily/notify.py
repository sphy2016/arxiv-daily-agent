"""macOS heads-up. Prefers terminal-notifier (click opens the digest); if it is missing or not
allowed to notify, falls back to an AppleScript dialog whose "Open digest" button opens the file."""
import json
import shutil
import subprocess
from pathlib import Path


def _target(open_path: Path | str) -> str:
    return open_path if isinstance(open_path, str) else open_path.resolve().as_uri()


def _terminal_notifier(title: str, message: str, open_path: Path | str | None) -> bool:
    tn = shutil.which("terminal-notifier") or "/opt/homebrew/bin/terminal-notifier"
    if not Path(tn).exists():
        return False
    cmd = [tn, "-title", title, "-message", message, "-group", "arxiv-daily"]
    if open_path:
        cmd += ["-open", _target(open_path)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def notify(title: str, message: str, open_path: Path | str | None = None) -> None:
    if _terminal_notifier(title, message, open_path):
        return
    if open_path is None:
        script = f"display notification {json.dumps(message)} with title {json.dumps(title)} sound name \"Glass\""
        subprocess.run(["osascript", "-e", script], check=False)
        return
    # Banners from osascript can't carry a click action, so use a dialog with a real button.
    # Popen so the pipeline doesn't block; the dialog dismisses itself after 4 hours.
    script = f'''
set r to display dialog {json.dumps(message)} with title {json.dumps(title)} ¬
    buttons {{"Later", "Open digest"}} default button "Open digest" giving up after 14400
if button returned of r is "Open digest" then do shell script "open " & quoted form of {json.dumps(_target(open_path))}
'''
    subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
