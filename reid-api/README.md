# reid-api

Person Re-Identification (Re-ID) sidecar. Wraps `OSNet-AIN-x1.0` ONNX inference
behind a small Flask app. Used by the backend indexer to produce per-face body
embeddings and by the scan endpoint (Phase 3) to gate face matches that pass
the cosine threshold but fail to match on body / clothing.

## One-time model export

The runtime image ships **without** the model. Export it once and mount the
resulting `models/` directory into the container via docker-compose.

`torchreid` at the version we need is NOT on PyPI (PyPI tops out at 0.2.5 and
lacks `osnet_ain`); install it from KaiyangZhou's `deep-person-reid` source.
`torch.onnx.export` also needs the `onnx` package. Simplest reproducible path
is a throwaway container — run from the repo root:

```bash
docker run --rm -v "$PWD/reid-api:/work" -w /work python:3.11-slim bash -c '
  apt-get update -qq && apt-get install -y -qq libgl1 libglib2.0-0 gcc g++ git
  pip install "numpy<2" Cython onnx
  pip install torch==2.1.2 torchvision==0.16.2 --index-url https://download.pytorch.org/whl/cpu
  git clone --depth 1 https://github.com/KaiyangZhou/deep-person-reid.git /tmp/dpr
  grep -vE "tb-nightly|flake8|yapf|isort" /tmp/dpr/requirements.txt > /tmp/req.txt
  pip install -r /tmp/req.txt tensorboard
  pip install --no-build-isolation -e /tmp/dpr
  python scripts/export_onnx.py'
# Produces reid-api/models/osnet_ain_x1_0.onnx (~8.7 MB), then:
docker compose restart reid-api
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
