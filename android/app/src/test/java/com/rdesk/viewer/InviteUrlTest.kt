package com.rdesk.viewer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** הכתובות כאן נוצרו בפועל ע"י rdesk/protocol.py::make_invite_url - הבדיקה
מוכיחה תאימות אמיתית בין הלקוחות, לא רק עקביות-עצמית של Kotlin. */
class InviteUrlTest {
    @Test fun parsesRealPythonGeneratedUrl() {
        val link = Protocol.parseInviteUrl("rdesk://connect/123456789/tok-abc_123?server=ws%3A%2F%2F127.0.0.1%3A8765")
        assertEquals("123456789", link?.id)
        assertEquals("tok-abc_123", link?.token)
        assertEquals("ws://127.0.0.1:8765", link?.server)
    }

    @Test fun parsesRealPythonGeneratedUrlWithSpecialCharsInServer() {
        val link = Protocol.parseInviteUrl(
            "rdesk://connect/123456789/tok?server=wss%3A%2F%2Fexample.com%3A9999%2Fpath%3Fa%3Db"
        )
        assertEquals("wss://example.com:9999/path?a=b", link?.server)
    }

    @Test fun rejectsWrongScheme() {
        assertNull(Protocol.parseInviteUrl("https://connect/123456789/tok"))
    }

    @Test fun rejectsGarbage() {
        for (bad in listOf("", "not a url at all", "rdesk://", "rdesk://connect/123456789", "rdesk://other/123456789/tok")) {
            assertNull(Protocol.parseInviteUrl(bad))
        }
    }
}
