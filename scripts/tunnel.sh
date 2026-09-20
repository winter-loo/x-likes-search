#!/usr/bin/env bash
set -euo pipefail

SSH_KEY="/home/ldd/pems/deeloo.cn.pem"
REMOTE="ubuntu@124.223.66.219"
REMOTE_PORT="18999"
LOCAL_PORT="8999"

exec /usr/sbin/ssh \
  -i "$SSH_KEY" \
  -o BatchMode=yes \
  -o IdentitiesOnly=yes \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o TCPKeepAlive=yes \
  -o ConnectTimeout=10 \
  -N \
  -R "127.0.0.1:${REMOTE_PORT}:127.0.0.1:${LOCAL_PORT}" \
  "$REMOTE"
