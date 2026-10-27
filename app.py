"""Offer Builder — Ashlar Insurance.

Upload client documents -> extract risk data -> find gaps -> draft the request
email -> upload carrier quotes -> compose the offer (HTML email + PDF) with a
sources annex. Nothing is sent automatically; the broker reviews every step.
"""
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import auth
import offer
import pipeline
from brain import process_uploads
from config import BROKER, MODEL

st.set_page_config(page_title="Offer Builder · Ashlar", page_icon="🧾", layout="wide")


# ── auth: the whole app is behind one password (stored in Supabase), fails closed ─
REASONS = {
    "bad_password": "Λάθος κωδικός.",
    "too_short": "Ο νέος κωδικός πρέπει να έχει τουλάχιστον 12 χαρακτήρες.",
    "same_password": "Ο νέος κωδικός πρέπει να διαφέρει από τον προσωρινό.",
    "not_configured": "Δεν έχει οριστεί κωδικός στη βάση.",
}


def gate() -> None:
    if st.session_state.get("auth"):
        return
    st.title("🔒 Offer Builder")
    pending = st.session_state.get("pending_pw")
    try:
        if pending is None:
            pw = st.text_input("Κωδικός", type="password")
            if st.button("Είσοδος", type="primary"):
                res = auth.login(pw)
                if res.get("ok") and res.get("must_change"):
                    st.session_state["pending_pw"] = pw
                    st.rerun()
                elif res.get("ok"):
                    st.session_state["auth"] = True
                    st.rerun()
                elif res.get("reason") == "locked":
                    st.error(f"Πολλές αποτυχημένες προσπάθειες. Δοκίμασε ξανά σε {max(1, res.get('retry_seconds', 900) // 60)} λεπτά.")
                else:
                    st.error(REASONS.get(res.get("reason"), "Αποτυχία εισόδου."))
        else:
            st.info("Πρώτη είσοδος: όρισε τον δικό σου κωδικό (τουλάχιστον 12 χαρακτήρες).")
            n1 = st.text_input("Νέος κωδικός", type="password")
            n2 = st.text_input("Επανάληψη νέου κωδικού", type="password")
            if st.button("Αλλαγή κωδικού", type="primary"):
                if n1 != n2:
                    st.error("Οι δύο κωδικοί δεν ταιριάζουν.")
                else:
                    res = auth.change_password(pending, n1)
                    if res.get("ok"):
                        st.session_state.pop("pending_pw", None)
                        st.session_state["auth"] = True
                        st.rerun()
                    st.error(REASONS.get(res.get("reason"), "Αποτυχία αλλαγής."))
    except auth.AuthUnavailable as e:
        st.error(f"Η σύνδεση με τη βάση δεν είναι διαθέσιμη ({e}). Η εφαρμογή δεν ανοίγει χωρίς έλεγχο κωδικού.")
    st.stop()


gate()

# ── state ────────────────────────────────────────────────────────────────────
S = st.session_state
for k, v in {
    "intake_blocks": [], "intake_files": [], "risk": None, "request_email": None,
    "quote_blocks": [], "quote_files": [], "quotes": [], "offer": None, "chat": [],
}.items():
    S.setdefault(k, v)


def client():
    return pipeline.make_client()


def risk_table(risk: dict) -> pd.DataFrame:
    rows = []
    for key, label, req in pipeline.FIELDS:
        cell = risk["fields"].get(key, {})
        rows.append({"key": key, "Στοιχείο": label + (" *" if req else ""),
                     "Τιμή": "" if cell.get("v") is None else str(cell.get("v")),
                     "Πηγή": cell.get("src") or ""})
    return pd.DataFrame(rows)


with st.sidebar:
    st.markdown(f"### 🧾 Offer Builder\n{BROKER['company']}")
    st.caption(f"Μοντέλο: {MODEL}")
    if st.button("🗑 Νέα υπόθεση", use_container_width=True):
        for k in ("intake_blocks", "intake_files", "risk", "request_email", "quote_blocks",
                  "quote_files", "quotes", "offer", "chat"):
            S.pop(k, None)
        st.rerun()
    st.caption("Η σύσταση και οι πηγές παράγονται από AI. Έλεγξέ τα πριν στείλεις οτιδήποτε.")

t1, t2, t3, t4 = st.tabs(["1 · Στοιχεία πελάτη", "2 · Email αιτήματος", "3 · Προσφορά", "💬 Chat"])

# ── tab 1: intake ────────────────────────────────────────────────────────────
with t1:
    files = st.file_uploader("Έντυπα, σύμβαση/RfP, φωτογραφίες, προηγούμενες προσφορές",
                             accept_multiple_files=True, key="up_intake",
                             type=["pdf", "png", "jpg", "jpeg", "webp", "docx", "xlsx", "xls", "csv", "txt", "md"])
    notes = st.text_area("Σημειώσεις / κείμενο από τον πελάτη (επικόλλησε εδώ)", height=160, key="notes")
    if st.button("Εξαγωγή στοιχείων", type="primary", disabled=not (files or notes.strip())):
        with st.spinner("Διαβάζω τα έγγραφα..."):
            S.intake_blocks, summaries = process_uploads(files)
            S.intake_files = [n for n, _ in summaries]
            try:
                S.risk = pipeline.extract_risk(client(), S.intake_blocks, notes)
                S.request_email = None
            except Exception as e:
                st.error(f"Σφάλμα: {e}")
        for n, icon in summaries:
            st.caption(f"{icon} {n}")

    if S.risk:
        m = pipeline.missing_fields(S.risk)
        st.success(f"Λείπουν {len(m['required'])} υποχρεωτικά και {len(m['optional'])} προαιρετικά στοιχεία.")
        st.caption("Διόρθωσε ή συμπλήρωσε τιμές κατευθείαν στον πίνακα (τα * είναι υποχρεωτικά).")
        edited = st.data_editor(risk_table(S.risk), hide_index=True, use_container_width=True,
                                disabled=["key", "Στοιχείο", "Πηγή"], key="risk_editor",
                                column_config={"key": None})
        for _, row in edited.iterrows():
            cell = S.risk["fields"][row["key"]]
            val = row["Τιμή"].strip() or None
            if val != cell.get("v"):
                cell["v"] = val
                cell["src"] = "χειροκίνητα" if val else None
        if S.risk["contract_flags"]:
            st.subheader("Πιθανά κενά σύμβασης")
            for f in S.risk["contract_flags"]:
                st.warning(f"**{f.get('issue')}** — {f.get('detail')}  \n_Πηγή: {f.get('src') or '—'}_")
        with st.expander(f"Εταίροι ({len(S.risk['people'])}) και έργα ({len(S.risk['past_projects'])})"):
            st.dataframe(pd.DataFrame(S.risk["people"]), use_container_width=True)
            st.dataframe(pd.DataFrame(S.risk["past_projects"]), use_container_width=True)

