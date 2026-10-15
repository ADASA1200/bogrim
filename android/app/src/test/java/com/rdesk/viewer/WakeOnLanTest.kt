package com.rdesk.viewer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/** תואם בדיוק ל-rdesk/wol.py - אותם מקרי בדיקה (ראו tests/test_wol.py). */
class WakeOnLanTest {
    @Test fun normalizeMacAcceptsColonAndDash() {
        assertEquals("AA:BB:CC:DD:EE:FF", WakeOnLan.normalizeMac("AA:BB:CC:DD:EE:FF"))
        assertEquals("aa-bb-cc-dd-ee-ff", WakeOnLan.normalizeMac("aa-bb-cc-dd-ee-ff"))
    }

    @Test fun normalizeMacRejectsGarbage() {
        for (bad in listOf("", "not a mac", "AA:BB:CC:DD:EE", "AA:BB:CC:DD:EE:GG", "AABBCCDDEEFF")) {
            assertThrows(IllegalArgumentException::class.java) { WakeOnLan.normalizeMac(bad) }
        }
    }

    @Test fun buildMagicPacketShape() {
        val packet = WakeOnLan.buildMagicPacket("AA:BB:CC:DD:EE:FF")
        assertEquals(102, packet.size)
        for (i in 0 until 6) assertEquals(0xFF.toByte(), packet[i])
        val mac = byteArrayOf(0xAA.toByte(), 0xBB.toByte(), 0xCC.toByte(), 0xDD.toByte(), 0xEE.toByte(), 0xFF.toByte())
        assertEquals(mac.toList(), packet.copyOfRange(6, 12).toList())
        assertEquals(mac.toList(), packet.copyOfRange(96, 102).toList())
        var repeats = 0
        for (i in 0 until 16) {
            if (packet.copyOfRange(6 + i * 6, 12 + i * 6).toList() == mac.toList()) repeats++
        }
        assertEquals(16, repeats)
    }
}
