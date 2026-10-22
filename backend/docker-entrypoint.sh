#!/bin/sh
# 1. Put the clips that ship with the image (the clip set) into the audio cache folder, without touching
#    any clip that is already there. Hosts with no persistent disk (Heroku, Render free) start with an
#    empty cache after every restart, and this is what gives the set a voice again without spending
#    credits. The folder is AUDIO_CACHE_DIR (default /data/audio; Heroku uses /tmp/audio).
# 2. Some hosts (Render, for one) mount a persistent disk owned by root. If we start as root, fix that one
#    folder and run the app as the unprivileged `zolo` user. Hosts that already run us as a non-root user
#    (Heroku) skip this.
set -e
AUDIO_DIR="${AUDIO_CACHE_DIR:-/data/audio}"
if [ "$(id -u)" = "0" ]; then
  mkdir -p "$AUDIO_DIR"
  cp -n /app/audio_seed/*.mp3 "$AUDIO_DIR"/ 2>/dev/null || true
  chown -R zolo:zolo "$AUDIO_DIR" 2>/dev/null || true
  exec runuser -u zolo -- "$@"
fi
mkdir -p "$AUDIO_DIR" 2>/dev/null || true
cp -n /app/audio_seed/*.mp3 "$AUDIO_DIR"/ 2>/dev/null || true
exec "$@"
