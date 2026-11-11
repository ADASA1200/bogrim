package org.videoblock

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.os.Bundle
import android.widget.ScrollView

class MainActivity : Activity() {

    override fun onResume() {
        super.onResume()
        render()
    }

    private fun render() {
        val prefs = Prefs(this)
        val col = column()
        col.addView(text(getString(R.string.app_name), 26f, bold = true))

        if (!Policy.isDeviceOwner(this)) {
            renderSetup(col)
        } else {
            Policy.enforceAsync(this)
            if (!prefs.hasPin) newPin(cancelable = false) { render() }
            val blocked = prefs.suspendedByUs.size
            col.addView(text("✅ ההגנה פעילה", 20f, bold = true))
            col.addView(text(
                "• $blocked אפליקציות וידאו / דפדפנים חסומים\n" +
                "• סינון DNS חוסם אתרי וידאו בכל האפליקציות\n" +
                "• אפליקציות וידאו חדשות נחסמות אוטומטית בהתקנה\n" +
                "• לא ניתן להסיר את התוכנה, לאפס את המכשיר מההגדרות, להיכנס למצב בטוח, " +
                "להפעיל ADB, להחליף VPN או להעביר קבצים ב-USB / כרטיס זיכרון"
            ))
            if (prefs.blockCamera) col.addView(text("• המצלמה חסומה"))
            if (prefs.permanent) {
                col.addView(text("🔒 המכשיר נעול לצמיתות. לא ניתן לשנות הגדרות או להסיר את ההגנה.", bold = true))
            } else {
                col.addView(button("ניהול (דורש קוד מנהל)") {
                    askPin { startActivity(Intent(this, AdminActivity::class.java)) }
                })
            }
        }
        setContentView(ScrollView(this).apply { addView(col) })
    }

    private fun renderSetup(col: android.widget.LinearLayout) {
        val cmd = "adb shell dpm set-device-owner $packageName/.AdminReceiver"
        col.addView(text("ההגנה עדיין לא הופעלה", 20f, bold = true))
        col.addView(text(
            "כדי שלא יהיה ניתן להסיר את החסימה בשום צורה, התוכנה חייבת לפעול כ\"בעלים של המכשיר\" " +
            "(Device Owner). זו פעולה חד-פעמית שנעשית מהמחשב:\n\n" +
            "1. מחק את כל החשבונות מהמכשיר (הגדרות ← חשבונות), כולל חשבון Google. " +
            "אפשר להוסיף אותם שוב אחרי ההפעלה.\n" +
            "2. הפעל אפשרויות מפתחים ו\"ניפוי באגים ב-USB\".\n" +
            "3. חבר את המכשיר למחשב והרץ:"
        ))
        col.addView(text(cmd, 14f, bold = true))
        col.addView(button("העתק פקודה") {
            getSystemService(ClipboardManager::class.java)
                .setPrimaryClip(ClipData.newPlainText("cmd", cmd))
            toast("הועתק")
        })
        col.addView(text(
            "4. פתח שוב את התוכנה והגדר קוד מנהל.\n\n" +
            "לאחר ההפעלה ניפוי הבאגים ייחסם אוטומטית, כך שגם דרך המחשב לא ניתן יהיה להסיר את התוכנה."
        ))
    }
}
