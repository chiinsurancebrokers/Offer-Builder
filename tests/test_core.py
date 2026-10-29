import io
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf  # noqa: E402

import brain  # noqa: E402
import offer  # noqa: E402
import pipeline  # noqa: E402

QUOTES = [
    {"insurer": "Εταιρεία Α", "variant": "ΕΠΑ 12 μήνες", "src": "a.pdf, σελ. 1"},
    {"insurer": "Εταιρεία Β", "variant": "ΕΠΑ 48 μήνες", "src": "b.pdf, σελ. 3"},
]
CONTENT = {
    "headline": "Προσφορά ευθύνης μελετητή",
    "intro": "Σας παραθέτουμε τις προσφορές.",
    "recommendation": {"insurer": "Εταιρεία Β", "variant": "ΕΠΑ 48 μήνες", "why": "Μεγαλύτερη ΕΠΑ."},
    "comparison": [{"criterion": "Ασφάλιστρα", "cells": ["€1.170", "€3.300"]}],
    "warnings": [{"title": "Συμβατική ευθύνη", "detail": "Εξαιρείται.", "src": "b.pdf, σελ. 4"}],
    "next_steps": ["Επιβεβαίωση ΕΠΑ"],
    "sources": [{"fact": "Όριο €250.000", "src": "a.pdf, σελ. 1"}],
}


def test_html_has_sources_and_escapes():
    c = dict(CONTENT, intro="<script>alert(1)</script>")
    html = offer.render_html(c, QUOTES, client_name="Test", documents=["a.pdf", "b.pdf"])
    assert "<script>alert" not in html
    assert "Πηγές" in html and "b.pdf, σελ. 3" in html and "a.pdf, σελ. 1" in html
    assert "Σημείο προσοχής: Συμβατική ευθύνη" in html


def test_pdf_renders_greek():
    pdf = offer.render_pdf(offer.render_html(CONTENT, QUOTES))
    assert pdf.startswith(b"%PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        text = "".join(p.get_text() for p in doc)
    assert "Σύγκριση προσφορών" in text and "€3.300" in text


def test_parse_json_handles_fences_and_noise():
    assert pipeline.parse_json('Ορίστε:\n```json\n{"a": 1}\n```') == {"a": 1}


def test_missing_fields():
    risk = {"fields": {k: {"v": None, "src": None} for k in pipeline.FIELD_KEYS},
            "people": [], "past_projects": []}
    risk["fields"]["applicant_name"] = {"v": "Χ ΑΤΕΕ", "src": "σημειώσεις"}
    risk["fields"]["year_established"] = {"v": "unknown", "src": None}
    m = pipeline.missing_fields(risk)
    keys = {x["key"] for x in m["required"]}
    assert "applicant_name" not in keys
    assert "year_established" in keys and "people" in keys
    assert any(x["key"] == "applicant_website" for x in m["optional"])


def test_extract_risk_fills_defaults(monkeypatch):
    monkeypatch.setattr(pipeline, "ask", lambda *a, **k: '{"fields": {"applicant_name": {"v": "Χ", "src": "s"}}}')
    r = pipeline.extract_risk(None, [], "")
    assert set(r["fields"]) == set(pipeline.FIELD_KEYS)
    assert r["people"] == [] and r["contract_flags"] == []


def test_process_uploads_types():
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "hello")
    pdf = doc.tobytes()
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (50, 50)).save(buf, "PNG")
    files = [("q.pdf", pdf), ("p.png", buf.getvalue()), ("n.txt", "γεια".encode()),
             SimpleNamespace(name="x.csv", read=lambda: b"a,b\n1,2", seek=lambda n: None)]
    blocks, summ = brain.process_uploads(files)
    kinds = [b["type"] for b in blocks]
    assert kinds.count("document") == 3 and kinds.count("image") == 1
    assert blocks[0]["source"]["media_type"] == "application/pdf"
    assert len(summ) == 4


def test_parse_json_repairs_unescaped_quotes():
    bad = '{"a": {"v": "Εταιρεία "ΑΒΓ" ΑΤΕΕ", "src": "x.pdf, σελ. 1"}, "b": 2}'
    out = pipeline.parse_json(bad)
    assert out["b"] == 2 and "ΑΒΓ" in out["a"]["v"]
