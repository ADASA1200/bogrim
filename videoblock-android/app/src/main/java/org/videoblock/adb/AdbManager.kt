package org.videoblock.adb

import android.content.Context
import android.util.Base64
import io.github.muntashirakon.adb.AbsAdbConnectionManager
import io.github.muntashirakon.adb.AdbStream
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder
import java.math.BigInteger
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.PrivateKey
import java.security.Security
import java.security.cert.Certificate
import java.security.interfaces.RSAPrivateKey
import java.security.interfaces.RSAPublicKey
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.X509EncodedKeySpec
import java.util.Date

/**
 * Self-ADB connection manager built on libadb-android (the same pure-Java ADB + SPAKE2 pairing
 * stack used by PCAPdroid-MDM and Switch). It holds one persisted RSA identity + self-signed
 * certificate, which the device authorises once (via the pairing code or the "Allow debugging"
 * dialog) and then remembers.
 */
class AdbManager private constructor(private val key: PrivateKey, private val cert: Certificate) :
    AbsAdbConnectionManager() {

    init {
        api = android.os.Build.VERSION.SDK_INT
        setTimeout(20, java.util.concurrent.TimeUnit.SECONDS)
    }

    override fun getPrivateKey(): PrivateKey = key
    override fun getCertificate(): Certificate = cert
    override fun getDeviceName(): String = "VideoBlock"

    /** Runs one shell command over the open connection and returns its combined output. */
    fun runShell(command: String): String {
        val stream: AdbStream = adbConnection!!.open("shell:$command")
        val out = StringBuilder()
        stream.openInputStream().use { input ->
            val buf = ByteArray(4096)
            while (true) {
                val n = try { input.read(buf) } catch (e: Exception) { break }
                if (n < 0) break
                if (n > 0) out.append(String(buf, 0, n))
            }
        }
        return out.toString()
    }

    companion object {
        @Volatile private var instance: AdbManager? = null

        fun get(context: Context): AdbManager {
            instance?.let { return it }
            synchronized(this) {
                instance?.let { return it }
                if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null)
                    Security.addProvider(BouncyCastleProvider())
                val (priv, cert) = loadOrCreateIdentity(context)
                return AdbManager(priv, cert).also { instance = it }
            }
        }

        private fun loadOrCreateIdentity(context: Context): Pair<PrivateKey, Certificate> {
            val sp = (if (android.os.Build.VERSION.SDK_INT >= 24)
                context.createDeviceProtectedStorageContext() else context)
                .getSharedPreferences("adbid", Context.MODE_PRIVATE)
            val kf = KeyFactory.getInstance("RSA")
            val cf = java.security.cert.CertificateFactory.getInstance("X.509")
            val privB64 = sp.getString("priv", null)
            val certB64 = sp.getString("cert", null)
            if (privB64 != null && certB64 != null) {
                val priv = kf.generatePrivate(PKCS8EncodedKeySpec(Base64.decode(privB64, Base64.NO_WRAP)))
                val cert = cf.generateCertificate(Base64.decode(certB64, Base64.NO_WRAP).inputStream())
                return priv to cert
            }
            val kp = KeyPairGenerator.getInstance("RSA").apply { initialize(2048) }.generateKeyPair()
            val subject = X500Name("CN=VideoBlock, O=VideoBlock, C=IL")
            val now = System.currentTimeMillis()
            val builder = JcaX509v3CertificateBuilder(
                subject, BigInteger.valueOf(now), Date(now - 86_400_000L),
                Date(now + 30L * 365 * 86_400_000L), subject, kp.public)
            val signer = JcaContentSignerBuilder("SHA256withRSA")
                .setProvider(BouncyCastleProvider.PROVIDER_NAME).build(kp.private)
            val cert = JcaX509CertificateConverter()
                .setProvider(BouncyCastleProvider.PROVIDER_NAME)
                .getCertificate(builder.build(signer))
            sp.edit()
                .putString("priv", Base64.encodeToString((kp.private as RSAPrivateKey).encoded, Base64.NO_WRAP))
                .putString("cert", Base64.encodeToString(cert.encoded, Base64.NO_WRAP))
                .apply()
            return kp.private to cert
        }
    }
}
