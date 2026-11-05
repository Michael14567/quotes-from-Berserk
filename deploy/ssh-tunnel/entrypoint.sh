#!/bin/sh
set -eu

umask 077
cp /run/secrets/ssh_private_key /run/ssh/id_ed25519
cp /run/secrets/ssh_known_hosts /run/ssh/known_hosts
chmod 600 /run/ssh/id_ed25519

ssh_pid=''
trap 'if [ -n "$ssh_pid" ]; then kill "$ssh_pid" 2>/dev/null || true; fi; exit 0' TERM INT

while :; do
  ssh -N -T \
  -i /run/ssh/id_ed25519 \
  -o IdentitiesOnly=yes \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=/run/ssh/known_hosts \
  -o ExitOnForwardFailure=yes \
  -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:15432:127.0.0.1:15432 \
  -L 127.0.0.1:19092:127.0.0.1:19092 \
  -L 127.0.0.1:29092:127.0.0.1:29092 \
  -L 127.0.0.1:39092:127.0.0.1:39092 \
  -L 0.0.0.0:18088:127.0.0.1:8088 \
  "${SSH_USER}@${SSH_HOST}" &
  ssh_pid=$!
  wait "$ssh_pid" || true
  ssh_pid=''
  sleep 5 &
  ssh_pid=$!
  wait "$ssh_pid" || true
  ssh_pid=''
done
