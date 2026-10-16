package com.rdesk.viewer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** בדיקות HostIdentity מול אחסון מדומה - תואם לדגם ה-9 ספרות של rdesk/protocol.py::new_id. */
class HostIdentityTest {

    @Test fun createdOnceAndPersistedAsNineDigits() {
        var stored: String? = null
        val id1 = HostIdentity.get(read = { stored }, write = { stored = it })
        assertNotNull(stored)
        assertEquals(9, id1.length)
        assertTrue(id1.all { it.isDigit() })

        val id2 = HostIdentity.get(read = { stored }, write = { stored = it })
        assertEquals(id1, id2)
    }

    @Test fun differsAcrossFreshStores() {
        val a = HostIdentity.get(read = { null }, write = {})
        val b = HostIdentity.get(read = { null }, write = {})
        assertTrue(a != b)
    }
}
