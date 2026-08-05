#!/usr/bin/env bash
# Fetch pinned models onto the RunPod network volume.
#
# Idempotent: skips any file already present (so a re-boot on a warm volume is a no-op).
# Prompt-only pipeline: just the RealVisXL checkpoint — no ControlNet, no InstantID. The
# face-detectability check runs offline on the host (scripts/check_face.py), not on the pod.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-/runpod-volume/models}"

CKPT_DIR="${MODELS_DIR}/checkpoints"

# --- pinned sources ---
REALVIS_URL="https://huggingface.co/SG161222/RealVisXL_V5.0/resolve/main/RealVisXL_V5.0.safetensors"
REALVIS_DEST="${CKPT_DIR}/RealVisXL_V5.0.safetensors"

download() {
    local url="$1" dest="$2"
    if [ -f "$dest" ]; then
        echo "skip (exists): $dest"
        return 0
    fi
    mkdir -p "$(dirname "$dest")"
    echo "downloading: $url"
    # Download to a temp name then move, so an interrupted fetch never looks "present".
    wget -q --show-progress -O "${dest}.partial" "$url"
    mv "${dest}.partial" "$dest"
    echo "saved: $dest"
}

download "$REALVIS_URL" "$REALVIS_DEST"

echo "models ready under ${MODELS_DIR}"
