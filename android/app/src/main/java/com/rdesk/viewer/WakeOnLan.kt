package com.rdesk.viewer

import android.content.SharedPreferences
import org.json.JSONObject
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress

/** Wake-on-LAN: שליחת מגיק-פאקט לרשת המקומית להעיר מחשב כבוי/בשינה לפני
ניסיון להתחבר אליו (כמו הפיצ'ר המקביל ב-AnyDesk) - תואם בדיוק ל-rdesk/wol.py
בצד Python. עובד רק באותה רשת מקומית (broadcast) - בלי VPN/תיעול מיוחד
אין דרך לשלוח WoL מהאינטרנט. */
object WakeOnLan {
    private val MAC_RE = Regex("^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
    private const val PREF_KEY = "wol_macs"   // JSON: {hostId: mac}

    fun normalizeMac(mac: String): String {
        val m = mac.trim()
        require(MAC_RE.matches(m)) { "bad_mac" }
        return m
    }

    private fun macBytes(mac: String): ByteArray =
        mac.split(":", "-").map { it.toInt(16).toByte() }.toByteArray()

    /** 6 בתים של 0xFF ואז כתובת ה-MAC חוזרת 16 פעם - הפורמט הסטנדרטי. */
    fun buildMagicPacket(mac: String): ByteArray {
        val body = macBytes(normalizeMac(mac))
        val packet = ByteArray(6 + 16 * 6)
        for (i in 0 until 6) packet[i] = 0xFF.toByte()
        for (i in 0 until 16) body.copyInto(packet, 6 + i * 6)
        return packet
    }

    /** true אם נשלח בהצלחה; false אם ה-MAC לא תקין (קריאה ברקע - IO חוסם). */
    fun send(mac: String, broadcast: String = "255.255.255.255", port: Int = 9): Boolean {
        val packet = try {
            buildMagicPacket(mac)
        } catch (e: IllegalArgumentException) {
            return false
        }
        DatagramSocket().use { s ->
            s.broadcast = true
            s.send(DatagramPacket(packet, packet.size, InetAddress.getByName(broadcast), port))
        }
        return true
    }

    // ------------------------------------------------------------- אחסון MAC לכל מזהה חיוג
    private fun loadMap(prefs: SharedPreferences): MutableMap<String, String> {
        val raw = prefs.getString(PREF_KEY, null) ?: return mutableMapOf()
        val obj = runCatching { JSONObject(raw) }.getOrNull() ?: return mutableMapOf()
        val map = mutableMapOf<String, String>()
        obj.keys().forEach { k -> map[k] = obj.optString(k) }
        return map
    }

    private fun saveMap(prefs: SharedPreferences, map: Map<String, String>) {
        val obj = JSONObject()
        map.forEach { (k, v) -> obj.put(k, v) }
        prefs.edit().putString(PREF_KEY, obj.toString()).apply()
    }

    fun getMac(prefs: SharedPreferences, hostId: String): String? = loadMap(prefs)[hostId]?.takeIf { it.isNotBlank() }

    fun setMac(prefs: SharedPreferences, hostId: String, mac: String) {
        val map = loadMap(prefs)
        if (mac.isBlank()) map.remove(hostId) else map[hostId] = mac
        saveMap(prefs, map)
    }
}
