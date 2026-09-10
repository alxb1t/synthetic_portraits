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
# --max-time on every provider call, not just the proxy probe: curl has no default
# transfer timeout, and the readiness deadline below is only tested BETWEEN iterations.
# A stalled connection inside a call therefore outlives every deadline in this script,
# and the EXIT trap cannot help because the script is not exiting — the pod simply bills
# for the length of the stall. A timed-out curl fails under `set -e` instead, which is
# an exit, which is the trap.
response=$(curl -sS -m 30 --connect-timeout 10 -X POST "${API}/pods" \
    -H "Authorization: Bearer ${RUNPOD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "${payload}")

pod_id=$(printf '%s' "$response" | python3 -c 'import sys, json; d=json.load(sys.stdin); d=d[0] if isinstance(d, list) else d; print(d.get("id", ""))' 2>/dev/null || true)
if [ -z "$pod_id" ]; then
    # The one window the EXIT trap below cannot cover: the provider may have created
    # the pod and only the id failed to reach us, so there is nothing to tear down by.
    # Saying so is the whole mitigation — .pod_id is absent, so down.sh has no target,
    # and an operator who reads "failed" as "nothing was created" leaves it billing.
    echo "pod creation failed:" >&2
    printf '%s\n' "$response" >&2
    echo "WARNING: a pod may have been created anyway — this failed while reading the" >&2
    echo "         id, not necessarily before the pod existed. Check the RunPod console" >&2
    echo "         for '${POD_NAME}' and delete it, or it bills unattended." >&2
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
#
# Readiness must test the route we will actually use. When the HTTP port is published the
# proxy needs NO public IP, so it is reachable exactly in the condition where the tunnel
# never becomes reachable at all — a capacity-starved region that issues no address.
# Measured 2026-09-09/10 in EU-RO-1: two pods reached RUNNING with runtime:null and were
# torn down at the deadline while the proxy route was the one that could have served them.
# Waiting LONGER on the tunnel's signal cannot fix that; only polling the other route can.
PROXY_URL="https://${pod_id}-${COMFYUI_PORT}.proxy.runpod.net"
echo "waiting up to ${deadline_secs}s for the pod to become reachable…"
public_ip="-"
ssh_port="-"
proxy_ready=0
ready_by=$((SECONDS + deadline_secs))
while [ "$SECONDS" -lt "$ready_by" ]; do
    pod=$(curl -sS -m 30 --connect-timeout 10 "${API}/pods?id=${pod_id}" -H "Authorization: Bearer ${RUNPOD_API_KEY}")
    read -r public_ip ssh_port pod_status <<EOF2
$(printf '%s' "$pod" | python3 -c '
import sys, json
d = json.load(sys.stdin)
d = d[0] if isinstance(d, list) else d
pm = d.get("portMappings") or {}
print(d.get("publicIp") or "-", pm.get("22", "-"), d.get("status") or "-")
' 2>/dev/null || echo "- - -")
EOF2

    # A container that died is not a container still starting. Measured 2026-09-10: three
    # pods whose image could not be pulled sat at EXITED within seconds while this loop,
    # reading only publicIp and portMappings, waited out its full deadline on each.
    #
    # Fail-OPEN by design: `status` is confirmed on GET /pods/{id}, but this is the ?id=
    # query form and that it carries the field is unproven. Only an explicit terminal
    # state aborts; anything else — including no status at all — keeps waiting exactly as
    # before, so this cannot tear down a pod that would have come up. Exiting here is an
    # exit, which is the EXIT trap, which is the teardown.
    case "$pod_status" in
        EXITED | TERMINATED)
            echo "pod ${pod_id} reached ${pod_status} — the container is not running." >&2
            echo "Most often the image could not be pulled; check the tag exists." >&2
            exit 1
            ;;
    esac
    echo "  [${SECONDS}s/${deadline_secs}s] ip=${public_ip} ssh_port=${ssh_port}"
    if [ "$public_ip" != "-" ] && [ "$ssh_port" != "-" ]; then
        break
    fi
    # /system_stats, not the bare host: the proxy resolves long before ComfyUI is listening,
    # so anything less would report ready while a render would still be refused.
    if [ "$EXPOSE_HTTP" = "1" ] && curl -sf -m 10 -o /dev/null "${PROXY_URL}/system_stats"; then
        proxy_ready=1
        echo "  proxy is answering at ${PROXY_URL}"
        break
    fi
    sleep "$POLL_INTERVAL_SECS"
done

echo
# Unreachable by BOTH routes is the only failure: fall out first, and the EXIT trap tears
# the pod down. Everything below is a reachable pod, so the trap is cleared and the
# hand-over trailer printed exactly once rather than per branch.
if [ "$public_ip" = "-" ] || [ "$ssh_port" = "-" ]; then
    if [ "$proxy_ready" != "1" ]; then
        echo "pod ${pod_id} never became reachable within ${deadline_secs}s." >&2
        echo "This is a known RunPod condition (RUNNING with no public IP and no port" >&2
        echo "mapping), not a fault here. The EXIT trap tears it down so it stops billing." >&2
        exit 1
    fi
fi

trap - EXIT  # the pod is reachable — hand it over rather than tearing it down

if [ "$proxy_ready" = "1" ]; then
    # No public IP was issued, so there is no tunnel to offer — the proxy is the only
    # route to this pod, not a fallback beside a working one.
    echo "pod ${pod_id} has no public IP; ComfyUI is answering on the proxy."
    echo "  ComfyUI: ${PROXY_URL}"
    echo "  Run:     uv run --group faces python generate.py --server ${PROXY_URL} ..."
    echo "  NOTE:    that URL is PUBLIC and UNAUTHENTICATED, and stays that way until"
    echo "           infra/down.sh runs — not just for a moment. Only GETs are verified;"
    echo "           whether the proxy accepts renders is unproven."
else
    echo "pod ${pod_id} is up at ${public_ip}:${ssh_port}"
    echo "  SSH:    ssh -i ${SSH_KEY} root@${public_ip} -p ${ssh_port}"
    echo "  Tunnel: ssh -i ${SSH_KEY} -N -L ${COMFYUI_PORT}:localhost:${COMFYUI_PORT} root@${public_ip} -p ${ssh_port}"
    echo "then ComfyUI is at http://localhost:${COMFYUI_PORT} (through the tunnel — no Cloudflare)"
    if [ "$EXPOSE_HTTP" = "1" ]; then
        echo "  Proxy:  ${PROXY_URL}"
        echo "          PUBLIC and UNAUTHENTICATED — prefer the tunnel above."
    fi
fi

echo
echo "tear down with: infra/down.sh   (do this promptly — billing runs until then)"
