#!/usr/bin/env bash
# Tear down the RunPod pod created by infra/up.sh — a DELETE against the recorded pod
# id. This STOPS per-second billing, so run it promptly after the work is verified.
#
# The pod's local disk is ephemeral: scp any renders off the pod BEFORE running this.
# Reads RUNPOD_API_KEY from the environment or the gitignored .env. Pass a pod id as
# the first argument to override infra/.pod_id.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [ -f "${REPO_ROOT}/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "${REPO_ROOT}/.env"
    set +a
fi

: "${RUNPOD_API_KEY:?set RUNPOD_API_KEY in .env}"

API="https://rest.runpod.io/v1"
STATE_FILE="${SCRIPT_DIR}/.pod_id"

pod_id="${1:-}"
if [ -z "$pod_id" ]; then
    if [ ! -f "$STATE_FILE" ]; then
        echo "no pod id given and ${STATE_FILE} is absent — nothing to tear down" >&2
        exit 1
    fi
    pod_id="$(cat "$STATE_FILE")"
fi

echo "tearing down pod ${pod_id} (stops billing)…"
code=$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "${API}/pods/${pod_id}" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}")

case "$code" in
    2*)
        echo "pod ${pod_id} deleted (HTTP ${code})"
        rm -f "$STATE_FILE"
        ;;
    *)
        echo "delete returned HTTP ${code} — check the RunPod console that pod ${pod_id} is gone" >&2
        exit 1
        ;;
esac
