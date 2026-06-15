#!/usr/bin/env bash
# graphdb_ready.sh — readiness gate + auto-recovery for the GraphDB container.
#
# Why this exists: on WSL2, the host bind mounts feeding GraphDB (./graphdb-data, and
# previously ./secrets) are bridged into the Docker VM over 9p and can go *stale* after
# a WSL/Docker restart. The engine stays up but its view of the host dir is empty or
# frozen: no license -> restricted mode, or a stale data dir -> the `hetionet` repo is
# not served. Reads still 200; writes and repo-scoped queries 404. A long eval run then
# fails mid-batch for reasons that have nothing to do with the eval.
#
# A container *recreate* (`down`/`up`) — not a restart — re-resolves the mounts. This
# script probes repo readiness and self-heals with exactly one recreate, then re-probes.
# Non-destructive: graphdb-data persists across down/up; only the container is replaced.
#
# Exit 0 = repo is serving and the eval can run. Exit 1 = a real problem the recreate
# could not fix (missing/invalid license, or the repo was never loaded), with guidance.
set -euo pipefail

HEALTH_URL="http://localhost:7200/repositories/hetionet/size"
WAIT_SECS="${WAIT_SECS:-90}"   # per-probe budget; override for slow cold boots

# Poll the repo-size endpoint until it answers 200 or the budget runs out.
poll() {
  local deadline=$(( SECONDS + WAIT_SECS ))
  while (( SECONDS < deadline )); do
    if curl -fsS -o /dev/null "$HEALTH_URL" 2>/dev/null; then return 0; fi
    sleep 3
  done
  return 1
}

echo "[graphdb-ready] ensuring container is up…"
docker compose up -d >/dev/null

echo "[graphdb-ready] waiting for the hetionet repo (up to ${WAIT_SECS}s)…"
if poll; then
  echo "[graphdb-ready] OK — repo serving $(curl -fsS "$HEALTH_URL") triples."
  exit 0
fi

echo "[graphdb-ready] repo not ready — suspected stale mount. Recreating the container…"
docker compose down
docker compose up -d >/dev/null

echo "[graphdb-ready] waiting again (up to ${WAIT_SECS}s)…"
if poll; then
  echo "[graphdb-ready] OK after recreate — repo serving $(curl -fsS "$HEALTH_URL") triples."
  exit 0
fi

# A recreate did not fix it -> not a transient mount glitch. Diagnose the two root causes.
echo "[graphdb-ready] FAILED after recreate. Diagnosing…" >&2
if [ ! -s secrets/graphdb.license ]; then
  echo "  ✗ secrets/graphdb.license is missing or empty — fetch the free license (see secrets/README.md)." >&2
elif docker logs biomedical-rag-graphdb 2>&1 | grep -q "License could not be loaded"; then
  echo "  ✗ GraphDB could not load the license — verify secrets/graphdb.license is the valid file." >&2
else
  echo "  ✗ hetionet repo not found — it may never have been loaded. Run: make ingest-load" >&2
fi
exit 1
