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
cat > "${COMFYUI_HOME}/extra_model_paths.yaml" <<YAML
runpod:
  base_path: ${MODELS_DIR}
  checkpoints: checkpoints
YAML

echo "launching ComfyUI on port ${COMFYUI_PORT}"
cd "${COMFYUI_HOME}"
exec python3 main.py --listen 0.0.0.0 --port "${COMFYUI_PORT}"
