import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from streamlit.testing.v1 import AppTest  # noqa: E402

import auth  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")


class FakeDB:
    """Mimics ob_login / ob_change_password."""
    def __init__(self, pw="Temp-abc", must_change=True):
        self.pw, self.must_change, self.fails = pw, must_change, 0

    def login(self, p):
        if self.fails >= 5:
            return {"ok": False, "reason": "locked", "retry_seconds": 600}
        if p == self.pw:
            return {"ok": True, "must_change": self.must_change}
        self.fails += 1
        return {"ok": False, "reason": "bad_password"}

    def change(self, old, new):
        if old != self.pw:
            return {"ok": False, "reason": "bad_password"}
        if len(new) < 12:
            return {"ok": False, "reason": "too_short"}
        self.pw, self.must_change = new, False
        return {"ok": True}


def patch(monkeypatch, db):
    monkeypatch.setattr(auth, "login", db.login)
    monkeypatch.setattr(auth, "change_password", db.change)


def run():
    return AppTest.from_file(APP, default_timeout=30).run()


def test_fails_closed_when_db_unreachable(monkeypatch):
    def boom(*a):
        raise auth.AuthUnavailable("down")
    monkeypatch.setattr(auth, "login", boom)
    at = run()
    at.text_input[0].set_value("x").run()
    at.button[0].click().run()
    assert any("δεν είναι διαθέσιμη" in e.value for e in at.error)
    assert len(at.tabs) == 0


def test_missing_supabase_env_raises(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    try:
        auth.login("x")
        assert False
    except auth.AuthUnavailable:
        pass


def test_wrong_password_stays_locked(monkeypatch):
    patch(monkeypatch, FakeDB())
    at = run()
    at.text_input[0].set_value("nope").run()
    at.button[0].click().run()
    assert any("Λάθος" in e.value for e in at.error)
    assert len(at.tabs) == 0


def test_temp_password_forces_change_then_enters(monkeypatch):
    db = FakeDB()
    patch(monkeypatch, db)
    at = run()
    at.text_input[0].set_value("Temp-abc").run()
    at.button[0].click().run()
    assert len(at.tabs) == 0 and len(at.text_input) == 2  # change form
    at.text_input[0].set_value("short").run()
    at.text_input[1].set_value("short").run()
    at.button[0].click().run()
    assert any("12" in e.value for e in at.error) and len(at.tabs) == 0
    at.text_input[0].set_value("a-much-longer-pw").run()
    at.text_input[1].set_value("different-pw-here").run()
    at.button[0].click().run()
    assert any("δεν ταιριάζουν" in e.value for e in at.error)
    at.text_input[1].set_value("a-much-longer-pw").run()
    at.button[0].click().run()
    assert not at.exception and len(at.tabs) == 4
    assert db.pw == "a-much-longer-pw" and not db.must_change


def test_normal_login_after_change(monkeypatch):
    patch(monkeypatch, FakeDB(pw="my-real-password", must_change=False))
    at = run()
    at.text_input[0].set_value("my-real-password").run()
    at.button[0].click().run()
    assert not at.exception and len(at.tabs) == 4
