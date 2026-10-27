"""pipeline.py — the Claude steps: extract risk data, find gaps, draft the
request email, extract carrier quotes, compose the offer.

Every extracted fact carries a "src" (file name + page) so the final offer
can list its sources. Sources are produced by Claude and must be checked by
the broker before anything is sent.
"""
from __future__ import annotations

import json
import os
import re
import time

import anthropic

from config import MAX_RETRIES, MAX_TOKENS, MODEL

# ── Single source of truth for the intake form ──────────────────────────────
# (key, Greek label, required)
FIELDS: list[tuple[str, str, bool]] = [
    ("applicant_name", "Επωνυμία ασφαλιζόμενου", True),
    ("applicant_afm", "ΑΦΜ / ΔΟΥ", True),
    ("applicant_address", "Έδρα", True),
    ("applicant_phone", "Τηλέφωνο", True),
    ("applicant_email", "Email", True),
    ("applicant_website", "Ιστοσελίδα", False),
    ("year_established", "Έτος ίδρυσης", True),
    ("staff_engineers", "Αριθμός μηχανικών", True),
    ("staff_architects", "Αριθμός αρχιτεκτόνων", True),
    ("staff_draughtsmen", "Σχεδιαστές", False),
    ("staff_trainees", "Εκπαιδευόμενοι", False),
    ("staff_admin", "Διοικητικό προσωπικό", False),
    ("turnover_prev", "Αμοιβές/κύκλος εργασιών προηγούμενου έτους", True),
    ("turnover_current", "Αμοιβές/κύκλος εργασιών τρέχοντος έτους", True),
    ("turnover_next", "Εκτίμηση επόμενου έτους", True),
    ("activity_split", "Ποσοστά δραστηριότητας (μελέτη/επίβλεψη/διαχείριση έργου)", True),
    ("subcontracting", "Υπεργολαβίες / εξωτερικοί σύμβουλοι (είδος, % αμοιβών)", True),
    ("financial_link_to_employer", "Οικονομική σύνδεση με εργοδότη/εργολάβο", True),
    ("project_employer", "Εργοδότης / κύριος του έργου", True),
    ("project_contractor", "Εργολάβος / κοινοπραξία", False),
    ("project_location", "Τοποθεσία έργου", True),
    ("project_type", "Είδος και σκοπός έργου", True),
    ("project_fee", "Αμοιβές για το έργο", True),
    ("project_construction_budget", "Προϋπολογισμός κατασκευής", True),
    ("project_start", "Έναρξη υπηρεσιών", True),
    ("project_end", "Λήξη υπηρεσιών / παράδοση", True),
    ("services_stages", "Στάδια υπηρεσιών", True),
    ("statutory_supervision", "Νόμιμη επίβλεψη (ναι/όχι)", True),
    ("structural_works_included", "Στατικές μελέτες/εργασίες (ναι/όχι)", True),
    ("project_management_included", "Project management / κατασκευή (ναι/όχι)", True),
    ("adjacent_property_risks", "Παρακείμενες ιδιοκτησίες / ρίσκα (εκσκαφές, δονήσεις)", False),
    ("limit_per_event", "Όριο ανά γεγονός (€)", True),
    ("limit_aggregate", "Ανώτατο όριο ευθύνης (€)", True),
    ("deductible_preference", "Επιθυμητή απαλλαγή", False),
    ("erp_months_requested", "Εκτεταμένη περίοδος αναγγελίας (μήνες, επιθυμητές επιλογές)", True),
    ("loss_of_documents_limit", "Απώλεια εγγράφων (όριο)", False),
    ("period_start", "Έναρξη ασφάλισης", True),
    ("period_end", "Λήξη ασφάλισης", True),
    ("previous_insurance", "Προηγούμενη/τρέχουσα ασφάλιση ευθύνης (εταιρεία, όριο, αναδρομική ισχύς)", True),
    ("claims_history_5y", "Ιστορικό ζημιών/απαιτήσεων 5ετίας", True),
    ("known_circumstances", "Γνωστά περιστατικά που μπορεί να οδηγήσουν σε αξίωση", True),
    ("contract_provided", "Παραδόθηκε το πλήρες κείμενο σύμβασης/RfP", True),
]
FIELD_KEYS = [k for k, _, _ in FIELDS]
_LABEL = {k: l for k, l, _ in FIELDS}
_REQUIRED = {k for k, _, r in FIELDS if r}

