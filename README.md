# Offer Builder — Ashlar Insurance

Εργαλείο για προσφορές ασφάλισης επαγγελματικής ευθύνης (αρχιτέκτονες/μηχανικοί).

**Ροή:** upload εγγράφων πελάτη → εξαγωγή στοιχείων κινδύνου (με πηγή αρχείο/σελίδα) →
έλεγχος ελλείψεων → email αιτήματος → upload προσφορών εταιρειών → σύγκριση →
προσφορά ως **HTML email** και **PDF** με παράρτημα πηγών.

Τίποτα δεν στέλνεται αυτόματα. Ο μεσίτης ελέγχει κάθε βήμα. Οι πηγές και η σύσταση
παράγονται από AI και πρέπει να επαληθεύονται με τα πρωτότυπα.

## Αρχεία

| Αρχείο | Ρόλος |
|---|---|
| `app.py` | Streamlit UI (κωδικός πρόσβασης σε όλη την εφαρμογή) |
| `brain.py` | Upload → blocks για το Claude (PDF natively, εικόνες, Word, Excel, CSV) |
| `pipeline.py` | Βήματα Claude: εξαγωγή, ελλείψεις, email, προσφορές, σύνθεση |
| `offer.py` | Template HTML (email-safe) και PDF (WeasyPrint) |
| `config.py` | Μοντέλο και στοιχεία μεσίτη από env vars |

Η φόρμα στοιχείων ορίζεται σε ένα σημείο: η λίστα `FIELDS` στο `pipeline.py`.

## Ρύθμιση

Ο κωδικός εισόδου αποθηκεύεται στη Supabase (πίνακας `offer_builder_auth`, hash bcrypt) και ελέγχεται
μόνο μέσω των συναρτήσεων `ob_login` / `ob_change_password`. Στην πρώτη είσοδο με τον προσωρινό
κωδικό η εφαρμογή ζητά νέο κωδικό (τουλάχιστον 12 χαρακτήρες). Μετά από 5 λάθη κλειδώνει για 15 λεπτά.

Environment variables (Railway → Variables, ή `.env` τοπικά):

| Μεταβλητή | Περιγραφή |
|---|---|
| `ANTHROPIC_API_KEY` | Υποχρεωτικό |
| `SUPABASE_URL`, `SUPABASE_KEY` | Υποχρεωτικά. Το URL του project και το publishable key (όχι service role) |
| `BROKER_NAME`, `BROKER_TEL`, `BROKER_EMAIL` | Εμφανίζονται στο υποσέλιδο της προσφοράς |
| `OFFERS_MODEL` | Προαιρετικό (προεπιλογή `claude-sonnet-5-5`) |

Αν ξεχάσεις τον κωδικό: στο SQL editor της Supabase τρέξε
`update public.offer_builder_auth set pw_hash = extensions.crypt('ΠΡΟΣΩΡΙΝΟΣ', extensions.gen_salt('bf',10)), must_change = true, locked_until = null, failed_attempts = 0;`

## Τοπικά

```bash
pip install -r requirements.txt
streamlit run app.py
pytest -q tests          # τεστ χωρίς κλήσεις API
```

Το PDF θέλει pango και γραμματοσειρά με ελληνικά (DejaVu/Noto) στο σύστημα. Το `Dockerfile` τα εγκαθιστά.

## Railway

New Project → Deploy from GitHub repo. Το `railway.toml` χρησιμοποιεί το `Dockerfile`.
Ορίσε τις μεταβλητές πάνω και δες το health check στο `/_stcore/health`.

## Ασφάλεια

- Το repo πρέπει να μείνει **private**. Μην βάζεις ονόματα πελατών ή δεδομένα υποθέσεων στον κώδικα.
- Ο κωδικός προστατεύει όλη την εφαρμογή, αλλά είναι βασικός έλεγχος. Για πιο ισχυρή προστασία
  βάλε μπροστά Cloudflare Access ή παρόμοιο.
- Τα έγγραφα στέλνονται στο Anthropic API για επεξεργασία. Δεν αποθηκεύονται σε βάση από την εφαρμογή.

## Επόμενα βήματα

Προσυμπλήρωση των εντύπων ERGO/NP/Groupama, δημιουργία draft στο Gmail (όχι αποστολή),
αποθήκευση υποθέσεων σε βάση.
