package org.videoblock.adb

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.math.BigInteger
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.KeyPairGenerator
import java.security.interfaces.RSAPublicKey

class AdbKeyTest {
    @Test fun androidPubkeyStructIsWellFormed() {
        val pub = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }
            .generateKeyPair().public as RSAPublicKey
        val enc = AdbKey.encodeAndroidPubkey(pub)
        assertEquals(4 + 4 + 64 * 4 + 64 * 4 + 4, enc.size)
        val b = ByteBuffer.wrap(enc).order(ByteOrder.LITTLE_ENDIAN)
        assertEquals(64, b.int)                 // modulus size in words
        val n0inv = b.int.toLong() and 0xFFFFFFFFL
        // Verify n0inv = -1/n mod 2^32 against the real modulus.
        val r32 = BigInteger.ONE.shiftLeft(32)
        val expected = pub.modulus.mod(r32).modInverse(r32).negate().mod(r32)
        assertEquals(expected.toLong(), n0inv)
        assertEquals(65537, enc.let {
            ByteBuffer.wrap(it, it.size - 4, 4).order(ByteOrder.LITTLE_ENDIAN).int
        })
    }
}