_UNKNOWN = {"", "unknown", "άγνωστο", "n/a", "null", "none"}

SYSTEM = (
    "Είσαι βοηθός ασφαλιστικού μεσίτη (Ashlar Insurance, Αθήνα) για ασφάλιση "
    "επαγγελματικής ευθύνης αρχιτεκτόνων/μηχανικών. Βασίζεσαι ΜΟΝΟ στα "
    "έγγραφα και τις σημειώσεις που σου δίνονται. Δεν επινοείς στοιχεία, "
    "αριθμούς ή όρους. Όταν κάτι δεν αναφέρεται, το δηλώνεις ως άγνωστο. "
    "Κάθε στοιχείο συνοδεύεται από πηγή (όνομα αρχείου και σελίδα, ή "
    "«σημειώσεις»). Απαντάς στα ελληνικά, εκτός αν ζητηθεί αλλιώς."
)


# ── helpers ─────────────────────────────────────────────────────────────────

def make_client(api_key: str | None = None) -> anthropic.Anthropic:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("Claude_API_Key")
    if not key:
        raise RuntimeError("Λείπει το ANTHROPIC_API_KEY.")
    return anthropic.Anthropic(api_key=key)


def ask(client, instruction: str, blocks: list | None = None,
        system: str = SYSTEM, max_tokens: int = MAX_TOKENS) -> str:
    content = list(blocks or []) + [{"type": "text", "text": instruction}]
    last: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=MODEL, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": content}],
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        except (anthropic.RateLimitError, anthropic.APIConnectionError,
                anthropic.InternalServerError) as e:
            last = e
            time.sleep(5 * 2 ** attempt)
    raise last  # type: ignore[misc]


def parse_json(text: str) -> dict:
    """Extract the outermost JSON object from a model reply."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"Δεν βρέθηκε JSON στην απάντηση: {text[:200]!r}")
    return json.loads(t[start:end + 1])


def is_unknown(v) -> bool:
    if v is None:
        return True
    return isinstance(v, str) and v.strip().lower() in _UNKNOWN


# ── step 1: extract risk data ───────────────────────────────────────────────

def extract_risk(client, blocks: list, notes: str = "") -> dict:
    skeleton = {k: {"v": None, "src": None} for k in FIELD_KEYS}
    instruction = f"""Από τα έγγραφα και τις σημειώσεις εξήγαγε τα στοιχεία κινδύνου για προσφορά
ασφάλισης επαγγελματικής ευθύνης. Επίστρεψε ΜΟΝΟ JSON με αυτή τη δομή:

{{
  "fields": {json.dumps(skeleton, ensure_ascii=False)},
  "people": [{{"name": "", "qualification": "", "position_since": "", "src": ""}}],
  "past_projects": [{{"description": "", "location": "", "fee": "", "src": ""}}],
  "contract_flags": [{{"issue": "", "detail": "", "src": ""}}]
}}

Κανόνες:
- "v" = η τιμή όπως αναφέρεται, "src" = «αρχείο, σελ. N» ή «σημειώσεις». Άγνωστο → {{"v": null, "src": null}}.
- Τα πεδία είναι: {", ".join(f"{k} ({_LABEL[k]})" for k in FIELD_KEYS)}.
- "contract_flags": σύγκρινε τις ασφαλιστικές απαιτήσεις της σύμβασης (ρήτρες αποζημίωσης,
  απαιτούμενο όριο/διάρκεια, ευθύνη υποσυμβούλων, συμβατική ευθύνη) με τα συνήθη όρια ενός
  συμβολαίου επαγγελματικής ευθύνης (ευθύνη εκ του νόμου, claims-made, εξαιρέσεις
  συμβατικής/αμιγώς οικονομικής ζημιάς) και κατέγραψε κάθε πιθανό κενό. Μόνο με βάση το κείμενο.
