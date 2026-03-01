"""
app/labs/extractor.py

Extracts structured lab values from confirmed document chunks using Ollama.
Called automatically when the patient confirms extracted text in the review step.

Key design decisions:
- Normalises test names to a canonical set so cross-session trends work
- Stores both numeric value (float) and raw string
- Runs per-upload, idempotent (deletes old values for that upload before re-extracting)
- Falls back to regex extraction if Ollama is unavailable
"""

import json
import os
import re
from datetime import datetime, timezone

import requests

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT  = int(os.environ.get("OLLAMA_TIMEOUT", "90"))

# ── Canonical test name mapping ────────────────────────────────────────────────
# Maps common variations → normalised name used in DB and charts
CANONICAL_NAMES: dict[str, str] = {
    # Blood sugar
    "hba1c": "HbA1c", "hemoglobin a1c": "HbA1c", "glycated hemoglobin": "HbA1c",
    "a1c": "HbA1c", "hb a1c": "HbA1c",
    "glucose": "Glucose", "blood glucose": "Glucose", "blood sugar": "Glucose",
    "fasting glucose": "Fasting Glucose", "fasting blood sugar": "Fasting Glucose",
    "rbs": "Random Blood Sugar", "random blood sugar": "Random Blood Sugar",
    # Lipids
    "total cholesterol": "Total Cholesterol", "cholesterol": "Total Cholesterol",
    "ldl": "LDL Cholesterol", "ldl cholesterol": "LDL Cholesterol",
    "ldl-c": "LDL Cholesterol",
    "hdl": "HDL Cholesterol", "hdl cholesterol": "HDL Cholesterol",
    "hdl-c": "HDL Cholesterol",
    "triglycerides": "Triglycerides", "tg": "Triglycerides",
    "vldl": "VLDL Cholesterol",
    # Kidney
    "creatinine": "Creatinine", "serum creatinine": "Creatinine",
    "urea": "Blood Urea", "blood urea": "Blood Urea", "bun": "Blood Urea Nitrogen",
    "blood urea nitrogen": "Blood Urea Nitrogen",
    "egfr": "eGFR", "estimated gfr": "eGFR",
    "uric acid": "Uric Acid",
    # Liver
    "alt": "ALT", "sgpt": "ALT", "alanine aminotransferase": "ALT",
    "ast": "AST", "sgot": "AST", "aspartate aminotransferase": "AST",
    "bilirubin": "Total Bilirubin", "total bilirubin": "Total Bilirubin",
    "direct bilirubin": "Direct Bilirubin",
    "alkaline phosphatase": "Alkaline Phosphatase", "alp": "Alkaline Phosphatase",
    # Blood count
    "hemoglobin": "Hemoglobin", "hb": "Hemoglobin", "haemoglobin": "Hemoglobin",
    "hematocrit": "Hematocrit", "pcv": "Hematocrit",
    "wbc": "WBC", "white blood cells": "WBC", "white blood cell count": "WBC",
    "rbc": "RBC", "red blood cells": "RBC", "red blood cell count": "RBC",
    "platelets": "Platelets", "platelet count": "Platelets",
    "mcv": "MCV", "mch": "MCH", "mchc": "MCHC",
    # Thyroid
    "tsh": "TSH", "thyroid stimulating hormone": "TSH",
    "t3": "T3", "t4": "T4", "free t3": "Free T3", "free t4": "Free T4",
    # Electrolytes
    "sodium": "Sodium", "na": "Sodium",
    "potassium": "Potassium", "k": "Potassium",
    "chloride": "Chloride", "cl": "Chloride",
    "calcium": "Calcium", "ca": "Calcium",
    # Vitamins / minerals
    "vitamin d": "Vitamin D", "25-oh vitamin d": "Vitamin D",
    "vitamin b12": "Vitamin B12", "b12": "Vitamin B12",
    "ferritin": "Ferritin", "iron": "Serum Iron",
    # Vitals
    "blood pressure": "Blood Pressure",
    "systolic": "Systolic BP", "diastolic": "Diastolic BP",
    "pulse": "Heart Rate", "heart rate": "Heart Rate",
    "weight": "Weight", "bmi": "BMI",
    # Protein
    "total protein": "Total Protein", "albumin": "Albumin", "globulin": "Globulin",
    # Inflammatory
    "crp": "CRP", "c-reactive protein": "CRP",
    "esr": "ESR", "erythrocyte sedimentation rate": "ESR",
}


def normalise_name(raw: str) -> str:
    """Map raw test name to canonical name. Returns Title Case if unknown."""
    key = raw.strip().lower()
    return CANONICAL_NAMES.get(key, raw.strip().title())


def _parse_numeric(val_str: str) -> float | None:
    """Extract first number from a string like '5.8 %' or '< 200'."""
    match = re.search(r"[\d]+\.?[\d]*", val_str.replace(",", ""))
    return float(match.group()) if match else None


