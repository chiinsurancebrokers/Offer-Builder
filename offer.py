"""offer.py — render the offer as an email-safe HTML page and as a PDF.

One template serves both: table layout and inline styles for email clients,
plus a print stylesheet that WeasyPrint uses for the PDF. The last section is
always the sources annex.
"""
from __future__ import annotations

from datetime import date

from jinja2 import Environment, select_autoescape

from config import BROKER, GOLD, INK, NAVY

_env = Environment(autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)

TEMPLATE = _env.from_string("""<!DOCTYPE html>
<html lang="el">
<head>
<meta charset="utf-8">
<title>{{ c.headline or "Προσφορά ασφάλισης" }}</title>
<style>
  @page { size: A4; margin: 18mm 16mm; }
  body { font-family: 'DejaVu Sans', 'Noto Sans', Arial, sans-serif; color: {{ ink }}; font-size: 13px; line-height: 1.5; }
  table { border-collapse: collapse; }
  th, td { vertical-align: top; }
  tr { page-break-inside: avoid; }
</style>
</head>
<body style="margin:0;padding:0;background:#f4f1ec;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ec;">
<tr><td align="center" style="padding:16px;">
<table role="presentation" width="720" cellpadding="0" cellspacing="0" style="max-width:720px;width:100%;background:#ffffff;">

  <tr><td style="background:{{ navy }};padding:22px 28px;border-bottom:4px solid {{ gold }};">
    <div style="color:{{ gold }};font-size:11px;letter-spacing:3px;text-transform:uppercase;">{{ broker.company }}</div>
    <div style="color:#ffffff;font-size:21px;font-weight:bold;margin-top:6px;">{{ c.headline or "Προσφορά ασφάλισης επαγγελματικής ευθύνης" }}</div>
    <div style="color:#c9d6e2;font-size:12px;margin-top:4px;">{{ today }}{% if client_name %} · {{ client_name }}{% endif %}</div>
  </td></tr>

  <tr><td style="padding:24px 28px 8px;">
    <p style="margin:0 0 12px;">{{ c.intro }}</p>
  </td></tr>

  {% if rec and rec.insurer %}
  <tr><td style="padding:0 28px 16px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#faf6ee;border-left:4px solid {{ gold }};">
      <tr><td style="padding:14px 16px;">
        <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#7a6a5a;">Ενδεικτική σύσταση</div>
        <div style="font-size:16px;font-weight:bold;margin:4px 0;">{{ rec.insurer }}{% if rec.variant %} — {{ rec.variant }}{% endif %}</div>
        <div>{{ rec.why }}</div>
      </td></tr>
    </table>
  </td></tr>
  {% endif %}

  {% if quotes %}
  <tr><td style="padding:8px 28px 4px;font-size:14px;font-weight:bold;color:{{ navy }};">Σύγκριση προσφορών</td></tr>
  <tr><td style="padding:0 28px 16px;">
    <table width="100%" cellpadding="6" cellspacing="0" style="border:1px solid #d9d2c6;font-size:12px;">
      <tr style="background:{{ navy }};color:#ffffff;">
        <th align="left" style="border:1px solid #d9d2c6;">Κριτήριο</th>
        {% for q in quotes %}
        <th align="left" style="border:1px solid #d9d2c6;">{{ q.insurer }}{% if q.variant %}<br><span style="font-weight:normal;">{{ q.variant }}</span>{% endif %}</th>
        {% endfor %}
      </tr>
      {% for row in c.comparison %}
      <tr style="background:{{ '#ffffff' if loop.index is odd else '#faf8f4' }};">
        <td style="border:1px solid #d9d2c6;font-weight:bold;">{{ row.criterion }}</td>
        {% for cell in row.cells %}
        <td style="border:1px solid #d9d2c6;">{{ cell }}</td>
        {% endfor %}
      </tr>
      {% endfor %}
    </table>
  </td></tr>
  {% endif %}

  {% if c.warnings %}
  <tr><td style="padding:8px 28px 4px;font-size:14px;font-weight:bold;color:#b45309;">Σημεία προσοχής</td></tr>
  <tr><td style="padding:0 28px 16px;">
    {% for w in c.warnings %}
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:8px;background:#fff7ed;border-left:4px solid #e67e22;">
      <tr><td style="padding:10px 14px;">
        <div style="font-weight:bold;">{{ w.title }}</div>
        <div>{{ w.detail }}</div>
        {% if w.src %}<div style="font-size:11px;color:#7a6a5a;margin-top:2px;">Πηγή: {{ w.src }}</div>{% endif %}
      </td></tr>
    </table>
    {% endfor %}
  </td></tr>
  {% endif %}

  {% if c.next_steps %}
  <tr><td style="padding:8px 28px 4px;font-size:14px;font-weight:bold;color:{{ navy }};">Επόμενα βήματα</td></tr>
  <tr><td style="padding:0 28px 16px;">
    <ol style="margin:0;padding-left:20px;">
      {% for s in c.next_steps %}<li style="margin-bottom:4px;">{{ s }}</li>{% endfor %}
    </ol>
  </td></tr>
  {% endif %}

  <tr><td style="padding:8px 28px 20px;font-size:11px;color:#7a6a5a;">
    Η παρούσα σύσταση είναι ενδεικτική και δεν αποτελεί δέσμευση ή βεβαίωση ασφαλιστικής κάλυψης.
    Η κάλυψη ισχύει μόνο με την έκδοση του ασφαλιστηρίου. Οι τιμές και οι όροι προέρχονται από τις
    προσφορές των εταιρειών και ισχύουν για το διάστημα που αναγράφεται σε αυτές.
  </td></tr>

  <tr><td style="padding:0 28px 8px;border-top:1px solid #e8e0d5;font-size:14px;font-weight:bold;color:{{ navy }};padding-top:16px;">Πηγές</td></tr>
  <tr><td style="padding:0 28px 20px;">
    <table width="100%" cellpadding="5" cellspacing="0" style="border:1px solid #e8e0d5;font-size:11px;">
      <tr style="background:#f4f1ec;"><th align="left" style="border:1px solid #e8e0d5;">Στοιχείο</th><th align="left" style="border:1px solid #e8e0d5;">Πηγή (αρχείο, σελίδα)</th></tr>
      {% for s in sources %}
      <tr><td style="border:1px solid #e8e0d5;">{{ s.fact }}</td><td style="border:1px solid #e8e0d5;">{{ s.src }}</td></tr>
      {% endfor %}
    </table>
    {% if documents %}
    <div style="font-size:11px;color:#7a6a5a;margin-top:8px;">Έγγραφα που εξετάστηκαν: {{ documents | join(", ") }}</div>
    {% endif %}
  </td></tr>

  <tr><td style="background:{{ navy }};padding:14px 28px;color:#c9d6e2;font-size:12px;">
    <strong style="color:#ffffff;">{{ broker.company }}</strong>{% if broker.name %} · {{ broker.name }}{% endif %}<br>
    {% if broker.tel %}{{ broker.tel }} · {% endif %}{% if broker.email %}{{ broker.email }} · {% endif %}{{ broker.web }}
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>
""")