- Μην αντιγράφεις ονόματα ή στοιχεία τρίτων πελατών που τυχόν εμφανίζονται ως παραδείγματα.

Σημειώσεις μεσίτη:
{notes or "(καμία)"}"""
    data = parse_json(ask(client, instruction, blocks))
    fields = data.get("fields", {})
    for k in FIELD_KEYS:
        fields.setdefault(k, {"v": None, "src": None})
    data["fields"] = fields
    data.setdefault("people", [])
    data.setdefault("past_projects", [])
    data.setdefault("contract_flags", [])
    return data


def missing_fields(risk: dict) -> dict[str, list[dict]]:
    """Deterministic gap check. Returns {'required': [...], 'optional': [...]}."""
    out: dict[str, list[dict]] = {"required": [], "optional": []}
    for k, label, req in FIELDS:
        cell = risk.get("fields", {}).get(k) or {}
        if is_unknown(cell.get("v")):
            out["required" if req else "optional"].append({"key": k, "label": label})
    if not risk.get("people"):
        out["required"].append({"key": "people", "label": "Εταίροι/συνεργάτες (ονόματα, ειδικότητα, έτη εμπειρίας)"})
    if not risk.get("past_projects"):
        out["required"].append({"key": "past_projects", "label": "3–4 μεγαλύτερα έργα της 5ετίας"})
    return out


# ── step 2: request email ───────────────────────────────────────────────────

def draft_request_email(client, risk: dict, missing: dict, extra: str = "") -> dict:
    items = missing["required"] + missing["optional"]
    instruction = f"""Γράψε email από τον ασφαλιστικό μεσίτη προς τον αρχιτέκτονα/μηχανικό (πελάτη) που ζητά
τα στοιχεία που λείπουν για να ζητηθούν προσφορές επαγγελματικής ευθύνης.

Στοιχεία που λείπουν (αριθμημένη λίστα, ξεχώρισε τα προαιρετικά):
{json.dumps(items, ensure_ascii=False)}

Στοιχεία που ήδη έχουμε (μην τα ξαναζητήσεις):
{json.dumps({k: v.get("v") for k, v in risk.get("fields", {}).items() if not is_unknown(v.get("v"))}, ensure_ascii=False)}

Πιθανά κενά σύμβασης που αξίζει να δει με τον νομικό του:
{json.dumps(risk.get("contract_flags", []), ensure_ascii=False)}

Οδηγίες: ευγενικό, σύντομο, επαγγελματικό. Εξήγησε σε 2–3 προτάσεις ότι η ασφάλιση είναι
claims-made και ότι η εκτεταμένη περίοδος αναγγελίας (ΕΠΑ) κοστίζει διαφορετικά ανά
διάρκεια, γι' αυτό ζητάμε τιμές ξεχωριστά. ΜΗΝ αναφέρεις άλλους πελάτες, εταιρείες ή
ονόματα. Άφησε υπογραφή με placeholder [Όνομα μεσίτη].
{extra}

