"""
scripts/enrich_disease_catalog.py

Generates plain-English short descriptions for all conditions in
disease_catalog_v2_raw.csv that are missing one, using Ollama.

Run:
    python scripts/enrich_disease_catalog.py
    python scripts/enrich_disease_catalog.py --resume   # continue after interrupt

Output: data/disease_catalog_v2.csv (ready to seed)
Estimated time: ~20 minutes for 600 conditions with llama3.2:3b
"""

import argparse
import csv
import json
import os
import time

import requests

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT  = int(os.environ.get("OLLAMA_TIMEOUT", "60"))

INPUT_PATH    = os.path.join("data", "disease_catalog_v2_raw.csv")
OUTPUT_PATH   = os.path.join("data", "disease_catalog_v2.csv")
PROGRESS_PATH = os.path.join("data", "enrich_progress.json")

BATCH_SIZE = 8


def ask_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 120},
    }
    resp = requests.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json=payload,
        timeout=OLLAMA_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def enrich_batch(rows: list[dict]) -> list[str]:
    """
    Ask Ollama for a plain-English 1-2 sentence description for each condition.
    Returns a list of descriptions in the same order.
    """
    names = [r["disease_name"] for r in rows]
    numbered = "\n".join(f"{i+1}. {name}" for i, name in enumerate(names))

    prompt = (
        "You are a medical writer. For each condition below, write a single "
        "plain-English sentence (max 20 words) that a patient can understand. "
        "Describe what the condition is — no jargon, no diagnosis advice.\n\n"
        f"{numbered}\n\n"
        "Reply with ONLY a JSON array of strings, one per condition, "
        "in the same order. Example: [\"Desc 1\", \"Desc 2\"]\n"
        "JSON array:"
    )

    raw = ask_ollama(prompt)

    # Strip markdown fences
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        result = json.loads(raw)
        if isinstance(result, list) and len(result) == len(rows):
            return [str(s).strip() for s in result]
    except json.JSONDecodeError:
        pass

    # Fallback: one at a time
    descriptions = []
    for row in rows:
        try:
            single_prompt = (
                f"In one plain-English sentence (max 20 words), what is "
                f"'{row['disease_name']}'? Patient-friendly, no jargon.\n"
                "Sentence:"
            )
            desc = ask_ollama(single_prompt)
            # Clean up — take first sentence only
            desc = desc.split(".")[0].strip() + "."
            descriptions.append(desc)
        except Exception:
            descriptions.append("")
    return descriptions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true",
                        help="Resume from saved progress")
    args = parser.parse_args()

    # Load input
    rows = []
    with open(INPUT_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} conditions from {INPUT_PATH}")

    # Load progress if resuming
    completed = {}  # icd_code -> short_desc
    if args.resume and os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, encoding="utf-8") as f:
            completed = json.load(f)
        print(f"Resuming — {len(completed)} already done")

    # Work out which need enrichment
    to_enrich = [
        r for r in rows
        if not r.get("short_desc") and r["icd_code"] not in completed
    ]
    print(f"Need enrichment: {len(to_enrich)}")

    # Test Ollama connection
    try:
        requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        print(f"Ollama reachable at {OLLAMA_BASE_URL}")
    except Exception:
        print(f"ERROR: Ollama not reachable at {OLLAMA_BASE_URL}")
        print("Start it with: ollama serve")
        return

    # Process in batches
    total_batches = (len(to_enrich) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_num in range(total_batches):
        batch = to_enrich[batch_num * BATCH_SIZE:(batch_num + 1) * BATCH_SIZE]
        print(f"Batch {batch_num + 1}/{total_batches} "
              f"({batch[0]['disease_name'][:40]}...)")

        try:
            descs = enrich_batch(batch)
            for row, desc in zip(batch, descs):
                completed[row["icd_code"]] = desc
        except Exception as e:
            print(f"  Batch failed: {e} — skipping")
            for row in batch:
                completed[row["icd_code"]] = ""

        # Save progress after every batch
        with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump(completed, f, ensure_ascii=False, indent=2)

        time.sleep(0.2)  # small pause between batches

    # Merge everything into output
    output_rows = []
    for row in rows:
        out = dict(row)
        if not out.get("short_desc"):
            out["short_desc"] = completed.get(row["icd_code"], "")
        output_rows.append(out)

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["icd_code", "disease_name", "chapter",
                           "synonyms", "short_desc"]
        )
        writer.writeheader()
        writer.writerows(output_rows)

    filled = sum(1 for r in output_rows if r["short_desc"])
    print(f"\nDone — {filled}/{len(output_rows)} conditions have descriptions")
    print(f"Output saved to {OUTPUT_PATH}")

    # Clean up progress file
    if os.path.exists(PROGRESS_PATH):
        os.remove(PROGRESS_PATH)


if __name__ == "__main__":
    main()
