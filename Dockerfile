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

# --- Reproducible-build lock (security S2) ---
# Exact versions resolved in the validated image, applied with `pip install -c` to every
# non-torch install below so a rebuild resolves the SAME dependency set instead of whatever
# PyPI serves that day (a yanked/compromised release then can't silently land). torch/
# torchvision keep their own pinned --index-url line (they fully determine the nvidia-*/triton
# tree). Regenerate constraints.txt from a fresh `pip freeze` if any pin is bumped.
COPY constraints.txt /opt/constraints.txt

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
    && pip3 install --no-cache-dir -c /opt/constraints.txt -r ComfyUI/requirements.txt \
    # ComfyUI imports `requests` (app/frontend_management.py) but omits it from
    # requirements.txt; the minimal CUDA base lacks it → startup crash without this.
    && pip3 install --no-cache-dir -c /opt/constraints.txt requests

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
# insightface + onnxruntime power both InstantID's face analysis and the FaceDetector gate;
# ultralytics drives the FaceDetailer bbox detector. We explicitly install the CPU onnxruntime
# (never the GPU variant on our line) to sidestep the Blackwell/cu128 CUDA-match pain; note a
# node dep (SAM2 via the Impact Subpack) transitively also pulls onnxruntime-gpu — both are
# version-pinned via constraints.txt to the validated set, not removed (validated in Phase 7).
# Every install is `-c` constraint-locked and the four named deps are exact-pinned (security S2)
# so builds are reproducible; numpy stays <2 (Impact Pack's ceiling) via its exact pin.
RUN pip3 install --no-cache-dir -c /opt/constraints.txt -r ComfyUI_InstantID/requirements.txt \
    && pip3 install --no-cache-dir -c /opt/constraints.txt -r ComfyUI-Impact-Pack/requirements.txt \
    && pip3 install --no-cache-dir -c /opt/constraints.txt -r ComfyUI-Impact-Subpack/requirements.txt \
    && pip3 install --no-cache-dir -c /opt/constraints.txt \
        insightface==1.0.1 onnxruntime==1.23.2 ultralytics==8.4.116 numpy==1.26.4

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
