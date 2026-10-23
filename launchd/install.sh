#!/bin/zsh
# Installs two LaunchAgents:
#   <user>.arxiv-daily         runs the pipeline on weekdays at 06:30 UTC (shown in local time). arXiv's RSS rolls
#                              over at 04:00 UTC (05:00 in winter), so earlier would see yesterday's batch.
#                              A missed run (Mac asleep) fires on wake.
#   <user>.arxiv-daily-server  the local helper behind the digest pages (http://127.0.0.1:8765), always on.
# Options: --no-daily   install only the page server (use this once GitHub Actions does the daily run)
#          --uninstall  remove both
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
DAILY=1; [[ "$1" == "--no-daily" ]] && DAILY=0
# 06:30 UTC expressed in this Mac's local time (fixed at install time; re-run after a DST change)
read H M <<< "$(date -j -f "%Y-%m-%d %H:%M %z" "2026-01-15 06:30 +0000" "+%H %M")"
HOUR=$((10#$H)); MINUTE=$((10#$M))
PYDIR="$(dirname "$(command -v python3)")"
CLAUDEDIR="$(dirname "$(command -v claude 2>/dev/null || echo /usr/local/bin/claude)")"  # only matters for provider = "claude-code"
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"
install_daily() {
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
  <key>StartCalendarInterval</key><array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$ROOT/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/launchd.err</string>
</dict></plist>
PL
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL -> $PLIST (weekdays $(printf '%02d:%02d' $HOUR $MINUTE) local). Test now: launchctl kickstart gui/$(id -u)/$LABEL"
}
remove_daily() {
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"; echo "daily job not installed (--no-daily)"
}
if [[ $DAILY == 1 ]]; then install_daily; else remove_daily; fi

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
