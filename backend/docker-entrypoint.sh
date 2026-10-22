#!/bin/sh
# 1. Put the clips that ship with the image (the common amounts) on the audio disk, without touching
#    any clip that is already there. A free host has no disk, so after every restart the cache starts
#    empty and this is what gives the common amounts a voice again without spending credits.
# 2. Some hosts (Render, for one) mount a persistent disk owned by root. Fix that one folder, then
#    run the app as the unprivileged `zolo` user, so nothing runs as root.
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /data/audio
  cp -n /app/audio_seed/*.mp3 /data/audio/ 2>/dev/null || true
  chown -R zolo:zolo /data/audio 2>/dev/null || true
  exec runuser -u zolo -- "$@"
fi
mkdir -p /data/audio 2>/dev/null || true
cp -n /app/audio_seed/*.mp3 /data/audio/ 2>/dev/null || true
exec "$@"
