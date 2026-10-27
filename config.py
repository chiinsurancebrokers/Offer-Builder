"""Ashlar Offers — shared configuration.

Everything personal (name, phone, email) comes from environment variables so
nothing identifying is committed to git.
"""
import os

MODEL = os.environ.get("OFFERS_MODEL", "claude-sonnet-5-5")
MAX_TOKENS = int(os.environ.get("OFFERS_MAX_TOKENS", "8000"))
MAX_RETRIES = 4

BROKER = {
    "company": os.environ.get("BROKER_COMPANY", "Ashlar Insurance"),
    "name": os.environ.get("BROKER_NAME", ""),
    "tel": os.environ.get("BROKER_TEL", ""),
    "email": os.environ.get("BROKER_EMAIL", ""),
    "web": os.environ.get("BROKER_WEB", "ashlar-assurance.com"),
}

# Brand colours used by the HTML/PDF template
NAVY = "#1C3F5E"
GOLD = "#C9A96E"
INK = "#1A2B3C"
