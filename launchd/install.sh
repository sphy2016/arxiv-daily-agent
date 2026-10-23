#!/bin/zsh
# Installs two LaunchAgents:
#   <user>.arxiv-daily         runs the pipeline daily at 12:00 local time (arXiv RSS updates ~09-11 JST);
#                              a missed run (Mac asleep) fires on wake.
#   <user>.arxiv-daily-server  the local helper behind the digest pages (http://127.0.0.1:8765), always on.
# Uninstall both: ./launchd/install.sh --uninstall
set -e
ROOT="${0:A:h:h}"
LABEL="com.$(whoami).arxiv-daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SLABEL="$LABEL-server"
SPLIST="$HOME/Library/LaunchAgents/$SLABEL.plist"
if [[ "$1" == "--uninstall" ]]; then
  for L in $LABEL $SLABEL; do
    launchctl bootout "gui/$(id -u)/$L" 2>/dev/null || true
    rm -f "$HOME/Library/LaunchAgents/$L.plist"; echo "removed $L"
  done
  exit 0
fi
PYDIR="$(dirname "$(command -v python3)")"
CLAUDEDIR="$(dirname "$(command -v claude 2>/dev/null || echo /usr/local/bin/claude)")"  # only matters for provider = "claude-code"
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$ROOT/run.sh</string><string>run</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$PYDIR:$CLAUDEDIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$ROOT/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/launchd.err</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL -> $PLIST (daily 12:00). Test now: launchctl kickstart gui/$(id -u)/$LABEL"

cat > "$SPLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$SLABEL</string>
  <key>ProgramArguments</key><array><string>$ROOT/run.sh</string><string>serve</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>$PYDIR:$CLAUDEDIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$ROOT/logs/server.out</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/server.err</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$SLABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$SPLIST"
echo "installed $SLABEL -> http://127.0.0.1:8765"
