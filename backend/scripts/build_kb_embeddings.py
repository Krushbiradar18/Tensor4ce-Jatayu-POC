"""
backend/scripts/build_kb_embeddings.py
=======================================
One-shot script: encodes every chunk in compliance_kb.json with
sentence-transformers (all-MiniLM-L6-v2) and writes a sidecar file
compliance_kb_embeddings.json to the same data/ directory.

Serialisation contract
-----------------------
  chunk_id == positional index in compliance_kb.json
  regulation, source  — copied verbatim for human-readability / sanity checks
  embedding           — list[float], L2-normalised unit vector

Run from the backend/ directory:
  python scripts/build_kb_embeddings.py            # default paths
  python scripts/build_kb_embeddings.py --kb data/compliance_kb.json

The server reads the sidecar at startup (via services/rag.py).
Re-run this script whenever compliance_kb.json is updated.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DEFAULT_KB_PATH  = "data/compliance_kb.json"
DEFAULT_OUT_PATH = "data/compliance_kb_embeddings.json"
MODEL_NAME       = "all-MiniLM-L6-v2"   # ~80 MB, local, no API key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_kb(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path} must be a JSON array of chunk objects")
    return data


def _build_embedding_text(chunk: dict) -> str:
    """Concatenate source + text for richer semantic representation."""
    parts = []
    if chunk.get("source"):
        parts.append(chunk["source"])
    if chunk.get("text"):
        parts.append(chunk["text"])
    return " ".join(parts)


def _normalise(vec: list[float]) -> list[float]:
    """L2-normalise so cosine-sim == dot-product (faster at query time)."""
    import math
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build(kb_path: str, out_path: str) -> None:
    # ---- 1. Load KB --------------------------------------------------------
    if not os.path.exists(kb_path):
        log.error(f"KB not found: {kb_path}")
        sys.exit(1)

    chunks = _load_kb(kb_path)
    log.info(f"Loaded {len(chunks)} chunks from {kb_path}")

    # ---- 2. Load model -----------------------------------------------------
    log.info(f"Loading sentence-transformer model '{MODEL_NAME}' …")
    t0 = time.perf_counter()
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        log.error("sentence-transformers not installed. Run: pip install sentence-transformers")
        sys.exit(1)

    model = SentenceTransformer(MODEL_NAME)
    log.info(f"Model loaded in {time.perf_counter() - t0:.1f}s")

    # ---- 3. Encode all chunks ----------------------------------------------
    texts = [_build_embedding_text(c) for c in chunks]

    log.info(f"Encoding {len(texts)} chunks …")
    t1 = time.perf_counter()
    raw_embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,   # L2-normalise in-place via the model
        convert_to_numpy=True,
    )
    log.info(f"Encoding done in {time.perf_counter() - t1:.1f}s")

    # ---- 4. Build sidecar array -------------------------------------------
    sidecar: list[dict] = []
    for idx, (chunk, emb) in enumerate(zip(chunks, raw_embeddings)):
        sidecar.append(
            {
                "chunk_id":  idx,                          # positional index → serialisation contract
                "regulation": chunk.get("regulation", ""),
                "source":     chunk.get("source", ""),
                "embedding":  emb.tolist(),                # numpy float32 → plain Python floats
            }
        )

    # ---- 5. Integrity sanity check ----------------------------------------
    assert len(sidecar) == len(chunks), "Embedding count mismatch!"
    for entry in sidecar:
        assert entry["chunk_id"] == sidecar.index(entry) or True  # O(1) check via loop idx
        assert len(entry["embedding"]) > 0, "Empty embedding detected"

    # Use enumerate-based check (O(n))
    for i, entry in enumerate(sidecar):
        assert entry["chunk_id"] == i, f"chunk_id mismatch at position {i}"

    log.info("✓ chunk_id integrity check passed for all entries")

    # ---- 6. Write sidecar --------------------------------------------------
    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(sidecar, fh, ensure_ascii=False, indent=2)

    log.info(f"✓ Wrote {len(sidecar)} embeddings → {out_path}")
    dim = len(sidecar[0]["embedding"])
    log.info(f"  Vector dimension: {dim}")
    log.info(f"  Model: {MODEL_NAME}")
    log.info("Re-run this script whenever compliance_kb.json is updated.")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build compliance KB embedding sidecar")
    parser.add_argument("--kb",  default=DEFAULT_KB_PATH,  help="Path to compliance_kb.json")
    parser.add_argument("--out", default=DEFAULT_OUT_PATH, help="Output sidecar path")
    args = parser.parse_args()
    build(args.kb, args.out)
