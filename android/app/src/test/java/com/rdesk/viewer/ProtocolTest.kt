package com.rdesk.viewer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** הווקטורים נוצרו ע"י rdesk/protocol.py (Python) - הבדיקה מוכיחה תאימות בין הלקוחות. */
class ProtocolTest {
    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }

    @Test fun deriveKeyMatchesPython() {
        assertEquals("7936d8cb01444df55711c7a16e02f29e1fafa78016fa4d05009cd908d969e478",
            hex(Protocol.deriveKey("permanent-pass")))
    }

    @Test fun deriveKeyHebrewPasswordMatchesPython() {
        assertEquals("26adcb8069febe49357585eea6e2ad48ec7d41af0a993b5d5070ec0ab17ad23f",
            hex(Protocol.deriveKey("סיסמה-עברית-123")))
    }

    @Test fun authTagMatchesPython() {
        val key = Protocol.deriveKey("permanent-pass")
        val sdp = "v=0\r\na=fingerprint:sha-256 AA:BB:CC\r\na=mid:0\r\n"
        val tag = "570e288433ee3eeb39580f9ac118f7cb59f3318812c1245c2c06e3ff1dcd1064"
        assertEquals(tag, Protocol.authTag(key, "0123456789abcdef", "viewer", sdp))
        assertTrue(Protocol.verifyTag(key, "0123456789abcdef", "viewer", sdp, tag))
        assertFalse(Protocol.verifyTag(key, "0123456789abcdef", "host", sdp, tag))
        assertFalse(Protocol.verifyTag(key, "other-nonce", "viewer", sdp, tag))
    }

    @Test fun authTagHebrewSdpMatchesPython() {
        val key = Protocol.deriveKey("סיסמה-עברית-123")
        assertEquals("e3dcd4fc76fbae04186d95589fd663208771c8e6f65da42955f721f9a15b1741",
            Protocol.authTag(key, "n1", "host", "שלום\r\n"))
    }

    @Test fun sessionCodeMatchesPython() {
        val o = "v=0\r\na=fingerprint:sha-256 aa:bb:cc:dd\r\n"
        val a = "v=0\r\na=fingerprint:sha-256 11:22:33:44\r\na=fingerprint:sha-384 99:99\r\n"
        assertEquals("391 552", Protocol.sessionCode(o, a))
    }

    @Test fun idHelpers() {
        assertEquals("123 456 789", Protocol.formatId("123456789"))
        assertEquals("1234", Protocol.cleanId("12 3-4"))
    }

    @Test fun safeFileName() {
        assertEquals("passwd", Protocol.safeFileName("../../etc/passwd"))
        assertEquals("x.exe", Protocol.safeFileName("..\\..\\win\\x.exe"))
        assertEquals("file", Protocol.safeFileName(""))
        assertEquals("a_b_.txt", Protocol.safeFileName("a:b?.txt"))
    }
}
