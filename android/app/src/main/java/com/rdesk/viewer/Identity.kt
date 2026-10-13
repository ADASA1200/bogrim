package com.rdesk.viewer

import android.content.SharedPreferences
import java.security.SecureRandom

/**
 * מזהה פנימי קבוע לצופה הזה (לא המזהה החיוג - זה רק למארחים לזהות "אותו מכשיר"
 * בין התחברויות, כדי ש"אמון תמידי" יעבוד בכלל). נוצר פעם אחת ונשמר, בניגוד
 * למזהה אקראי-חדש-בכל-חיבור. תואם ל-rdesk/config.py::viewer_identity בצד Python.
 */
object DeviceIdentity {
    private const val PREF_KEY = "viewer_id"

    fun get(prefs: SharedPreferences): String =
        get(read = { prefs.getString(PREF_KEY, null) }, write = { prefs.edit().putString(PREF_KEY, it).apply() })

    @Synchronized
    fun get(read: () -> String?, write: (String) -> Unit): String {
        read()?.let { return it }
        val id = "v" + randomHex(12)
        write(id)
        return id
    }

    private fun randomHex(n: Int): String {
        val b = ByteArray(n)
        SecureRandom().nextBytes(b)
        return b.joinToString("") { "%02x".format(it) }.take(n)
    }
}
