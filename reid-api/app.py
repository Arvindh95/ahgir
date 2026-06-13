"""Re-Identification sidecar.

Single endpoint: POST /embed with a single `file` part containing an upper-body
image crop. Returns a 512-d L2-normalised embedding vector.

The model file is loaded once at module import time from MODEL_PATH (env-
overridable). If the file is missing the service starts anyway and reports
unhealthy via /healthcheck — the caller in the indexer / scan path is expected
to fail-soft on errors, so a missing model does not break the rest of the stack.
"""
from __future__ import annotations

import io
import logging
import os
from typing import Optional

import numpy as np
import onnxruntime as ort
from flask import Flask, jsonify, request
from PIL import Image

logger = logging.getLogger("reid-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

MODEL_PATH = os.environ.get("REID_MODEL_PATH", "/app/models/osnet_ain_x1_0.onnx")

# OSNet expects 256x128 input (H, W) normalised with ImageNet statistics in
# RGB order. Keep these as module constants so the export script and this
# preprocessor agree.
INPUT_H = 256
INPUT_W = 128
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)

# Clamp ORT threads — the VPS is CPU-only and OSNet is small enough that
# thread fan-out for a single 256x128 inference hurts more than it helps.
_SESS_OPTIONS = ort.SessionOptions()
_SESS_OPTIONS.intra_op_num_threads = 2
_SESS_OPTIONS.inter_op_num_threads = 1

_session: Optional[ort.InferenceSession] = None
_input_name: Optional[str] = None
_model_load_error: Optional[str] = None


def _load_session() -> None:
    global _session, _input_name, _model_load_error
    if not os.path.exists(MODEL_PATH):
        _model_load_error = f"model file not found at {MODEL_PATH}"
        logger.warning(_model_load_error)
        return
    try:
        _session = ort.InferenceSession(
            MODEL_PATH,
            sess_options=_SESS_OPTIONS,
            providers=["CPUExecutionProvider"],
        )
        _input_name = _session.get_inputs()[0].name
        logger.info(f"Loaded ONNX model {MODEL_PATH}, input={_input_name}")
        _model_load_error = None
    except Exception as exc:
        _model_load_error = f"failed to load model: {exc}"
        logger.exception(_model_load_error)


_load_session()

app = Flask(__name__)


def _preprocess(image_bytes: bytes) -> np.ndarray:
    """Decode, resize, normalise, transpose to NCHW."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    img = img.resize((INPUT_W, INPUT_H), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    # HWC -> CHW, add batch dim
    arr = np.transpose(arr, (2, 0, 1))
    return np.expand_dims(arr, axis=0)


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalise so downstream cosine = dot product."""
    norm = np.linalg.norm(vec)
    if norm < 1e-12:
        return vec
    return vec / norm


@app.route("/healthcheck", methods=["GET"])
def healthcheck():
    if _session is None:
        return jsonify({"status": "unhealthy", "error": _model_load_error}), 503
    return jsonify({"status": "ok", "model": MODEL_PATH}), 200


@app.route("/embed", methods=["POST"])
def embed():
    if _session is None:
        return jsonify({"error": _model_load_error or "model not loaded"}), 503
    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "missing 'file' part"}), 400
    raw = f.read()
    if not raw:
        return jsonify({"error": "empty file"}), 400
    try:
        x = _preprocess(raw)
    except Exception as exc:
        return jsonify({"error": f"preprocess failed: {exc}"}), 400
    try:
        out = _session.run(None, {_input_name: x})[0]  # shape (1, D)
    except Exception as exc:
        logger.exception("inference failed")
        return jsonify({"error": f"inference failed: {exc}"}), 500
    vec = _l2_normalize(out[0].astype(np.float32))
    return jsonify({"embedding": vec.tolist(), "dim": int(vec.shape[0])}), 200
