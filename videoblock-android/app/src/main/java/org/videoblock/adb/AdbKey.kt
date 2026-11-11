package org.videoblock.adb

import android.content.Context
import android.util.Base64
import java.math.BigInteger
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.interfaces.RSAPrivateKey
import java.security.interfaces.RSAPublicKey
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.X509EncodedKeySpec
import javax.crypto.Cipher

/**
 * The RSA identity adbd authenticates. Generated once and kept in device-protected storage.
 * Also encodes the public key in adb's own `android_pubkey` format so the device can show the
 * "Allow debugging from this computer?" dialog and remember our key.
 */
class AdbKey private constructor(private val pair: KeyPair) {

    /** PKCS#1 v1.5 signature over adbd's 20-byte token (prefixed with the SHA-1 DigestInfo). */
    fun sign(token: ByteArray): ByteArray {
        val c = Cipher.getInstance("RSA/ECB/PKCS1Padding")
        c.init(Cipher.ENCRYPT_MODE, pair.private)
        return c.doFinal(SHA1_DIGEST_INFO + token)
    }

    /** adb public-key line: base64(android_pubkey struct) + " " + name. */
    fun adbPublicKey(name: String = "videoblock@android"): ByteArray {
        val pub = pair.public as RSAPublicKey
        val encoded = encodeAndroidPubkey(pub)
        return (Base64.encodeToString(encoded, Base64.NO_WRAP) + " " + name + "\u0000").toByteArray()
    }

    companion object {
        // ASN.1 DigestInfo prefix for SHA-1, as adb prepends before RSA-signing the token.
        private val SHA1_DIGEST_INFO = byteArrayOf(
            0x30, 0x21, 0x30, 0x09, 0x06, 0x05, 0x2b, 0x0e, 0x03, 0x02, 0x1a, 0x05, 0x00, 0x04, 0x14)

        private const val WORDS = 64 // 2048-bit modulus in 32-bit words

        fun load(context: Context): AdbKey {
            val sp = (if (android.os.Build.VERSION.SDK_INT >= 24)
                context.createDeviceProtectedStorageContext() else context)
                .getSharedPreferences("adbkey", Context.MODE_PRIVATE)
            val priv = sp.getString("priv", null); val pub = sp.getString("pub", null)
            if (priv != null && pub != null) {
                val kf = KeyFactory.getInstance("RSA")
                val pr = kf.generatePrivate(PKCS8EncodedKeySpec(Base64.decode(priv, Base64.NO_WRAP)))
                val pb = kf.generatePublic(X509EncodedKeySpec(Base64.decode(pub, Base64.NO_WRAP)))
                return AdbKey(KeyPair(pb, pr))
            }
            val gen = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }
            val kp = gen.generateKeyPair()
            sp.edit()
                .putString("priv", Base64.encodeToString((kp.private as RSAPrivateKey).encoded, Base64.NO_WRAP))
                .putString("pub", Base64.encodeToString((kp.public as RSAPublicKey).encoded, Base64.NO_WRAP))
                .apply()
            return AdbKey(KeyPair(kp.public, kp.private))
        }

        /** Builds the little-endian android_pubkey struct adbd stores and matches against. */
        fun encodeAndroidPubkey(pub: RSAPublicKey): ByteArray {
            val r32 = BigInteger.ONE.shiftLeft(32)
            val n = pub.modulus
            val n0inv = n.mod(r32).modInverse(r32).negate().mod(r32)             // -1/n[0] mod 2^32
            val rr = BigInteger.ONE.shiftLeft(2048 * 2).mod(n)                   // R^2 mod n
            val out = java.nio.ByteBuffer.allocate(4 + 4 + WORDS * 4 + WORDS * 4 + 4)
                .order(java.nio.ByteOrder.LITTLE_ENDIAN)
            out.putInt(WORDS)
            out.putInt(n0inv.toInt())
            putWords(out, n); putWords(out, rr)
            out.putInt(pub.publicExponent.toInt())
            return out.array()
        }

        private fun putWords(out: java.nio.ByteBuffer, value: BigInteger) {
            val mask = BigInteger.ONE.shiftLeft(32).subtract(BigInteger.ONE)
            var v = value
            repeat(WORDS) { out.putInt(v.and(mask).toInt()); v = v.shiftRight(32) }
        }
    }
}
