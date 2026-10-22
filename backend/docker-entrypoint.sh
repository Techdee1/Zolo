#!/bin/sh
# Some hosts (Render, for one) mount a persistent disk owned by root. Fix that one folder, then run
# the app as the unprivileged `zolo` user, so the audio cache is writable and nothing runs as root.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data/audio
  chown zolo:zolo /data/audio 2>/dev/null || true
  exec runuser -u zolo -- "$@"
fi
exec "$@"
