#!/usr/bin/env bash
# Fetch pinned models onto the RunPod network volume.
#
# Idempotent: skips any file already present (so a re-boot on a warm volume is a no-op).
# v0.2 adds the InstantID stack (identity) + the FaceDetailer bbox detector on top of the
# RealVisXL checkpoint. Each file lands in its own ComfyUI model subfolder — subfolder-isolated
# so generic filenames (config.json, diffusion_pytorch_model.safetensors) never collide.
# Sources + pins are from v0.2_research (Phase 0). The face-detectability check runs offline
# on the host (scripts/check_face.py), not on the pod.
#
# Supply-chain hardening (security S1): every source is pinned to an IMMUTABLE commit SHA
# (`resolve/<sha>/…`, never the mutable `main` branch) and every file is SHA-256 verified after
# download — a mismatch aborts before the file is moved into place. Two of these weights are
# code-executing pickle (`ip-adapter.bin`, `face_yolov8m.pt`) from third-party mirrors, so a moved
# ref or a compromised mirror cannot silently swap in a different file. Revisions + checksums were
# recorded 2026-08-09 via the HF API (paths-info LFS oids); re-record if a pin is bumped.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-/runpod-volume/models}"

CKPT_DIR="${MODELS_DIR}/checkpoints"
INSTANTID_DIR="${MODELS_DIR}/instantid"
CONTROLNET_DIR="${MODELS_DIR}/controlnet"
ANTELOPE_DIR="${MODELS_DIR}/insightface/models/antelopev2"
ULTRALYTICS_BBOX_DIR="${MODELS_DIR}/ultralytics/bbox"

# --- pinned sources (immutable commit SHA + SHA-256) ---
# RealVisXL: the repo ships fp16/fp32 variants — there is no bare RealVisXL_V5.0.safetensors
# (requesting it 404s → start.sh crash-loop). fp16 is the inference build (~6.5 GB).
REALVIS_REV="ac93e0dda1f6d448cae19bbfab8c5e720a5e48bc"
REALVIS_URL="https://huggingface.co/SG161222/RealVisXL_V5.0/resolve/${REALVIS_REV}/RealVisXL_V5.0_fp16.safetensors"
REALVIS_DEST="${CKPT_DIR}/RealVisXL_V5.0_fp16.safetensors"
REALVIS_SHA="6a35a7855770ae9820a3c931d4964c3817b6d9e3c6f9c4dabb5b3a94e5643b80"

# InstantID stack (ip-adapter + identity ControlNet + config) — one pinned commit.
INSTANTID_REV="57b32dfee076092ad2930c71fd6d439c2c3b1820"

# InstantID IP-Adapter (~1.69 GB, pickle) → models/instantid/.
IPADAPTER_URL="https://huggingface.co/InstantX/InstantID/resolve/${INSTANTID_REV}/ip-adapter.bin"
IPADAPTER_DEST="${INSTANTID_DIR}/ip-adapter.bin"
IPADAPTER_SHA="02b3618e36d803784166660520098089a81388e61a93ef8002aa79a5b1c546e1"

# InstantID identity ControlNet (weights + config) → models/controlnet/.
CN_URL="https://huggingface.co/InstantX/InstantID/resolve/${INSTANTID_REV}/ControlNetModel/diffusion_pytorch_model.safetensors"
CN_DEST="${CONTROLNET_DIR}/diffusion_pytorch_model.safetensors"
CN_SHA="c8127be9f174101ebdafee9964d856b49b634435cf6daa396d3f593cf0bbbb05"
CN_CFG_URL="https://huggingface.co/InstantX/InstantID/resolve/${INSTANTID_REV}/ControlNetModel/config.json"
CN_CFG_DEST="${CONTROLNET_DIR}/config.json"
CN_CFG_SHA="2480c42f363d712faae8d0e17cb850a5d1e4cafc232fbd022b1d43eee45234eb"

