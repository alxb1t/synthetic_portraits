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

if [ -f "$STATE_FILE" ]; then
    echo "a pod id already exists at ${STATE_FILE} ($(cat "$STATE_FILE")) — run infra/down.sh first" >&2
    exit 1
fi
if [ ! -f "${SSH_KEY}.pub" ]; then
    echo "SSH public key not found: ${SSH_KEY}.pub (set RUNPOD_SSH_KEY or create the keypair)" >&2
    exit 1
fi
PUBKEY="$(cat "${SSH_KEY}.pub")"

# Build the create payload safely (PUBLIC_KEY enables SSH; only 22/tcp is exposed —
# ComfyUI's 8188 is reached through the tunnel). dataCenterIds is set when provided so
# the pod lands in the network volume's region.
payload=$(
    RUNPOD_NAME="$POD_NAME" RUNPOD_IMG="$IMAGE" RUNPOD_GPU="$GPU_TYPE" \
    RUNPOD_DISK="$CONTAINER_DISK_GB" RUNPOD_MNT="$VOLUME_MOUNT_PATH" \
    RUNPOD_VOL="$RUNPOD_NETWORK_VOLUME_ID" RUNPOD_DC="${RUNPOD_DATACENTER:-}" \
    RUNPOD_PUBKEY="$PUBKEY" python3 <<'PY'
import json, os
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
    "ports": ["22/tcp"],
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

# Poll the query endpoint (?id=) — unlike GET /pods/{id}, it populates publicIp +
# portMappings once the TCP proxy is wired up.
echo "waiting for the pod's public IP + SSH port…"
public_ip=""
ssh_port=""
for _ in $(seq 1 60); do
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
    echo "  ip=${public_ip} ssh_port=${ssh_port}"
    if [ "$public_ip" != "-" ] && [ "$ssh_port" != "-" ]; then
        break
    fi
    sleep 5
done

echo
if [ "$public_ip" != "-" ] && [ "$ssh_port" != "-" ]; then
    echo "pod ${pod_id} is up at ${public_ip}:${ssh_port}"
    echo "  SSH:    ssh -i ${SSH_KEY} root@${public_ip} -p ${ssh_port}"
    echo "  Tunnel: ssh -i ${SSH_KEY} -N -L ${COMFYUI_PORT}:localhost:${COMFYUI_PORT} root@${public_ip} -p ${ssh_port}"
    echo "then ComfyUI is at http://localhost:${COMFYUI_PORT} (through the tunnel — no Cloudflare)"
else
    echo "public IP / SSH port not ready — check 'curl ${API}/pods?id=${pod_id}'." >&2
fi
echo
echo "tear down with: infra/down.sh   (do this promptly — billing runs until then)"
