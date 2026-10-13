package com.rdesk.viewer

import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

data class HistoryEntry(
    val peer: String,
    val mode: String,
    val startedAt: Long,
    val endedAt: Long?,
)

/**
 * יומן חיבורים מקומי: מי התחברנו אליו, מתי ובאיזה מצב. נשמר כמערך JSON
 * (מקביל ל-rdesk/connlog.py בצד Python, אך "peer" מתייחס כאן למזהה המחשב המרוחק
 * שאליו התחברנו - לא למזהה הנכנס). האחסון עצמו (read/write) מוזרק כפונקציות
 * כדי לאפשר בדיקות יחידה בלי תלות ב-SharedPreferences האמיתי של אנדרואיד.
 */
object ConnectionHistory {
    private const val PREF_KEY = "history"
    private const val MAX_ENTRIES = 200

    fun startEntry(prefs: SharedPreferences, peer: String, mode: String) =
        startEntry(peer, mode, read = { prefs.getString(PREF_KEY, null) }, write = { save(prefs, it) })

    fun endLast(prefs: SharedPreferences, peer: String) =
        endLast(peer, read = { prefs.getString(PREF_KEY, null) }, write = { save(prefs, it) })

    fun recent(prefs: SharedPreferences, limit: Int = 50): List<HistoryEntry> =
        recent(read = { prefs.getString(PREF_KEY, null) }, limit = limit)

    fun clear(prefs: SharedPreferences) = save(prefs, emptyList())

    @Synchronized
    fun startEntry(peer: String, mode: String, read: () -> String?, write: (List<HistoryEntry>) -> Unit) {
        val entries = load(read()).toMutableList()
        entries.add(HistoryEntry(peer, mode, System.currentTimeMillis() / 1000, null))
        write(entries.takeLast(MAX_ENTRIES))
    }

    @Synchronized
    fun endLast(peer: String, read: () -> String?, write: (List<HistoryEntry>) -> Unit) {
        val entries = load(read()).toMutableList()
        for (i in entries.indices.reversed()) {
            val e = entries[i]
            if (e.peer == peer && e.endedAt == null) {
                entries[i] = e.copy(endedAt = System.currentTimeMillis() / 1000)
                break
            }
        }
        write(entries)
    }

    fun recent(read: () -> String?, limit: Int = 50): List<HistoryEntry> =
        load(read()).asReversed().take(limit)

    private fun load(raw: String?): List<HistoryEntry> {
        if (raw == null) return emptyList()
        val arr = runCatching { JSONArray(raw) }.getOrNull() ?: return emptyList()
        return (0 until arr.length()).mapNotNull { i ->
            val o = arr.optJSONObject(i) ?: return@mapNotNull null
            HistoryEntry(
                peer = o.optString("peer"),
                mode = o.optString("mode"),
                startedAt = o.optLong("startedAt"),
                endedAt = if (o.isNull("endedAt")) null else o.optLong("endedAt"),
            )
        }
    }

    private fun save(prefs: SharedPreferences, entries: List<HistoryEntry>) {
        val arr = JSONArray()
        for (e in entries) {
            arr.put(
                JSONObject()
                    .put("peer", e.peer)
                    .put("mode", e.mode)
                    .put("startedAt", e.startedAt)
                    .put("endedAt", e.endedAt ?: JSONObject.NULL)
            )
        }
        prefs.edit().putString(PREF_KEY, arr.toString()).apply()
    }
}
