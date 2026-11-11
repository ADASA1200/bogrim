package org.videoblock.adb

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.ByteArrayInputStream

class AdbProtocolTest {
    @Test fun encodeHeaderIsLittleEndianWithMagicAndChecksum() {
        val payload = "shell:echo hi\u0000".toByteArray()
        val m = AdbProtocol.encode(AdbProtocol.OPEN, 1, 0, payload)
        assertEquals(AdbProtocol.HEADER_SIZE + payload.size, m.size)
        fun le(o: Int) = (m[o].toInt() and 0xFF) or ((m[o+1].toInt() and 0xFF) shl 8) or
                ((m[o+2].toInt() and 0xFF) shl 16) or ((m[o+3].toInt() and 0xFF) shl 24)
        assertEquals(AdbProtocol.OPEN, le(0))
        assertEquals(1, le(4)); assertEquals(0, le(8))
        assertEquals(payload.size, le(12))
        assertEquals(AdbProtocol.checksum(payload), le(16))
        assertEquals(AdbProtocol.OPEN.inv(), le(20))
    }

    @Test fun roundTripThroughReader() {
        val payload = byteArrayOf(1, 2, 3, 4, 5, 6)
        val bytes = AdbProtocol.encode(AdbProtocol.WRTE, 7, 9, payload)
        val msg = AdbProtocol.read(ByteArrayInputStream(bytes))
        assertEquals(AdbProtocol.WRTE, msg.command)
        assertEquals(7, msg.arg0); assertEquals(9, msg.arg1)
        assertArrayEquals(payload, msg.payload)
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsBadMagic() {
        val bytes = AdbProtocol.encode(AdbProtocol.CNXN, 0, 0, ByteArray(0))
        bytes[20] = (bytes[20] + 1).toByte() // corrupt magic
        AdbProtocol.read(ByteArrayInputStream(bytes))
    }
}