# ── tab 2: request email ─────────────────────────────────────────────────────
with t2:
    if not S.risk:
        st.info("Πρώτα εξήγαγε στοιχεία στο βήμα 1.")
    else:
        extra = st.text_input("Επιπλέον οδηγία για το email (προαιρετικά)")
        if st.button("Δημιουργία email αιτήματος", type="primary"):
            with st.spinner("Γράφω το email..."):
                try:
                    S.request_email = pipeline.draft_request_email(
                        client(), S.risk, pipeline.missing_fields(S.risk), extra)
                except Exception as e:
                    st.error(f"Σφάλμα: {e}")
        if S.request_email:
            S.request_email["subject"] = st.text_input("Θέμα", S.request_email["subject"])
            S.request_email["body"] = st.text_area("Κείμενο", S.request_email["body"], height=420)
            st.download_button("⬇ Λήψη .txt", f"{S.request_email['subject']}\n\n{S.request_email['body']}",
                               file_name="email-aitimatos.txt")

# ── tab 3: offer ─────────────────────────────────────────────────────────────
with t3:
    qfiles = st.file_uploader("Προσφορές ασφαλιστικών εταιρειών (PDF)", accept_multiple_files=True,
                              key="up_quotes", type=["pdf", "docx", "png", "jpg", "jpeg"])
    if st.button("Ανάγνωση προσφορών", disabled=not qfiles):
        with st.spinner("Διαβάζω τις προσφορές..."):
            S.quote_blocks, summaries = process_uploads(qfiles)
            S.quote_files = [n for n, _ in summaries]
            try:
                S.quotes = pipeline.extract_quotes(client(), S.quote_blocks)
                S.offer = None
            except Exception as e:
                st.error(f"Σφάλμα: {e}")

    if S.quotes:
        st.caption("Έλεγξε τα ποσά με τα πρωτότυπα. Μπορείς να τα διορθώσεις εδώ.")
        qdf = pd.DataFrame([{k: (", ".join(v) if isinstance(v, list) else v) for k, v in q.items()}
                            for q in S.quotes])
        edited = st.data_editor(qdf, use_container_width=True, hide_index=True, key="quote_editor")
        for i, row in edited.iterrows():
            for k in qdf.columns:
                if k in ("key_exclusions", "conditions"):
                    S.quotes[i][k] = [x.strip() for x in str(row[k] or "").split(",") if x.strip()]
                else:
                    S.quotes[i][k] = row[k] if pd.notna(row[k]) else None

        bnotes = st.text_area("Σημειώσεις μεσίτη για τη σύσταση (π.χ. προτίμηση ΕΠΑ, προϋπολογισμός)", height=100)
        if st.button("Σύνθεση προσφοράς", type="primary"):
            with st.spinner("Συνθέτω την προσφορά..."):
                try:
                    S.offer = pipeline.compose_offer(client(), S.risk or {"fields": {}}, S.quotes, bnotes)
                except Exception as e:
                    st.error(f"Σφάλμα: {e}")

    if S.offer:
        name = ((S.risk or {}).get("fields", {}).get("applicant_name", {}) or {}).get("v") or ""
        docs = S.intake_files + S.quote_files
        html = offer.render_html(S.offer, S.quotes, client_name=name, documents=docs)
        c1, c2, _ = st.columns([1, 1, 4])
        c1.download_button("⬇ HTML (email)", html, file_name="prosfora.html", mime="text/html")
        try:
            c2.download_button("⬇ PDF", offer.render_pdf(html), file_name="prosfora.pdf", mime="application/pdf")
        except Exception as e:
            c2.error(f"PDF: {e}")
        components.html(html, height=900, scrolling=True)

# ── tab 4: free chat over the loaded documents ───────────────────────────────
with t4:
    for m in S.chat:
        with st.chat_message(m["role"]):
            st.write(m["content"])
    q = st.chat_input("Ρώτα κάτι για τα έγγραφα της υπόθεσης...")
    if q:
        S.chat.append({"role": "user", "content": q})
        history = "\n".join(f"{m['role']}: {m['content']}" for m in S.chat[:-1])
        with st.spinner("..."):
            try:
                reply = pipeline.ask(client(), (f"Προηγούμενη συζήτηση:\n{history}\n\n" if history else "") + q,
                                     S.intake_blocks + S.quote_blocks)
            except Exception as e:
                reply = f"Σφάλμα: {e}"
        S.chat.append({"role": "assistant", "content": reply})
        st.rerun()
