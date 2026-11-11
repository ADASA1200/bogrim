package org.videoblock

import android.app.Activity
import android.app.AlertDialog
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch

/** PIN-protected settings. Closes itself as soon as it leaves the screen, so the PIN is asked again. */
class AdminActivity : Activity() {
    private lateinit var prefs: Prefs

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        if (prefs.permanent || !Policy.isDeviceOwner(this)) { finish(); return }
        render()
    }

    override fun onStop() { super.onStop(); finish() }

    private fun apply() = Policy.enforceAsync(this)

    private fun render() {
        val col = column()
        col.addView(text("ניהול חוסם הווידאו", 22f, bold = true))

        // --- Camera
        col.addView(Switch(this).apply {
            text = "חסום מצלמה (מונע צילום וידאו)"
            isChecked = prefs.blockCamera
            setOnCheckedChangeListener { _, v -> prefs.blockCamera = v; apply() }
        })

        // --- Apps
        col.addView(text("אפליקציות", 18f, bold = true))
        col.addView(text("מסומן = חסום. אפליקציות וידאו ודפדפנים מסומנים אוטומטית. " +
            "ניתן לשחרר אפליקציה (למשל דפדפן) — אתרי הווידאו עדיין ייחסמו בסינון ה-DNS.", 13f))
        val apps = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        col.addView(apps)
        Thread { val rows = loadApps(); runOnUiThread { fillApps(apps, rows) } }.start()

        // --- Domains
        col.addView(text("אתרים נוספים לחסימה", 18f, bold = true))
        val domains = EditText(this).apply {
            hint = "example.com (שורה לכל אתר)"
            setText(prefs.extraDomains.sorted().joinToString("\n"))
            minLines = 3
        }
        col.addView(domains)
        col.addView(button("שמור אתרים") {
            prefs.extraDomains = domains.text.lines()
                .map { it.trim().lowercase().removePrefix("https://").removePrefix("http://")
                    .removePrefix("www.").substringBefore('/') }
                .filter { it.contains('.') }.toSet()
            toast("נשמר")
        })

        // --- PIN
        col.addView(button("שינוי קוד מנהל") { newPin(cancelable = true) {} })

        // --- Danger zone
        col.addView(text("פעולות בלתי הפיכות", 18f, bold = true))
        col.addView(button("🔒 נעילה לצמיתות") { confirmPermanent() })
        col.addView(button("הסרת ההגנה מהמכשיר") { confirmRelease() })

        setContentView(ScrollView(this).apply { addView(col) })
    }

    private data class Row(val pkg: String, val label: String, val blocked: Boolean, val auto: Boolean)

    private fun loadApps(): List<Row> {
        val pm = packageManager
        val essential = Policy.essentialPackages(this)
        val auto = Policy.detectVideoApps(this) + Blocklist.videoPackages
        val targets = Policy.computeTargets(this, prefs)
        return pm.getInstalledApplications(PackageManager.MATCH_UNINSTALLED_PACKAGES)
            .filter { it.packageName !in essential }
            .filter { it.packageName in auto || it.packageName in prefs.forceBlocked ||
                pm.getLaunchIntentForPackage(it.packageName) != null ||
                (it.flags and ApplicationInfo.FLAG_SYSTEM) == 0 }
            .map { Row(it.packageName, pm.getApplicationLabel(it).toString(),
                it.packageName in targets, it.packageName in auto) }
            .sortedWith(compareByDescending<Row> { it.blocked }.thenBy { it.label })
    }

    private fun fillApps(container: LinearLayout, rows: List<Row>) {
        rows.forEach { r ->
            container.addView(CheckBox(this).apply {
                text = if (r.auto) "${r.label}  (וידאו)" else r.label
                isChecked = r.blocked
                setOnCheckedChangeListener { _, block ->
                    if (block) {
                        prefs.allowed -= r.pkg
                        if (!r.auto) prefs.forceBlocked += r.pkg
                    } else {
                        prefs.forceBlocked -= r.pkg
                        if (r.auto) prefs.allowed += r.pkg
                    }
                    apply()
                }
            })
        }
    }

    private fun confirmPermanent() {
        val phrase = "נעל לצמיתות"
        val f = EditText(this).apply { hint = phrase }
        AlertDialog.Builder(this).setTitle("נעילה לצמיתות")
            .setMessage("לאחר הנעילה לא יהיה ניתן יותר לשנות הגדרות, לשחרר אפליקציות או להסיר " +
                "את ההגנה — גם עם הקוד. הדרך היחידה תהיה מחיקה מלאה של המכשיר במצב Recovery.\n\n" +
                "להמשך הקלד: $phrase")
            .setView(f)
            .setPositiveButton("נעל") { _, _ ->
                if (f.text.toString().trim() == phrase) {
                    prefs.permanent = true; apply(); toast("המכשיר ננעל לצמיתות"); finish()
                } else toast("הטקסט לא תואם — לא בוצעה נעילה")
            }
            .setNegativeButton("ביטול", null).show()
    }

    private fun confirmRelease() {
        AlertDialog.Builder(this).setTitle("הסרת ההגנה")
            .setMessage("כל החסימות יבוטלו ותהיה אפשרות להסיר את התוכנה. להמשיך?")
            .setPositiveButton("הסר הגנה") { _, _ ->
                runCatching { Policy.release(this) }
                    .onSuccess { toast("ההגנה הוסרה. כעת ניתן להסיר את התוכנה."); finishAffinity() }
                    .onFailure { toast("שגיאה: ${it.message}") }
            }
            .setNegativeButton("ביטול", null).show()
    }
}
