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
    && pip3 install --no-cache-dir -r ComfyUI/requirements.txt \
    # ComfyUI imports `requests` (app/frontend_management.py) but omits it from
    # requirements.txt; the minimal CUDA base lacks it → startup crash without this.
    && pip3 install --no-cache-dir requests

# --- Custom nodes (pinned) : InstantID (identity) + Impact Pack/Subpack (FaceDetailer) ---
# Exact commits verified in v0.2_research (Phase 0) — pins, not floating HEAD.
ARG INSTANTID_REF=72495e806bc2ab9c41581e15ccaa1bcf83c477e8
ARG IMPACT_PACK_REF=429d0159ad429e64d2b3916e6e7be9c22d025c3c
ARG IMPACT_SUBPACK_REF=50c7b71a6a224734cc9b21963c6d1926816a97f1
WORKDIR /opt/ComfyUI/custom_nodes
RUN git clone https://github.com/cubiq/ComfyUI_InstantID.git \
    && git -C ComfyUI_InstantID checkout "${INSTANTID_REF}" \
    && git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git \
    && git -C ComfyUI-Impact-Pack checkout "${IMPACT_PACK_REF}" \
    && git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git \
    && git -C ComfyUI-Impact-Subpack checkout "${IMPACT_SUBPACK_REF}"

# --- Face / detailer Python deps ---
# insightface + CPU onnxruntime (the CPU build only — never the GPU variant, never both; it
# sidesteps the Blackwell/cu128 CUDA-match pain) power both InstantID's face analysis and the
# FaceDetector gate; ultralytics
# drives the FaceDetailer bbox detector. Impact Pack caps numpy<2 — pin it so a transitive dep
# can't pull numpy>=2. The nodes' own requirements.txt files are the source of truth for the
# rest; install numpy<2 last so its constraint wins.
RUN pip3 install --no-cache-dir -r ComfyUI_InstantID/requirements.txt \
    && pip3 install --no-cache-dir -r ComfyUI-Impact-Pack/requirements.txt \
    && pip3 install --no-cache-dir -r ComfyUI-Impact-Subpack/requirements.txt \
    && pip3 install --no-cache-dir insightface onnxruntime "ultralytics>=8.3.162" "numpy<2"

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
