#!/usr/bin/env bash
# On-pod boot: start sshd (for the tunnel), fetch models onto the volume, launch ComfyUI.
set -euo pipefail

COMFYUI_HOME="${COMFYUI_HOME:-/opt/ComfyUI}"
MODELS_DIR="${MODELS_DIR:-/runpod-volume/models}"
COMFYUI_PORT="${COMFYUI_PORT:-8188}"

# sshd for the SSH tunnel that generate.py drives ComfyUI over. This image is FROM
# nvidia/cuda (not a RunPod base image), so we install RunPod's injected PUBLIC_KEY
# into authorized_keys ourselves and generate host keys before launching sshd.
if command -v sshd >/dev/null 2>&1; then
    mkdir -p /root/.ssh
    printf '%s\n' "${PUBLIC_KEY:-${SSH_PUBLIC_KEY:-}}" > /root/.ssh/authorized_keys
    chmod 700 /root/.ssh
    chmod 600 /root/.ssh/authorized_keys
    mkdir -p /var/run/sshd
    ssh-keygen -A
    /usr/sbin/sshd
    echo "sshd started"
fi

# One-time model fetch onto the persistent network volume (idempotent).
/opt/download_models.sh

# Point ComfyUI at the volume's models (code is in the image, weights are on the volume).
# v0.2 exposes the InstantID + FaceDetailer folders too, not just checkpoints; insightface
# maps the antelopev2 pack (both InstantIDFaceAnalysis and the face gate resolve it there).
cat > "${COMFYUI_HOME}/extra_model_paths.yaml" <<YAML
runpod:
  base_path: ${MODELS_DIR}
  checkpoints: checkpoints
  controlnet: controlnet
  instantid: instantid
  ultralytics: ultralytics
  insightface: insightface
YAML

# extra_model_paths.yaml is not enough for two custom nodes: the Impact Subpack
# (UltralyticsDetectorProvider) and the InstantID node resolve models from
# ${COMFYUI_HOME}/models/<x> directly (folder_paths.models_dir) and IGNORE the yaml. Without
# these symlinks the bbox detector list comes up empty and the InstantID node auto-downloads a
# BROKEN (nested) antelopev2 pack. Point both dirs at the volume's copies. (Found live in Phase 6.)
mkdir -p "${COMFYUI_HOME}/models"
ln -sfn "${MODELS_DIR}/ultralytics" "${COMFYUI_HOME}/models/ultralytics"
ln -sfn "${MODELS_DIR}/insightface" "${COMFYUI_HOME}/models/insightface"

echo "launching ComfyUI on port ${COMFYUI_PORT}"
cd "${COMFYUI_HOME}"
exec python3 main.py --listen 0.0.0.0 --port "${COMFYUI_PORT}"
