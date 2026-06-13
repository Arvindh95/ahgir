# reid-api

Person Re-Identification (Re-ID) sidecar. Wraps `OSNet-AIN-x1.0` ONNX inference
behind a small Flask app. Used by the backend indexer to produce per-face body
embeddings and by the scan endpoint (Phase 3) to gate face matches that pass
the cosine threshold but fail to match on body / clothing.

## One-time model export

The runtime image ships **without** the model. Export it once and mount the
resulting `models/` directory into the container via docker-compose.

```bash
# In a python env you can throw away (large torch download):
pip install torch==2.1.2 torchvision==0.16.2 torchreid==1.4.0
python reid-api/scripts/export_onnx.py
# Produces reid-api/models/osnet_ain_x1_0.onnx (~7.4 MB)
```

If the file is missing the container starts anyway and `/embed` returns 503.
The indexer treats 503 as a fail-soft (writes `NULL` into `faces.reid_embedding`
and continues), so the rest of the stack stays healthy.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/healthcheck` | 200 if model loaded; 503 + error otherwise |
| `POST` | `/embed` | Multipart `file` ⇒ `{"embedding": [...512 floats], "dim": 512}` |

The returned vector is L2-normalised so cosine similarity reduces to dot
product downstream.
