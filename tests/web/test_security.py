import pytest
from mailbender.web.security import WebSecurity


def make() -> WebSecurity:
    return WebSecurity(secret_key="k" * 32, password="hunter2")


def test_check_password_constant_time_match():
    s = make()
    assert s.check_password("hunter2") is True
    assert s.check_password("wrong") is False


def test_empty_password_rejects_everything():
    s = WebSecurity(secret_key="k" * 32, password="")
    assert s.login_enabled is False
    assert s.check_password("") is False
    assert s.check_password("anything") is False


def test_session_round_trip():
    s = make()
    token = s.issue_session()
    assert s.valid_session(token) is True


def test_session_rejects_tampered_and_missing():
    s = make()
    assert s.valid_session(None) is False
    assert s.valid_session("not-a-token") is False
    assert s.valid_session(s.issue_session() + "x") is False


def test_session_rejected_under_different_secret_key():
    a = WebSecurity(secret_key="a" * 32, password="hunter2")
    b = WebSecurity(secret_key="b" * 32, password="hunter2")
    assert b.valid_session(a.issue_session()) is False


def test_session_survives_password_change_same_key():
    a = WebSecurity(secret_key="k" * 32, password="old")
    token = a.issue_session()
    b = WebSecurity(secret_key="k" * 32, password="new")
    assert b.valid_session(token) is True


def test_csrf_round_trip_and_reject():
    s = make()
    assert s.valid_csrf(s.issue_csrf()) is True
    assert s.valid_csrf(None) is False
    assert s.valid_csrf("nope") is False