# antelopev2 pack (5 ONNX, ~428 MB) → models/insightface/models/antelopev2/. Scriptable mirror
# of the InstantX Space (Spaces are awkward to script). Consumed by InstantIDFaceAnalysis AND
# the insightface FaceDetector gate. Third-party mirror → pinned + checksummed.
ANTELOPE_REV="397cafa6d8310e96e302e96528c20a4c92a884f2"
ANTELOPE_BASE="https://huggingface.co/MonsterMMORPG/InstantID_Models/resolve/${ANTELOPE_REV}/models/antelopev2"
ANTELOPE_FILES=(1k3d68.onnx 2d106det.onnx genderage.onnx glintr100.onnx scrfd_10g_bnkps.onnx)
ANTELOPE_SHAS=(
    df5c06b8a0c12e422b2ed8947b8869faa4105387f199c477af038aa01f9a45cc  # 1k3d68.onnx
    f001b856447c413801ef5c42091ed0cd516fcd21f2d6b79635b1e733a7109dbf  # 2d106det.onnx
    4fde69b1c810857b88c64a335084f1c3fe8f01246c9a191b48c7bb756d6652fb  # genderage.onnx
    4ab1d6435d639628a6f3e5008dd4f929edf4c4124b1a7169e1048f9fef534cdf  # glintr100.onnx
    5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91  # scrfd_10g_bnkps.onnx
)

# FaceDetailer bbox detector (pickle) → models/ultralytics/bbox/. Third-party mirror → pinned + checksummed.
YOLO_REV="53cc19de382014514d9d4038601d261a7faa9b7b"
YOLO_URL="https://huggingface.co/Bingsu/adetailer/resolve/${YOLO_REV}/face_yolov8m.pt"
YOLO_DEST="${ULTRALYTICS_BBOX_DIR}/face_yolov8m.pt"
YOLO_SHA="717923c19b3f4bbf5250b728f1fa6b2cb72a33aed1d236ea9caf0e21ad943e5f"

verify_sha256() {
    # Abort on any checksum mismatch — a swapped/corrupt file must never be trusted.
    local file="$1" expected="$2" actual
    actual="$(sha256sum "$file" | awk '{print $1}')"
    if [ "$actual" != "$expected" ]; then
        echo "ERROR: SHA-256 mismatch for $file" >&2
        echo "  expected: $expected" >&2
        echo "  actual:   $actual" >&2
        rm -f "$file"
        exit 1
    fi
}

download() {
    local url="$1" dest="$2" sha256="$3"
    if [ -f "$dest" ]; then
        # Re-verify warm-volume files too, so an out-of-band swap is caught, not skipped blindly.
        verify_sha256 "$dest" "$sha256"
        echo "skip (exists, verified): $dest"
        return 0
    fi
    mkdir -p "$(dirname "$dest")"
    echo "downloading: $url"
    # Download to a temp name, verify, then move — an interrupted or tampered fetch never lands
    # under the real name (so it never looks "present" and never loads as a trusted model).
    wget -q --show-progress -O "${dest}.partial" "$url"
    verify_sha256 "${dest}.partial" "$sha256"
    mv "${dest}.partial" "$dest"
    echo "saved (verified): $dest"
}

download "$REALVIS_URL" "$REALVIS_DEST" "$REALVIS_SHA"
download "$IPADAPTER_URL" "$IPADAPTER_DEST" "$IPADAPTER_SHA"
download "$CN_URL" "$CN_DEST" "$CN_SHA"
download "$CN_CFG_URL" "$CN_CFG_DEST" "$CN_CFG_SHA"
for i in "${!ANTELOPE_FILES[@]}"; do
    download "${ANTELOPE_BASE}/${ANTELOPE_FILES[$i]}" "${ANTELOPE_DIR}/${ANTELOPE_FILES[$i]}" "${ANTELOPE_SHAS[$i]}"
done
download "$YOLO_URL" "$YOLO_DEST" "$YOLO_SHA"

echo "models ready under ${MODELS_DIR}"
