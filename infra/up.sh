#!/usr/bin/env bash
# Provision an on-demand RunPod GPU pod (RTX 4090) with the models network volume
# attached, then print the SSH tunnel command that generate.py drives ComfyUI over.
#
# ⚠️ METERED: this creates a pod that bills PER SECOND until infra/down.sh tears it
# down. Reads RUNPOD_API_KEY + RUNPOD_NETWORK_VOLUME_ID (and optional overrides) from
# the environment or the gitignored .env. The pod id is saved to infra/.pod_id so
# down.sh tears down exactly this pod.
#
# The exact runtime response shape (portMappings / publicIp) is confirmed and relocked
# against the live pod in Phase 5 — until then the raw pod JSON is echoed so the human
# can read the connection details if a field name has drifted.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load .env (never committed) so the key/volume live only there.
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
STATE_FILE="${SCRIPT_DIR}/.pod_id"

if [ -f "$STATE_FILE" ]; then
    echo "a pod id already exists at ${STATE_FILE} ($(cat "$STATE_FILE")) — run infra/down.sh first" >&2
    exit 1
fi

payload=$(cat <<JSON
{
  "name": "${POD_NAME}",
  "imageName": "${IMAGE}",
  "cloudType": "SECURE",
  "computeType": "GPU",
  "gpuCount": 1,
  "gpuTypeIds": ["${GPU_TYPE}"],
  "gpuTypePriority": "availability",
  "containerDiskInGb": ${CONTAINER_DISK_GB},
  "volumeMountPath": "${VOLUME_MOUNT_PATH}",
  "networkVolumeId": "${RUNPOD_NETWORK_VOLUME_ID}",
  "ports": ["${COMFYUI_PORT}/http", "22/tcp"]
}
JSON
)

echo "creating pod '${POD_NAME}' (${GPU_TYPE}) — this STARTS per-second billing…"
response=$(curl -sS -X POST "${API}/pods" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "${payload}")

pod_id=$(printf '%s' "$response" | python3 -c 'import sys, json; print(json.load(sys.stdin).get("id", ""))' 2>/dev/null || true)
if [ -z "$pod_id" ]; then
    echo "pod creation failed:" >&2
    printf '%s\n' "$response" >&2
    exit 1
fi
printf '%s' "$pod_id" > "$STATE_FILE"
echo "pod created: ${pod_id} (id saved to ${STATE_FILE})"

echo "waiting for the pod to reach RUNNING…"
public_ip=""
ssh_port=""
for _ in $(seq 1 60); do
    pod=$(curl -sS "${API}/pods/${pod_id}" \
        -H "Authorization: Bearer ${RUNPOD_API_KEY}")
    read -r status public_ip ssh_port <<EOF2
$(printf '%s' "$pod" | python3 -c '
import sys, json
d = json.load(sys.stdin)
pm = d.get("portMappings") or {}
print(d.get("desiredStatus", ""), d.get("publicIp") or "-", pm.get("22", "-"))
' 2>/dev/null || echo "- - -")
EOF2
    echo "  status=${status} ip=${public_ip} ssh_port=${ssh_port}"
    if [ "$status" = "RUNNING" ] && [ "$public_ip" != "-" ] && [ "$ssh_port" != "-" ]; then
        break
    fi
    sleep 10
done

echo
echo "pod ${pod_id} is up. raw pod detail:"
printf '%s\n' "$pod"
echo
if [ "$public_ip" != "-" ] && [ "$ssh_port" != "-" ]; then
    echo "open the ComfyUI tunnel (leave running in another shell):"
    echo "  ssh -N -L ${COMFYUI_PORT}:localhost:${COMFYUI_PORT} root@${public_ip} -p ${ssh_port}"
    echo "then ComfyUI is at http://localhost:${COMFYUI_PORT}"
else
    echo "connection details not parsed — read them from the raw JSON above (relock field names)."
fi
echo
echo "tear down with: infra/down.sh   (do this promptly — billing runs until then)"
