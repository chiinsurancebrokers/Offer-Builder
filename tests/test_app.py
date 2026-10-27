import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_fails_closed_without_password(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD_SHA256", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert any("APP_PASSWORD_SHA256" in e.value for e in at.error)
    assert len(at.tabs) == 0


def test_wrong_then_right_password(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD_SHA256", hashlib.sha256(b"secret").hexdigest())
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert len(at.tabs) == 0  # locked
    at.text_input[0].set_value("nope").run()
    at.button[0].click().run()
    assert any("Λάθος" in e.value for e in at.error)
    at.text_input[0].set_value("secret").run()
    at.button[0].click().run()
    assert not at.exception
    assert len(at.tabs) == 4


def test_malformed_hash_is_reported(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD_SHA256", "abc123")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert any("δεν είναι έγκυρο sha256" in e.value and "6 χαρακτήρες" in e.value for e in at.error)
    assert len(at.tabs) == 0


def test_hash_with_quotes_and_spaces_is_accepted(monkeypatch):
    h = hashlib.sha256(b"secret").hexdigest()
    monkeypatch.setenv("APP_PASSWORD_SHA256", f' "{h.upper()}" ')
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input[0].set_value("secret").run()
    at.button[0].click().run()
    assert len(at.tabs) == 4
