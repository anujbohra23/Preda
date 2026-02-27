"""
scripts/seed_disease_catalog.py

Seeds the disease_catalog table from data/disease_catalog_v2.csv.
Uses sentence-transformers all-MiniLM-L6-v2 (384 dims).

Run after enrich_disease_catalog.py has completed:
    python scripts/seed_disease_catalog.py

Safe to re-run — upserts by icd_code.
"""

import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models import DiseaseCatalog

# Try v2 first, fall back to v1
V2_PATH = os.path.join("data", "disease_catalog_v2.csv")
V1_PATH = os.path.join("data", "disease_catalog.csv")
CATALOG_PATH = V2_PATH if os.path.exists(V2_PATH) else V1_PATH


def main():
    print(f"Using catalog: {CATALOG_PATH}")

    # Load CSV
    rows = []
    with open(CATALOG_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} conditions")

    # Load model
    print("Loading sentence-transformer model (all-MiniLM-L6-v2)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    print("Model loaded.")

    # Build corpus — embed disease_name + short_desc together
    corpus = []
    for r in rows:
        name = r.get("disease_name", "")
        desc = r.get("short_desc", "")
        synonyms = r.get("synonyms", "")
        # Include synonyms in embedding text for better retrieval
        text = f"{name}. {desc}"
        if synonyms:
            # Take first 2 synonyms only
            syn_list = [s.strip() for s in synonyms.split("|")[:2] if s.strip()]
            if syn_list:
                text += " Also known as: " + ", ".join(syn_list)
        corpus.append(text)

    # Encode
    print(f"Encoding {len(corpus)} conditions...")
    embeddings = model.encode(
        corpus,
        batch_size=32,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    print(f"Embedding shape: {embeddings.shape}")  # (621, 384)

    # Upsert into DB
    app = create_app("development")
    with app.app_context():
        inserted = 0
        updated = 0

        for i, row in enumerate(rows):
            vec = embeddings[i].astype(np.float32)

            # Upsert by icd_code (preferred) or disease_name
            existing = None
            if row.get("icd_code"):
                existing = DiseaseCatalog.query.filter_by(
                    icd_code=row["icd_code"]
                ).first()
            if not existing:
                existing = DiseaseCatalog.query.filter_by(
                    disease_name=row["disease_name"]
                ).first()

            if existing:
                existing.disease_name   = row["disease_name"]
                existing.icd_code       = row.get("icd_code", "")
                existing.short_desc     = row.get("short_desc", "")
                existing.embedding_blob = vec.tobytes()
                updated += 1
            else:
                db.session.add(DiseaseCatalog(
                    disease_name    = row["disease_name"],
                    icd_code        = row.get("icd_code", ""),
                    short_desc      = row.get("short_desc", ""),
                    embedding_blob  = vec.tobytes(),
                ))
                inserted += 1

            # Commit in batches of 100
            if (i + 1) % 100 == 0:
                db.session.commit()
                print(f"  {i + 1}/{len(rows)} processed...")

        db.session.commit()
        total = DiseaseCatalog.query.count()
        print(f"\nDone — {inserted} inserted, {updated} updated")
        print(f"Total diseases in DB: {total}")

        # Verify embedding dimension
        d = DiseaseCatalog.query.first()
        if d and d.embedding_blob:
            dim = len(d.embedding_blob) // 4
            print(f"Stored embedding dimension: {dim}")
            assert dim == 384, f"Expected 384 dims, got {dim}"
            print("✓ Dimension check passed")


if __name__ == "__main__":
    main()