def _parse_status(status_str: str) -> str:
    s = status_str.strip().lower()
    if s in ("high", "h", "above normal", "elevated", "↑"):
        return "high"
    if s in ("low", "l", "below normal", "↓"):
        return "low"
    if s in ("normal", "n", "within range", "within normal limits"):
        return "normal"
    return "unknown"


# ── Ollama extraction ──────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """You are a medical data extractor. Extract ALL lab test results from the text below.

Return ONLY a JSON array. Each item must have:
- "test_name": string (exact name as in the report)
- "value": string (the result value including units if given)
- "unit": string or null
- "reference_range": string or null (e.g. "4.0-5.6" or "< 200")
- "status": string or null ("Normal", "High", "Low", or null if not stated)
- "report_date": string or null (YYYY-MM-DD format if a date is visible)

Rules:
- Extract every numeric result you can find
- If no lab values are present, return []
- Return ONLY the JSON array, no other text

Text:
{text}

JSON array:"""


def extract_from_chunks(
    chunks: list[str],
    session_id: int,
    upload_id: int,
    user_id: int,
) -> list[dict]:
    """
    Extract lab values from a list of text chunks.
    Returns a list of dicts ready to insert as LabValue rows.
    Does NOT write to DB — caller is responsible.
    """
    all_text = "\n\n".join(chunks)

    # Try Ollama first
    raw_results = _extract_via_ollama(all_text)

    # Fall back to regex if Ollama fails or returns nothing useful
    if not raw_results:
        raw_results = _extract_via_regex(all_text)

    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for item in raw_results:
        raw_name = item.get("test_name", "").strip()
        if not raw_name:
            continue

        raw_val = str(item.get("value", "") or "").strip()
        numeric = _parse_numeric(raw_val)
        status_raw = item.get("status") or ""
        status = _parse_status(status_raw) if status_raw else "unknown"

        rows.append({
            "user_id":         user_id,
            "session_id":      session_id,
            "upload_id":       upload_id,
            "test_name":       normalise_name(raw_name),
            "value":           numeric,
            "unit":            (item.get("unit") or "").strip() or None,
            "raw_value":       raw_val or None,
            "reference_range": (item.get("reference_range") or "").strip() or None,
            "status":          status,
            "report_date":     item.get("report_date") or None,
            "created_at":      now,
        })

    return rows


def _extract_via_ollama(text: str) -> list[dict]:
    prompt = EXTRACTION_PROMPT.format(text=text[:3000])  # cap to avoid timeout
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 800},
    }

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

        # Strip markdown fences
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, requests.RequestException, Exception) as e:
        print(f"[labs] Ollama extraction failed: {e} — falling back to regex")

    return []


# ── Regex fallback ─────────────────────────────────────────────────────────────

# Matches patterns like:
#   Hemoglobin    12.5   g/dL   (10.0-14.5)   Normal
#   HbA1c: 7.2%
LAB_PATTERN = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9\s\-/\.]{2,30}?)"  # test name
    r"[\s:]+?"
    r"(?P<value>[\d]+\.?[\d]*)"                       # numeric value
    r"\s*(?P<unit>%|g/dL|mg/dL|mmol/L|U/L|mEq/L|"
    r"IU/L|ng/mL|pg/mL|μIU/mL|mIU/L|mm/hr|"
    r"cells/μL|K/μL|M/μL|fL|pg|g/L|nmol/L|"
    r"pmol/L|μmol/L|mmHg|bpm|kg|kg/m2)?"
    r"(?:\s*[\(\[]"
    r"(?P<ref>[^\)\]]+)"
    r"[\)\]])?"
    r"(?:\s+(?P<status>Normal|High|Low|H|L|N))?",
    re.IGNORECASE,
)

# Known non-test words to filter out
_SKIP_NAMES = {
    "date", "time", "name", "age", "sex", "id", "ref", "page",
    "collected", "reported", "doctor", "patient", "lab", "test",
    "result", "value", "unit", "range", "status", "method",
}


def _extract_via_regex(text: str) -> list[dict]:
    results = []
    for m in LAB_PATTERN.finditer(text):
        name = m.group("name").strip().rstrip(":").strip()
        if name.lower() in _SKIP_NAMES or len(name) < 2:
            continue
        results.append({
            "test_name":       name,
            "value":           m.group("value"),
            "unit":            m.group("unit") or None,
            "reference_range": m.group("ref") or None,
            "status":          m.group("status") or None,
            "report_date":     None,
        })
    return results


# ── DB write helper ────────────────────────────────────────────────────────────

def save_lab_values(rows: list[dict], upload_id: int) -> int:
    """
    Upsert lab values for an upload. Deletes old values for this upload first.
    Must be called inside a Flask app context.
    Returns count of rows saved.
    """
    from ..extensions import db
    from ..models import LabValue

    # Delete existing values for this upload (idempotent re-extraction)
    LabValue.query.filter_by(upload_id=upload_id).delete()

    for row in rows:
        db.session.add(LabValue(**row))

    db.session.commit()
    return len(rows)