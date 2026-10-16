package com.rdesk.viewer

import android.content.SharedPreferences
import java.security.SecureRandom

/**
 * המזהה בן 9 הספרות שמחשב (או מכשיר אחר) מקליד כדי להתחבר *לטלפון הזה*
 * כשהוא פועל במצב מארח - תואם ל-rdesk/config.py::host_identity בצד Python
 * (אותה שיטה: מספר אקראי בטוח, נוצר פעם אחת ונשמר). שונה מ-DeviceIdentity
 * (ה-"viewer_id" הפנימי, לא-מחויג, שמשמש לזיהוי המכשיר הזה כצופה מול
 * מארחים אחרים - שני המזהים קיימים זה לצד זה, בדיוק כמו ב-Windows.
 */
object HostIdentity {
    private const val PREF_KEY = "host_dial_id"

    fun get(prefs: SharedPreferences): String =
        get(read = { prefs.getString(PREF_KEY, null) }, write = { prefs.edit().putString(PREF_KEY, it).apply() })

    @Synchronized
    fun get(read: () -> String?, write: (String) -> Unit): String {
        read()?.let { return it }
        val rnd = SecureRandom()
        val id = (1..9).joinToString("") { rnd.nextInt(10).toString() }
        write(id)
        return id
    }

    fun regenerate(prefs: SharedPreferences): String {
        val rnd = SecureRandom()
        val id = (1..9).joinToString("") { rnd.nextInt(10).toString() }
        prefs.edit().putString(PREF_KEY, id).apply()
        return id
    }
}
