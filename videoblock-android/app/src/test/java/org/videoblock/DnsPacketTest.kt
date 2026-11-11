package org.videoblock

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DnsPacketTest {

    /** Builds an IPv4/UDP DNS query for [name] from 10.111.222.2:40000 to 10.111.222.1:53. */
    private fun query(name: String, dstPort: Int = 53): ByteArray {
        val q = mutableListOf<Byte>()
        q += listOf(0x12, 0x34, 0x01, 0x00, 0, 1, 0, 0, 0, 0, 0, 0).map { it.toByte() }
        name.split('.').forEach { l -> q += l.length.toByte(); q += l.toByteArray().toList() }
        q += listOf(0, 0, 1, 0, 1).map { it.toByte() }
        val total = 28 + q.size
        val p = ByteArray(total)
        p[0] = 0x45; p[3] = total.toByte(); p[9] = 17
        byteArrayOf(10, 111, 222.toByte(), 2).copyInto(p, 12)
        byteArrayOf(10, 111, 222.toByte(), 1).copyInto(p, 16)
        p[20] = (40000 ushr 8).toByte(); p[21] = 40000.toByte()
        p[22] = (dstPort ushr 8).toByte(); p[23] = dstPort.toByte()
        q.toByteArray().copyInto(p, 28)
        return p
    }

    private fun u16(b: ByteArray, o: Int) = ((b[o].toInt() and 0xFF) shl 8) or (b[o + 1].toInt() and 0xFF)

    @Test fun parsesName() {
        val p = query("rr3---sn-abc.googlevideo.com")
        val d = DnsPacket.parse(p, p.size)
        assertNotNull(d)
        assertEquals("rr3---sn-abc.googlevideo.com", d!!.name)
    }

    @Test fun ignoresNonDns() {
        val p = query("a.com", dstPort = 80)
        assertNull(DnsPacket.parse(p, p.size))
    }

    @Test fun nxdomainReplyIsValid() {
        val p = query("www.youtube.com")
        val d = DnsPacket.parse(p, p.size)!!
        val r = d.reply(d.nxdomain())
        assertEquals(r.size, u16(r, 2))                       // IP total length
        var sum = 0
        for (i in 0 until 20 step 2) sum += u16(r, i)
        while (sum ushr 16 != 0) sum = (sum and 0xFFFF) + (sum ushr 16)
        assertEquals(0xFFFF, sum)                               // IP header checksum verifies
        assertEquals(10, r[12].toInt()); assertEquals(1, r[15].toInt())   // src = DNS server
        assertEquals(2, r[19].toInt())                                    // dst = app
        assertEquals(53, u16(r, 20)); assertEquals(40000, u16(r, 22))     // ports swapped
        assertEquals(r.size - 20, u16(r, 24))                             // UDP length
        assertEquals(0x1234, u16(r, 28))                                  // same DNS id
        assertTrue(r[30].toInt() and 0x80 != 0)                           // QR
        assertTrue(r[30].toInt() and 0x01 != 0)                           // RD kept
        assertEquals(3, r[31].toInt() and 0x0F)                           // NXDOMAIN
        assertEquals(1, u16(r, 32)); assertEquals(0, u16(r, 34))          // 1 question, 0 answers
    }

    @Test fun domainMatching() {
        assertTrue(Blocklist.isBlockedDomain("youtube.com", emptySet()))
        assertTrue(Blocklist.isBlockedDomain("M.YouTube.com.", emptySet()))
        assertTrue(Blocklist.isBlockedDomain("rr1---sn-x.googlevideo.com", emptySet()))
        assertTrue(Blocklist.isBlockedDomain("v16.tiktokcdn.com", emptySet()))
        assertFalse(Blocklist.isBlockedDomain("notyoutube.com", emptySet()))
        assertFalse(Blocklist.isBlockedDomain("google.com", emptySet()))
        assertFalse(Blocklist.isBlockedDomain("wikipedia.org", emptySet()))
        assertTrue(Blocklist.isBlockedDomain("cdn.example.org", setOf("example.org")))
    }
}