Επίστρεψε ΜΟΝΟ JSON: {{"subject": "...", "body": "..."}} (body σε απλό κείμενο)."""
    data = parse_json(ask(client, instruction, max_tokens=3000))
    return {"subject": data.get("subject", ""), "body": data.get("body", "")}


# ── step 3: carrier quotes ──────────────────────────────────────────────────

QUOTE_KEYS = ["insurer", "total_premium", "limit_per_event", "limit_aggregate", "deductible",
              "period", "erp", "trigger", "territory", "validity", "key_exclusions",
              "conditions", "src"]


def extract_quotes(client, blocks: list) -> list[dict]:
    instruction = f"""Κάθε έγγραφο είναι προσφορά ασφαλιστικής εταιρείας (μπορεί να έχει εναλλακτικές,
π.χ. διαφορετικές απαλλαγές ή ΕΠΑ). Επίστρεψε ΜΟΝΟ JSON:
{{"quotes": [{{"insurer": "", "variant": "", "total_premium": "", "limit_per_event": "",
"limit_aggregate": "", "deductible": "", "period": "", "erp": "", "trigger": "",
"territory": "", "validity": "", "key_exclusions": [""], "conditions": [""], "src": "αρχείο, σελ. N"}}]}}

Μία εγγραφή ανά εναλλακτική. Τα ποσά ακριβώς όπως γράφονται (με το νόμισμα). "total_premium"
= ολικά/μικτά ασφάλιστρα. Στις εξαιρέσεις βάλε μόνο όσες αγγίζουν μελέτη/επίβλεψη/ανακαίνιση,
συμβατική ή οικονομική ευθύνη, διαχείριση έργου, υπέρβαση κόστους, προθεσμίες. Άγνωστο → null.
ΜΗΝ υπολογίσεις ή συμπεράνεις ασφάλιστρα που δεν αναγράφονται."""
    data = parse_json(ask(client, instruction, blocks))
    quotes = data.get("quotes", [])
    for q in quotes:
        for k in QUOTE_KEYS:
            q.setdefault(k, None)
    return quotes


# ── step 4: compose the offer ───────────────────────────────────────────────

def compose_offer(client, risk: dict, quotes: list[dict], broker_notes: str = "") -> dict:
    facts = {k: v.get("v") for k, v in risk.get("fields", {}).items() if not is_unknown(v.get("v"))}
    instruction = f"""Σύνθεσε το περιεχόμενο προσφοράς/σύγκρισης για τον πελάτη (αρχιτέκτονα).

Στοιχεία πελάτη/έργου: {json.dumps(facts, ensure_ascii=False)}
Πιθανά κενά σύμβασης: {json.dumps(risk.get("contract_flags", []), ensure_ascii=False)}
Προσφορές εταιρειών: {json.dumps(quotes, ensure_ascii=False)}
Σημειώσεις μεσίτη: {broker_notes or "(καμία)"}

Επίστρεψε ΜΟΝΟ JSON:
{{
  "headline": "",
  "intro": "2-3 προτάσεις",
  "recommendation": {{"insurer": "", "variant": "", "why": ""}},
  "comparison": [{{"criterion": "", "cells": ["ανά προσφορά, με την ίδια σειρά"]}}],
  "warnings": [{{"title": "", "detail": "", "src": ""}}],
  "next_steps": [""],
  "sources": [{{"fact": "", "src": ""}}]
}}

Κανόνες: χρησιμοποίησε αποκλειστικά τα δοθέντα στοιχεία· τα ποσά να ταυτίζονται με τις προσφορές·
κριτήρια σύγκρισης: ασφάλιστρα, όριο, απαλλαγή, ΕΠΑ, trigger, περίοδος, ισχύς προσφοράς, σημαντικές
εξαιρέσεις· στα "warnings" ανέφερε κενά ανάμεσα στη σύμβαση και στην κάλυψη, αντιφάσεις μέσα στις
προσφορές (π.χ. κάλυψη έργου vs εξαίρεση εργασιών ανακαίνισης), και λήξη ισχύος προσφορών· η
σύσταση είναι ενδεικτική και όχι δεσμευτική· κάθε στοιχείο στα "sources" με αρχείο/σελίδα."""
    data = parse_json(ask(client, instruction))
    for k, default in (("comparison", []), ("warnings", []), ("next_steps", []), ("sources", [])):
        data.setdefault(k, default)
    data.setdefault("recommendation", {})
    return data
