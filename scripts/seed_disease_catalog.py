"""
Seed the disease catalog using sentence-transformer embeddings (384 dims).

Run once (and re-run whenever disease_catalog.csv changes):
    python scripts/seed_disease_catalog.py
"""
import sys
import os
import csv
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models import DiseaseCatalog

CATALOG_PATH = os.path.join('data', 'disease_catalog.csv')


def main():
    app = create_app('development')

    with app.app_context():
        # ── Read CSV ───────────────────────────────────────────────────────
        rows = []
        with open(CATALOG_PATH, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        print(f'Found {len(rows)} diseases in catalog.')

        # ── Load sentence transformer ──────────────────────────────────────
        print('Loading sentence transformer model...')
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        print('Model loaded.')

        # ── Build corpus ───────────────────────────────────────────────────
        corpus = [
            f"{r['disease_name']} {r['short_desc']}"
            for r in rows
        ]

        # ── Encode all diseases ────────────────────────────────────────────
        print('Encoding disease descriptions...')
        embeddings = model.encode(
            corpus,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        print(f'Embedding shape: {embeddings.shape}')  # should be (51, 384)

        # ── Upsert into DB ─────────────────────────────────────────────────
        inserted = 0
        updated  = 0

        for i, row in enumerate(rows):
            vec = embeddings[i].astype(np.float32)

            existing = DiseaseCatalog.query.filter_by(
                disease_name=row['disease_name']
            ).first()

            if existing:
                existing.icd_code       = row['icd_code']
                existing.short_desc     = row['short_desc']
                existing.embedding_blob = vec.tobytes()
                updated += 1
            else:
                db.session.add(DiseaseCatalog(
                    disease_name    = row['disease_name'],
                    icd_code        = row['icd_code'],
                    short_desc      = row['short_desc'],
                    embedding_blob  = vec.tobytes(),
                ))
                inserted += 1

        db.session.commit()
        print(f'Done — {inserted} inserted, {updated} updated.')
        print(f'Total diseases in DB: {DiseaseCatalog.query.count()}')

        # ── Verify dimension ───────────────────────────────────────────────
        d = DiseaseCatalog.query.first()
        if d and d.embedding_blob:
            dim = len(d.embedding_blob) // 4
            print(f'Stored embedding dimension: {dim}')
            assert dim == 384, f'Expected 384 dims, got {dim}'
            print('✓ Dimension check passed.')


if __name__ == '__main__':
    main()