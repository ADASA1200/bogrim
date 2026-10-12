"""בדיקה ש-truststore באמת מחליף את ה-SSLContext הגלובלי (ולא רק מדווח שהצליח)."""
import ssl

from rdesk import net


def test_use_system_trust_store_actually_patches_ssl_context():
    assert net.use_system_trust_store() is True
    assert ssl.SSLContext.__module__.startswith("truststore")
    assert net.use_system_trust_store() is True   # אידמפוטנטי - לא קורס בקריאה חוזרת