def _merge_sources(content: dict, quotes: list[dict]) -> list[dict]:
    """Model-listed sources + one line per quote, de-duplicated."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []

    def add(fact, src):
        if not fact or not src:
            return
        key = (str(fact), str(src))
        if key not in seen:
            seen.add(key)
            out.append({"fact": fact, "src": src})

    for q in quotes:
        label = q.get("insurer") or "Προσφορά"
        if q.get("variant"):
            label += f" ({q['variant']})"
        add(f"{label}: ασφάλιστρα, όρια, εξαιρέσεις", q.get("src"))
    for s in content.get("sources", []):
        add(s.get("fact"), s.get("src"))
    for w in content.get("warnings", []):
        add(f"Σημείο προσοχής: {w.get('title')}", w.get("src"))
    return out


def render_html(content: dict, quotes: list[dict], client_name: str = "",
                documents: list[str] | None = None) -> str:
    return TEMPLATE.render(
        c=content, rec=content.get("recommendation") or {}, quotes=quotes,
        sources=_merge_sources(content, quotes), documents=documents or [],
        client_name=client_name, broker=BROKER, today=date.today().strftime("%d/%m/%Y"),
        navy=NAVY, gold=GOLD, ink=INK,
    )


def render_pdf(html: str) -> bytes:
    from weasyprint import HTML
    return HTML(string=html).write_pdf()
