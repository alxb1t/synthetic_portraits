#!/usr/bin/env bash
# Fetch pinned models onto the RunPod network volume.
#
# Idempotent: skips any file already present (so a re-boot on a warm volume is a no-op).
# v0.2 adds the InstantID stack (identity) + the FaceDetailer bbox detector on top of the
# RealVisXL checkpoint. Each file lands in its own ComfyUI model subfolder — subfolder-isolated
# so generic filenames (config.json, diffusion_pytorch_model.safetensors) never collide.
# Sources + pins are from v0.2_research (Phase 0). The face-detectability check runs offline
# on the host (scripts/check_face.py), not on the pod.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-/runpod-volume/models}"

CKPT_DIR="${MODELS_DIR}/checkpoints"
INSTANTID_DIR="${MODELS_DIR}/instantid"
CONTROLNET_DIR="${MODELS_DIR}/controlnet"
ANTELOPE_DIR="${MODELS_DIR}/insightface/models/antelopev2"
ULTRALYTICS_BBOX_DIR="${MODELS_DIR}/ultralytics/bbox"

# --- pinned sources ---
# RealVisXL: the repo ships fp16/fp32 variants — there is no bare RealVisXL_V5.0.safetensors
# (requesting it 404s → start.sh crash-loop). fp16 is the inference build (~6.5 GB).
REALVIS_URL="https://huggingface.co/SG161222/RealVisXL_V5.0/resolve/main/RealVisXL_V5.0_fp16.safetensors"
REALVIS_DEST="${CKPT_DIR}/RealVisXL_V5.0_fp16.safetensors"

# InstantID IP-Adapter (~1.69 GB) → models/instantid/.
IPADAPTER_URL="https://huggingface.co/InstantX/InstantID/resolve/main/ip-adapter.bin"
IPADAPTER_DEST="${INSTANTID_DIR}/ip-adapter.bin"

# InstantID identity ControlNet (weights + config) → models/controlnet/.
CN_URL="https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/diffusion_pytorch_model.safetensors"
CN_DEST="${CONTROLNET_DIR}/diffusion_pytorch_model.safetensors"
CN_CFG_URL="https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/config.json"
CN_CFG_DEST="${CONTROLNET_DIR}/config.json"

# antelopev2 pack (5 ONNX, ~428 MB) → models/insightface/models/antelopev2/. Scriptable mirror
# of the InstantX Space (Spaces are awkward to script). Consumed by InstantIDFaceAnalysis AND
# the insightface FaceDetector gate.
ANTELOPE_BASE="https://huggingface.co/MonsterMMORPG/InstantID_Models/resolve/main/models/antelopev2"
ANTELOPE_FILES=(1k3d68.onnx 2d106det.onnx genderage.onnx glintr100.onnx scrfd_10g_bnkps.onnx)

# FaceDetailer bbox detector → models/ultralytics/bbox/.
YOLO_URL="https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov8m.pt"
YOLO_DEST="${ULTRALYTICS_BBOX_DIR}/face_yolov8m.pt"

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
download "$IPADAPTER_URL" "$IPADAPTER_DEST"
download "$CN_URL" "$CN_DEST"
download "$CN_CFG_URL" "$CN_CFG_DEST"
for f in "${ANTELOPE_FILES[@]}"; do
    download "${ANTELOPE_BASE}/${f}" "${ANTELOPE_DIR}/${f}"
done
download "$YOLO_URL" "$YOLO_DEST"

echo "models ready under ${MODELS_DIR}"
