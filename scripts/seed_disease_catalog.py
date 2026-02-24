"""
Seed the disease catalog and build TF-IDF embeddings.

Run once (and re-run whenever disease_catalog.csv changes):
    python scripts/seed_disease_catalog.py
"""
import sys
import os
import csv
import pickle
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sklearn.feature_extraction.text import TfidfVectorizer
from app import create_app
from app.extensions import db
from app.models import DiseaseCatalog


CATALOG_PATH    = os.path.join('data', 'disease_catalog.csv')
VECTORIZER_PATH = os.path.join('data', 'tfidf_vectorizer.pkl')


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

        # ── Build corpus for TF-IDF ────────────────────────────────────────
        # Each disease is represented as "name + description"
        corpus = [
            f"{r['disease_name']} {r['short_desc']}"
            for r in rows
        ]



        # ── Fit TF-IDF vectorizer ──────────────────────────────────────────
        vectorizer = TfidfVectorizer(
            analyzer='word',
            ngram_range=(1, 2),     # unigrams + bigrams
            min_df=1,
            max_features=8000,
            stop_words='english',
            sublinear_tf=True        # apply log normalization to TF
        )
        tfidf_matrix = vectorizer.fit_transform(corpus)  # shape: (N, vocab)

        print(f'TF-IDF matrix shape: {tfidf_matrix.shape}')

        # ── Save vectorizer to disk ────────────────────────────────────────
        os.makedirs('data', exist_ok=True)
        with open(VECTORIZER_PATH, 'wb') as f:
            pickle.dump(vectorizer, f)
        print(f'Vectorizer saved to {VECTORIZER_PATH}')

        # ── Upsert diseases into DB ────────────────────────────────────────
        inserted = 0
        updated  = 0

        for i, row in enumerate(rows):
            # Get dense vector for this disease
            vec = tfidf_matrix[i].toarray().astype(np.float32).flatten()

            existing = DiseaseCatalog.query.filter_by(
                disease_name=row['disease_name']
            ).first()

            if existing:
                existing.icd_code     = row['icd_code']
                existing.short_desc   = row['short_desc']
                existing.embedding_blob = vec.tobytes()
                updated += 1
            else:
                db.session.add(DiseaseCatalog(
                    disease_name    = row['disease_name'],
                    icd_code        = row['icd_code'],
                    short_desc      = row['short_desc'],
                    embedding_blob=vec.tobytes()
                ))
                inserted += 1

        db.session.commit()
        print(f'Done — {inserted} inserted, {updated} updated.')
        print(f'Total diseases in DB: {DiseaseCatalog.query.count()}')


if __name__ == '__main__':
    main()
    