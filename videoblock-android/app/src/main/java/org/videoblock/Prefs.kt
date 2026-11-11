package org.videoblock

import android.content.Context
import android.content.SharedPreferences
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

/** All persistent settings. Stored in device-protected storage so they are readable before first unlock. */
class Prefs(context: Context) {
    private val sp: SharedPreferences =
        // Device-protected storage (readable before first unlock) exists from API 24.
        (if (android.os.Build.VERSION.SDK_INT >= 24) context.createDeviceProtectedStorageContext() else context)
            .getSharedPreferences("vb", Context.MODE_PRIVATE)

    /** Packages the administrator explicitly allowed even though they can play video. */
    var allowed: Set<String>
        get() = sp.getStringSet("allowed", emptySet())!!.toSet()
        set(v) = sp.edit().putStringSet("allowed", v).apply()

    /** Packages the administrator blocked manually (e.g. a messenger with video channels). */
    var forceBlocked: Set<String>
        get() = sp.getStringSet("force", emptySet())!!.toSet()
        set(v) = sp.edit().putStringSet("force", v).apply()

    /** Packages this app suspended, so they can be released when no longer targeted. */
    var suspendedByUs: Set<String>
        get() = sp.getStringSet("suspended", emptySet())!!.toSet()
        set(v) = sp.edit().putStringSet("suspended", v).commit().let { }

    var hiddenByUs: Set<String>
        get() = sp.getStringSet("hidden", emptySet())!!.toSet()
        set(v) = sp.edit().putStringSet("hidden", v).commit().let { }

    /** Extra domains to block in the DNS filter, one per entry. */
    var extraDomains: Set<String>
        get() = sp.getStringSet("domains", emptySet())!!.toSet()
        set(v) = sp.edit().putStringSet("domains", v).apply()

    var blockCamera: Boolean
        get() = sp.getBoolean("camera", false)
        set(v) = sp.edit().putBoolean("camera", v).apply()

    /** Once true, protection can never be removed and settings can never be changed. */
    var permanent: Boolean
        get() = sp.getBoolean("permanent", false)
        set(v) = sp.edit().putBoolean("permanent", v).commit().let { }

    var upstreamDns: String
        get() = sp.getString("dns", DEFAULT_DNS)!!
        set(v) = sp.edit().putString("dns", v).apply()

    // ---------- PIN ----------

    val hasPin get() = sp.contains("pin_hash")

    fun setPin(pin: String) {
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        sp.edit().putString("pin_salt", salt.hex()).putString("pin_hash", hash(pin, salt).hex())
            .putInt("fails", 0).putLong("lock_until", 0).commit()
    }

    /** Minutes the PIN entry is still locked out after repeated failures, 0 if not locked. */
    fun lockoutMinutesLeft(): Long {
        val left = sp.getLong("lock_until", 0) - System.currentTimeMillis()
        return if (left > 0) (left + 59_999) / 60_000 else 0
    }

    fun checkPin(pin: String): Boolean {
        if (lockoutMinutesLeft() > 0) return false
        val salt = sp.getString("pin_salt", null)?.unhex() ?: return false
        val expected = sp.getString("pin_hash", null)?.unhex() ?: return false
        val ok = MessageDigest.isEqual(hash(pin, salt), expected)
        if (ok) {
            sp.edit().putInt("fails", 0).putLong("lock_until", 0).apply()
        } else {
            val fails = sp.getInt("fails", 0) + 1
            // After 5 wrong attempts: 1, 2, 4, 8 ... minutes, up to 24 hours.
            val lockMin = if (fails >= 5) minOf(1L shl minOf(fails - 5, 11), 24 * 60L) else 0L
            sp.edit().putInt("fails", fails)
                .putLong("lock_until", System.currentTimeMillis() + lockMin * 60_000).commit()
        }
        return ok
    }

    private fun hash(pin: String, salt: ByteArray): ByteArray =
        SecretKeyFactory.getInstance("PBKDF2WithHmacSHA1")
            .generateSecret(PBEKeySpec(pin.toCharArray(), salt, 20_000, 256)).encoded

    private fun ByteArray.hex() = joinToString("") { "%02x".format(it) }
    private fun String.unhex() = chunked(2).map { it.toInt(16).toByte() }.toByteArray()

    companion object {
        /** Cloudflare "for Families": also blocks adult and malware sites upstream. */
        const val DEFAULT_DNS = "1.1.1.3"
    }
}
