"""בדיקות ל-acl.py: רשימת IP מורשים ו-TOTP."""
from rdesk import acl


def test_ip_allowed_empty_whitelist_allows_everything():
    assert acl.ip_allowed("1.2.3.4", [])
    assert acl.ip_allowed(None, [])


def test_ip_allowed_exact_match():
    assert acl.ip_allowed("1.2.3.4", ["1.2.3.4"])
    assert not acl.ip_allowed("1.2.3.5", ["1.2.3.4"])


def test_ip_allowed_cidr_match():
    assert acl.ip_allowed("192.168.1.42", ["192.168.1.0/24"])
    assert not acl.ip_allowed("192.168.2.42", ["192.168.1.0/24"])


def test_ip_allowed_none_ip_rejected_when_whitelist_set():
    assert not acl.ip_allowed(None, ["1.2.3.4"])


def test_ip_allowed_bad_entries_are_ignored():
    assert not acl.ip_allowed("1.2.3.4", ["not-an-ip", "also bad/x"])


def test_totp_round_trip():
    secret = acl.totp_new_secret()
    code = acl.totp_code(secret)
    assert acl.totp_verify(secret, code)


def test_totp_wrong_code_fails():
    secret = acl.totp_new_secret()
    assert not acl.totp_verify(secret, "000000") or acl.totp_code(secret) == "000000"
    bad = "000000" if acl.totp_code(secret) != "000000" else "111111"
    assert not acl.totp_verify(secret, bad)


def test_totp_tolerates_one_step_clock_drift():
    secret = acl.totp_new_secret()
    code = acl.totp_code(secret, t=1000.0, step=30)
    assert acl.totp_verify(secret, code, t=1029.0, step=30)   # אותו צעד
    assert acl.totp_verify(secret, code, t=1031.0, step=30)   # צעד אחד הלאה - בתוך window=1
    assert not acl.totp_verify(secret, code, t=1100.0, step=30)  # הרבה יותר מאוחר


def test_totp_verify_handles_garbage_safely():
    assert not acl.totp_verify("", "123456")
    assert not acl.totp_verify("NOTBASE32!!!", "123456")
    assert not acl.totp_verify("JBSWY3DPEHPK3PXP", "")
