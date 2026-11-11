package org.videoblock

import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import android.util.Log
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.Executors

/**
 * Local DNS filter. Only DNS traffic is routed into this VPN (all other traffic goes
 * directly to the network), so it costs no speed or battery. Queries for video domains
 * get NXDOMAIN; everything else is forwarded to a family-safe upstream resolver.
 */
class DnsVpnService : VpnService() {
    private var tun: ParcelFileDescriptor? = null
    private var reader: Thread? = null
    private val pool = Executors.newFixedThreadPool(8)

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (tun == null) start()
        return START_STICKY
    }

    private fun start() {
        val iface = Builder()
            .setSession(getString(R.string.app_name))
            .addAddress(TUN_ADDR, 32)
            .addDnsServer(DNS_ADDR)
            .addRoute(DNS_ADDR, 32)
            .setBlocking(true)
            .establish() ?: return
        tun = iface
        reader = Thread({ loop(iface, Prefs(this)) }, "dns-tun").apply { start() }
    }

    private fun loop(iface: ParcelFileDescriptor, prefs: Prefs) {
        val input = FileInputStream(iface.fileDescriptor)
        val output = FileOutputStream(iface.fileDescriptor)
        val buf = ByteArray(32767)
        val upstreams = listOf(prefs.upstreamDns, "1.0.0.3").distinct().map { InetAddress.getByName(it) }
        try {
            while (!Thread.interrupted()) {
                val n = input.read(buf)
                if (n <= 0) continue
                val q = DnsPacket.parse(buf, n) ?: continue
                if (Blocklist.isBlockedDomain(q.name, prefs.extraDomains)) {
                    write(output, q.reply(q.nxdomain()))
                } else {
                    pool.execute { forward(q, upstreams, output) }
                }
            }
        } catch (e: Exception) {
            Log.i("VideoBlock", "tun closed: $e")
        }
    }

    private fun forward(q: DnsPacket, upstreams: List<InetAddress>, out: FileOutputStream) {
        for (server in upstreams) {
            try {
                DatagramSocket().use { s ->
                    protect(s) // send outside the VPN, straight to the real network
                    s.soTimeout = 4000
                    s.send(DatagramPacket(q.dns, q.dns.size, server, 53))
                    val resp = ByteArray(4096)
                    val p = DatagramPacket(resp, resp.size)
                    s.receive(p)
                    write(out, q.reply(resp.copyOf(p.length)))
                    return
                }
            } catch (_: Exception) { /* try next upstream */ }
        }
        write(out, q.reply(q.servfail()))
    }

    private fun write(out: FileOutputStream, packet: ByteArray) {
        synchronized(out) { runCatching { out.write(packet) } }
    }

    override fun onRevoke() = stop()
    override fun onDestroy() { stop(); super.onDestroy() }

    private fun stop() {
        reader?.interrupt()
        runCatching { tun?.close() }
        tun = null
    }

    companion object {
        const val TUN_ADDR = "10.111.222.2"
        const val DNS_ADDR = "10.111.222.1"
    }
}

/** A DNS query captured from the tun interface (IPv4/UDP only — the only route we install). */
class DnsPacket private constructor(
    private val src: ByteArray, private val dst: ByteArray,
    private val srcPort: Int, private val dstPort: Int,
    val dns: ByteArray, val name: String, private val questionEnd: Int,
) {
    fun nxdomain() = errorReply(3)
    fun servfail() = errorReply(2)

    /** Echoes the question back with QR=1, RA=1 and the given RCODE, no answers. */
    private fun errorReply(rcode: Int): ByteArray {
        val r = dns.copyOf(questionEnd)
        r[2] = ((r[2].toInt() or 0x80) and 0xF9).toByte() // QR=1, keep opcode+RD, clear AA/TC
        r[3] = (0x80 or rcode).toByte()                                // RA=1, RCODE
        for (i in 6 until 12) r[i] = 0                                 // AN/NS/AR = 0
        return r
    }

    /** Wraps a DNS payload in IPv4/UDP headers addressed back to the querying app. */
    fun reply(payload: ByteArray): ByteArray {
        val total = 28 + payload.size
        val p = ByteArray(total)
        p[0] = 0x45; p[2] = (total ushr 8).toByte(); p[3] = total.toByte()
        p[6] = 0x40; p[8] = 64; p[9] = 17
        System.arraycopy(dst, 0, p, 12, 4)
        System.arraycopy(src, 0, p, 16, 4)
        var sum = 0
        for (i in 0 until 20 step 2) sum += ((p[i].toInt() and 0xFF) shl 8) or (p[i + 1].toInt() and 0xFF)
        while (sum ushr 16 != 0) sum = (sum and 0xFFFF) + (sum ushr 16)
        val ck = sum.inv() and 0xFFFF
        p[10] = (ck ushr 8).toByte(); p[11] = ck.toByte()
        val udpLen = 8 + payload.size
        p[20] = (dstPort ushr 8).toByte(); p[21] = dstPort.toByte()
        p[22] = (srcPort ushr 8).toByte(); p[23] = srcPort.toByte()
        p[24] = (udpLen ushr 8).toByte(); p[25] = udpLen.toByte()
        // UDP checksum 0 = "not computed", valid for IPv4.
        System.arraycopy(payload, 0, p, 28, payload.size)
        return p
    }

    companion object {
        fun parse(b: ByteArray, n: Int): DnsPacket? {
            if (n < 20 || (b[0].toInt() ushr 4) != 4 || b[9].toInt() != 17) return null
            val ihl = (b[0].toInt() and 0x0F) * 4
            if (n < ihl + 8 + 12) return null
            fun u16(o: Int) = ((b[o].toInt() and 0xFF) shl 8) or (b[o + 1].toInt() and 0xFF)
            val srcPort = u16(ihl); val dstPort = u16(ihl + 2)
            if (dstPort != 53) return null
            val dns = b.copyOfRange(ihl + 8, n)
            // Parse QNAME
            val sb = StringBuilder()
            var o = 12
            while (o < dns.size) {
                val len = dns[o].toInt() and 0xFF
                if (len == 0) { o++; break }
                if (len and 0xC0 != 0 || o + 1 + len > dns.size) return null
                if (sb.isNotEmpty()) sb.append('.')
                for (i in 1..len) sb.append((dns[o + i].toInt() and 0xFF).toChar())
                o += 1 + len
            }
            val questionEnd = o + 4 // QTYPE + QCLASS
            if (questionEnd > dns.size) return null
            return DnsPacket(b.copyOfRange(12, 16), b.copyOfRange(16, 20), srcPort, dstPort,
                dns, sb.toString(), questionEnd)
        }
    }
}
