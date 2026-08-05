# syntax=docker/dockerfile:1

# ComfyUI GPU image: RealVisXL V5.0 txt2img (prompt-only; pose is prompt-driven).
# cu128 PyTorch wheels — the Blackwell/sm_120 requirement; cu124 fails at runtime with
# "no kernel image is available". Models are NOT baked in; they are fetched onto a
# RunPod network volume at boot by download_models.sh (see start.sh).
#
# The exact ComfyUI ref is confirmed and relocked against the live pod in Phase 5 — the
# image mirrors the placeholder-then-relock rule.

ARG CUDA_IMAGE=nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04
FROM ${CUDA_IMAGE} AS base

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# System deps: python, git, ssh (for the tunnel to 8188), libs a few wheels need.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git wget ca-certificates \
        openssh-server libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# --- PyTorch (cu128) ---
ARG TORCH_VERSION=2.7.1
ARG TORCHVISION_VERSION=0.22.1
ARG PYTORCH_INDEX=https://download.pytorch.org/whl/cu128
RUN pip3 install --no-cache-dir \
        "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" \
        --index-url "${PYTORCH_INDEX}"

# --- ComfyUI (pinned) ---
ARG COMFYUI_REPO=https://github.com/comfyanonymous/ComfyUI.git
ARG COMFYUI_REF=v0.3.45
WORKDIR /opt
RUN git clone "${COMFYUI_REPO}" ComfyUI \
    && git -C ComfyUI checkout "${COMFYUI_REF}" \
    && pip3 install --no-cache-dir -r ComfyUI/requirements.txt

# --- sshd (for the SSH tunnel to ComfyUI's 8188) ---
RUN mkdir -p /var/run/sshd \
    && sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config

# Provisioning scripts (model fetch + boot).
COPY download_models.sh /opt/download_models.sh
COPY infra/start.sh /opt/start.sh
RUN chmod +x /opt/download_models.sh /opt/start.sh

# ComfyUI code lives in the image; models live on the mounted network volume.
ENV COMFYUI_HOME=/opt/ComfyUI
ENV MODELS_DIR=/runpod-volume/models

EXPOSE 8188 22

CMD ["/opt/start.sh"]
