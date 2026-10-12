package com.rdesk.viewer

import java.security.MessageDigest
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/** תואם בדיוק ל-rdesk/protocol.py בצד ה-Python. */
object Protocol {
    const val MAX_CLIPBOARD_BYTES = 1024 * 1024
    const val FILE_CHUNK = 16 * 1024

    fun cleanId(raw: String): String = raw.filter { it.isDigit() }

    fun formatId(raw: String): String = cleanId(raw).chunked(3).joinToString(" ")

    private fun hmac(key: ByteArray, msg: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return mac.doFinal(msg)
    }

    /**
     * PBKDF2-HMAC-SHA256, 200,000 סבבים, 32 בתים, salt = "rdesk-v1".
     * ממומש ידנית כדי להבטיח קידוד UTF-8 זהה ל-Python גם לסיסמאות בעברית
     * (מימוש ה-provider של אנדרואיד עשוי לקודד אחרת).
     */
    fun deriveKey(password: String): ByteArray {
        val pw = password.toByteArray(Charsets.UTF_8)
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(if (pw.isEmpty()) ByteArray(1) else pw, "HmacSHA256"))
        val salt = "rdesk-v1".toByteArray(Charsets.UTF_8) + byteArrayOf(0, 0, 0, 1)
        var u = mac.doFinal(salt)
        val t = u.copyOf()
        for (i in 2..200_000) {
            u = mac.doFinal(u)
            for (j in t.indices) t[j] = (t[j].toInt() xor u[j].toInt()).toByte()
        }
        return t
    }

    private fun hex(b: ByteArray) = b.joinToString("") { "%02x".format(it) }

    fun authTag(key: ByteArray, nonce: String, role: String, sdp: String): String =
        hex(hmac(key, "$role\n$nonce\n$sdp".toByteArray(Charsets.UTF_8)))

    fun verifyTag(key: ByteArray, nonce: String, role: String, sdp: String, tag: String): Boolean =
        MessageDigest.isEqual(
            authTag(key, nonce, role, sdp).toByteArray(Charsets.UTF_8),
            tag.toByteArray(Charsets.UTF_8),
        )

    private val fingerprintRe = Regex("a=fingerprint:sha-256 ([0-9A-Fa-f:]+)")

    private fun fingerprint(sdp: String): String =
        fingerprintRe.find(sdp)?.groupValues?.get(1)?.uppercase() ?: ""

    /** קוד אבטחה בן 6 ספרות. זהה בשני הצדדים אם ורק אם אין מתווך. */
    fun sessionCode(offerSdp: String, answerSdp: String): String {
        val h = MessageDigest.getInstance("SHA-256")
            .digest((fingerprint(offerSdp) + "|" + fingerprint(answerSdp)).toByteArray(Charsets.UTF_8))
        val n = ((h[0].toLong() and 0xff) shl 24 or ((h[1].toLong() and 0xff) shl 16) or
                ((h[2].toLong() and 0xff) shl 8) or (h[3].toLong() and 0xff)) % 1_000_000
        val s = "%06d".format(n)
        return s.substring(0, 3) + " " + s.substring(3)
    }

    fun safeFileName(name: String): String {
        var n = name.replace('\\', '/').substringAfterLast('/')
        n = n.replace(Regex("[\\u0000-\\u001f<>:\"|?*]"), "_").trim('.', ' ')
        return n.ifEmpty { "file" }
    }
}

data class Perms(
    val control: Boolean = true,
    val clipboard: Boolean = true,
    val files: Boolean = true,
    val chat: Boolean = true,
)

data class Monitor(val index: Int, val width: Int, val height: Int)

data class ConnectionInfo(
    val monitors: List<Monitor>,
    val monitor: Int,
    val perms: Perms,
    val mode: String,   // "interactive" (באישור המשתמש) | "unattended" (סיסמה קבועה)
    val code: String,
)

class ConnectException(message: String) : Exception(message)
