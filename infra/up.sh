#!/usr/bin/env bash
# Provision an on-demand RunPod GPU pod (RTX PRO 4500 Blackwell) with the models
# network volume attached, inject our SSH public key, then print the SSH + tunnel
# commands. generate.py / tuning drives ComfyUI over an SSH tunnel to localhost:8188.
#
# Why SSH (not the HTTP proxy): these SECURE + network-volume pods sit behind RunPod's
# Cloudflare proxy, which 403s API POSTs to /prompt. An SSH tunnel bypasses it entirely.
# (This mirrors the sibling isekai project's proven infra.)
#
# ⚠️ METERED: creating a pod starts PER-SECOND billing until infra/down.sh tears it
# down. Reads RUNPOD_API_KEY + RUNPOD_NETWORK_VOLUME_ID (+ optional overrides) from .env.
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
: "${RUNPOD_NETWORK_VOLUME_ID:?set RUNPOD_NETWORK_VOLUME_ID in .env (create the volume once, then reuse it)}"

API="https://rest.runpod.io/v1"
POD_NAME="${RUNPOD_POD_NAME:-synthetic-portraits}"
IMAGE="${RUNPOD_IMAGE:-ghcr.io/alxb1t/synthetic_portraits:latest}"
GPU_TYPE="${RUNPOD_GPU_TYPE:-NVIDIA RTX PRO 4500 Blackwell}"
CONTAINER_DISK_GB="${RUNPOD_CONTAINER_DISK_GB:-30}"
VOLUME_MOUNT_PATH="${RUNPOD_VOLUME_MOUNT_PATH:-/runpod-volume}"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"
SSH_KEY="${RUNPOD_SSH_KEY:-${HOME}/.ssh/id_ed25519_runpod}"
STATE_FILE="${SCRIPT_DIR}/.pod_id"

# Readiness deadlines (design D6). A pod that reaches RUNNING without ever becoming
# reachable bills indefinitely for nothing — RunPod returned several such pods on
# 2026-09-08/09, with runtime:null, no publicIp and no portMappings. The wait is therefore
# bounded, and expiry tears the pod down instead of warning and leaving it running. The
# fallback deadline is longer because ComfyUI must additionally finish starting behind the
# proxy, whereas the tunnelled path only waits for an IP to be issued.
READY_DEADLINE_TUNNEL_SECS="${READY_DEADLINE_TUNNEL_SECS:-180}"
READY_DEADLINE_PROXY_SECS="${READY_DEADLINE_PROXY_SECS:-420}"
POLL_INTERVAL_SECS="${POLL_INTERVAL_SECS:-5}"

# Publishing ComfyUI's port is OPT-IN (design D3). An HTTP-exposed port is served by
# RunPod at https://<pod id>-8188.proxy.runpod.net and needs no public IP, so it works
# exactly when the tunnel cannot. But RunPod's own docs say "your service becomes publicly
# accessible" and "the Pod ID provides only obscurity, not security", and ComfyUI has no
# auth of its own. The requirement pod.up-enables-ssh says the render server is reached
# "without exposing a public port", so tunnel-only stays the default and exposure is a
# deliberate act. The proxy is a DIAGNOSTIC channel: it is not render-tested.
EXPOSE_HTTP="${RUNPOD_EXPOSE_HTTP:-0}"

if [ -f "$STATE_FILE" ]; then
    echo "a pod id already exists at ${STATE_FILE} ($(cat "$STATE_FILE")) — run infra/down.sh first" >&2
    exit 1
fi
if [ ! -f "${SSH_KEY}.pub" ]; then
    echo "SSH public key not found: ${SSH_KEY}.pub (set RUNPOD_SSH_KEY or create the keypair)" >&2
    exit 1
fi
PUBKEY="$(cat "${SSH_KEY}.pub")"

# Build the create payload safely (PUBLIC_KEY enables SSH). dataCenterIds is set when
# provided so the pod lands in the network volume's region. Ports: 22/tcp always, and
# ComfyUI's 8188/http only when RUNPOD_EXPOSE_HTTP=1 — see the EXPOSE_HTTP comment above.
payload=$(
    RUNPOD_NAME="$POD_NAME" RUNPOD_IMG="$IMAGE" RUNPOD_GPU="$GPU_TYPE" \
    RUNPOD_DISK="$CONTAINER_DISK_GB" RUNPOD_MNT="$VOLUME_MOUNT_PATH" \
    RUNPOD_VOL="$RUNPOD_NETWORK_VOLUME_ID" RUNPOD_DC="${RUNPOD_DATACENTER:-}" \
    RUNPOD_PUBKEY="$PUBKEY" RUNPOD_EXPOSE_HTTP="$EXPOSE_HTTP" python3 <<'PY'
import json, os

# Tunnelled access always; the public HTTP port only when explicitly opted into.
ports = ["22/tcp"]
if os.environ.get("RUNPOD_EXPOSE_HTTP") == "1":
    ports.append("8188/http")

body = {
    "name": os.environ["RUNPOD_NAME"],
    "imageName": os.environ["RUNPOD_IMG"],
    "cloudType": "SECURE",
    "computeType": "GPU",
    "gpuCount": 1,
    "gpuTypeIds": [os.environ["RUNPOD_GPU"]],
    "gpuTypePriority": "availability",
    "containerDiskInGb": int(os.environ["RUNPOD_DISK"]),
    "volumeMountPath": os.environ["RUNPOD_MNT"],
    "networkVolumeId": os.environ["RUNPOD_VOL"],
    "ports": ports,
    "env": {"PUBLIC_KEY": os.environ["RUNPOD_PUBKEY"]},
}
dc = os.environ.get("RUNPOD_DC")
if dc:
    body["dataCenterIds"] = [dc]
print(json.dumps(body))
PY
)

