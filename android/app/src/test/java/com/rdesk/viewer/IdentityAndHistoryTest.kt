package com.rdesk.viewer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** בדיקות DeviceIdentity ו-ConnectionHistory מול אחסון מדומה (בלי תלות ב-SharedPreferences האמיתי). */
class IdentityAndHistoryTest {

    @Test fun deviceIdentityIsCreatedOnceAndPersisted() {
        var stored: String? = null
        val id1 = DeviceIdentity.get(read = { stored }, write = { stored = it })
        assertNotNull(stored)
        assertTrue(id1.startsWith("v"))
        assertEquals(13, id1.length)

        val id2 = DeviceIdentity.get(read = { stored }, write = { stored = it })
        assertEquals(id1, id2)
    }

    @Test fun deviceIdentityDiffersAcrossFreshStores() {
        val a = DeviceIdentity.get(read = { null }, write = {})
        val b = DeviceIdentity.get(read = { null }, write = {})
        assertTrue(a != b)
    }

    @Test fun historyStartAndEndRoundTrip() {
        var raw: String? = null
        val read = { raw }
        val write: (List<HistoryEntry>) -> Unit = { entries ->
            val arr = org.json.JSONArray()
            for (e in entries) {
                arr.put(
                    org.json.JSONObject()
                        .put("peer", e.peer).put("mode", e.mode)
                        .put("startedAt", e.startedAt)
                        .put("endedAt", e.endedAt ?: org.json.JSONObject.NULL)
                )
            }
            raw = arr.toString()
        }

        ConnectionHistory.startEntry("123456789", "interactive", read, write)
        var entries = ConnectionHistory.recent(read)
        assertEquals(1, entries.size)
        assertEquals("123456789", entries[0].peer)
        assertNull(entries[0].endedAt)

        ConnectionHistory.endLast("123456789", read, write)
        entries = ConnectionHistory.recent(read)
        assertEquals(1, entries.size)
        assertNotNull(entries[0].endedAt)
        assertTrue(entries[0].endedAt!! >= entries[0].startedAt)
    }

    @Test fun historyMostRecentFirstAndRespectsLimit() {
        var raw: String? = null
        val read = { raw }
        val write: (List<HistoryEntry>) -> Unit = { entries ->
            val arr = org.json.JSONArray()
            for (e in entries) {
                arr.put(
                    org.json.JSONObject()
                        .put("peer", e.peer).put("mode", e.mode)
                        .put("startedAt", e.startedAt)
                        .put("endedAt", e.endedAt ?: org.json.JSONObject.NULL)
                )
            }
            raw = arr.toString()
        }

        for (i in 1..5) ConnectionHistory.startEntry("id$i", "interactive", read, write)
        val entries = ConnectionHistory.recent(read, limit = 3)
        assertEquals(3, entries.size)
        assertEquals("id5", entries[0].peer)
        assertEquals("id4", entries[1].peer)
        assertEquals("id3", entries[2].peer)
    }

    @Test fun historyEndLastOnlyAffectsMatchingOpenEntry() {
        var raw: String? = null
        val read = { raw }
        val write: (List<HistoryEntry>) -> Unit = { entries ->
            val arr = org.json.JSONArray()
            for (e in entries) {
                arr.put(
                    org.json.JSONObject()
                        .put("peer", e.peer).put("mode", e.mode)
                        .put("startedAt", e.startedAt)
                        .put("endedAt", e.endedAt ?: org.json.JSONObject.NULL)
                )
            }
            raw = arr.toString()
        }

        ConnectionHistory.startEntry("a", "interactive", read, write)
        ConnectionHistory.startEntry("b", "unattended", read, write)
        ConnectionHistory.endLast("b", read, write)

        val entries = ConnectionHistory.recent(read)
        val a = entries.first { it.peer == "a" }
        val b = entries.first { it.peer == "b" }
        assertNull(a.endedAt)
        assertNotNull(b.endedAt)
    }
}
