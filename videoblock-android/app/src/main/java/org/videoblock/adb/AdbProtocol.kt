package org.videoblock.adb

import java.io.InputStream
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * The ADB wire protocol (the one `adb` uses to talk to `adbd`). We speak it over a local TCP
 * socket to the device's own adbd, so the app can run a privileged shell command on itself
 * after the user approves the "Allow debugging" dialog. Framing only — no transport policy here.
 */
object AdbProtocol {
    const val CNXN = 0x4e584e43
    const val AUTH = 0x48545541
    const val OPEN = 0x4e45504f
    const val OKAY = 0x59414b4f
    const val WRTE = 0x45545257
    const val CLSE = 0x45534c43

    const val AUTH_TOKEN = 1
    const val AUTH_SIGNATURE = 2
    const val AUTH_RSAPUBLICKEY = 3

    const val VERSION = 0x01000001
    const val MAX_DATA = 256 * 1024
    const val HEADER_SIZE = 24

    /** Encodes one message (6 little-endian uint32s + payload). */
    fun encode(command: Int, arg0: Int, arg1: Int, payload: ByteArray): ByteArray {
        val b = ByteBuffer.allocate(HEADER_SIZE + payload.size).order(ByteOrder.LITTLE_ENDIAN)
        b.putInt(command); b.putInt(arg0); b.putInt(arg1)
        b.putInt(payload.size); b.putInt(checksum(payload)); b.putInt(command.inv())
        b.put(payload)
        return b.array()
    }

    /** Sum of payload bytes (unsigned), as adbd expects in the header. */
    fun checksum(payload: ByteArray): Int {
        var sum = 0
        for (x in payload) sum += (x.toInt() and 0xFF)
        return sum
    }

    data class Message(val command: Int, val arg0: Int, val arg1: Int, val payload: ByteArray)

    /** Reads exactly one message from the stream, or throws on EOF / malformed header. */
    fun read(input: InputStream): Message {
        val head = readFully(input, HEADER_SIZE)
        val b = ByteBuffer.wrap(head).order(ByteOrder.LITTLE_ENDIAN)
        val command = b.int; val arg0 = b.int; val arg1 = b.int
        val len = b.int; b.int /* data crc */; val magic = b.int
        require(magic == command.inv()) { "bad magic" }
        require(len in 0..(MAX_DATA)) { "bad length $len" }
        val payload = if (len > 0) readFully(input, len) else ByteArray(0)
        return Message(command, arg0, arg1, payload)
    }

    fun write(out: OutputStream, data: ByteArray) { out.write(data); out.flush() }

    private fun readFully(input: InputStream, n: Int): ByteArray {
        val buf = ByteArray(n); var off = 0
        while (off < n) {
            val r = input.read(buf, off, n - off)
            if (r < 0) throw java.io.EOFException("adb stream closed")
            off += r
        }
        return buf
    }
}
