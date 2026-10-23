"""Heads-up: an ntfy push if $NTFY_TOPIC is set, plus on macOS a notification. Prefers terminal-notifier (click opens the digest); if it is missing or not
allowed to notify, falls back to an AppleScript dialog whose "Open digest" button opens the file."""
import json
import os
import shutil
import subprocess
import sys
import urllib.request
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


def _ntfy(title: str, message: str, open_path: Path | str | None) -> bool:
    """Phone/desktop push through ntfy.sh (or your own server) when $NTFY_TOPIC is set."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return False
    headers = {"Title": title.encode("ascii", "replace").decode()}
    if isinstance(open_path, str) and open_path.startswith("http"):
        headers["Click"] = open_path
    req = urllib.request.Request(f"{os.environ.get('NTFY_SERVER', 'https://ntfy.sh').rstrip('/')}/{topic}",
                                 data=message.encode(), headers=headers, method="POST")
    try:
        urllib.request.urlopen(req, timeout=15).close()
        return True
    except OSError:
        return False


def notify(title: str, message: str, open_path: Path | str | None = None) -> None:
    ntfy = _ntfy(title, message, open_path)
    if ntfy or sys.platform != "darwin":
        return
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