echo "creating pod '${POD_NAME}' (${GPU_TYPE}) — this STARTS per-second billing…"
response=$(curl -sS -X POST "${API}/pods" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "${payload}")

pod_id=$(printf '%s' "$response" | python3 -c 'import sys, json; d=json.load(sys.stdin); d=d[0] if isinstance(d, list) else d; print(d.get("id", ""))' 2>/dev/null || true)
if [ -z "$pod_id" ]; then
    echo "pod creation failed:" >&2
    printf '%s\n' "$response" >&2
    exit 1
fi
printf '%s' "$pod_id" > "$STATE_FILE"
echo "pod created: ${pod_id} (id saved to ${STATE_FILE})"

# From here until the pod is confirmed reachable, ANY exit must stop the billing this
# script started. The readiness deadline below is one way out, but it is only one: a curl
# that fails under `set -e`, a JSON parse blowup, or a Ctrl-C would each leave a live pod
# and a written .pod_id behind — the same failure the deadline exists to prevent, reached
# by a different route. One trap covers the whole class. Cleared on the success path.
trap 'rc=$?; [ "$rc" -eq 0 ] || { echo "aborting — tearing down pod ${pod_id} so it stops billing" >&2; "${SCRIPT_DIR}/down.sh" "$pod_id" || true; }' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

deadline_secs="$READY_DEADLINE_TUNNEL_SECS"
if [ "$EXPOSE_HTTP" = "1" ]; then
    deadline_secs="$READY_DEADLINE_PROXY_SECS"
fi

# Poll the query endpoint (?id=) — unlike GET /pods/{id}, it populates publicIp +
# portMappings once the TCP proxy is wired up.
echo "waiting up to ${deadline_secs}s for the pod's public IP + SSH port…"
public_ip="-"
ssh_port="-"
ready_by=$((SECONDS + deadline_secs))
while [ "$SECONDS" -lt "$ready_by" ]; do
    pod=$(curl -sS "${API}/pods?id=${pod_id}" -H "Authorization: Bearer ${RUNPOD_API_KEY}")
    read -r public_ip ssh_port <<EOF2
$(printf '%s' "$pod" | python3 -c '
import sys, json
d = json.load(sys.stdin)
d = d[0] if isinstance(d, list) else d
pm = d.get("portMappings") or {}
print(d.get("publicIp") or "-", pm.get("22", "-"))
' 2>/dev/null || echo "- -")
EOF2
    echo "  [${SECONDS}s/${deadline_secs}s] ip=${public_ip} ssh_port=${ssh_port}"
    if [ "$public_ip" != "-" ] && [ "$ssh_port" != "-" ]; then
        break
    fi
    sleep "$POLL_INTERVAL_SECS"
done

echo
if [ "$public_ip" != "-" ] && [ "$ssh_port" != "-" ]; then
    trap - EXIT  # the pod is good — hand it over rather than tearing it down
    echo "pod ${pod_id} is up at ${public_ip}:${ssh_port}"
    echo "  SSH:    ssh -i ${SSH_KEY} root@${public_ip} -p ${ssh_port}"
    echo "  Tunnel: ssh -i ${SSH_KEY} -N -L ${COMFYUI_PORT}:localhost:${COMFYUI_PORT} root@${public_ip} -p ${ssh_port}"
    echo "then ComfyUI is at http://localhost:${COMFYUI_PORT} (through the tunnel — no Cloudflare)"
    if [ "$EXPOSE_HTTP" = "1" ]; then
        echo "  Proxy:  https://${pod_id}-${COMFYUI_PORT}.proxy.runpod.net"
        echo "          PUBLIC and UNAUTHENTICATED, and NOT render-tested — diagnostics only."
    fi
    echo
    echo "tear down with: infra/down.sh   (do this promptly — billing runs until then)"
else
    echo "pod ${pod_id} never became reachable within ${deadline_secs}s." >&2
    echo "This is a known RunPod condition (RUNNING with no public IP and no port" >&2
    echo "mapping), not a fault here. The EXIT trap tears it down so it stops billing." >&2
    exit 1
fi
