package org.videoblock

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Typeface
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast

/** Small helpers for building the (deliberately simple) code-only UI. */
fun Activity.dp(v: Int) = (v * resources.displayMetrics.density).toInt()

fun Activity.column(): LinearLayout = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    layoutDirection = View.LAYOUT_DIRECTION_RTL
    setPadding(dp(16), dp(16), dp(16), dp(16))
}

fun Activity.text(s: CharSequence, size: Float = 16f, bold: Boolean = false) = TextView(this).apply {
    text = s; textSize = size; gravity = Gravity.START
    textDirection = View.TEXT_DIRECTION_RTL
    if (bold) setTypeface(typeface, Typeface.BOLD)
    setPadding(0, dp(6), 0, dp(6))
}

fun Activity.button(s: String, onClick: () -> Unit) = Button(this).apply {
    text = s; setOnClickListener { onClick() }
}

fun Activity.toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

fun Activity.pinField(hint: String) = EditText(this).apply {
    this.hint = hint
    inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
}

/** Asks for the PIN; calls [onOk] only if it is correct. */
fun Activity.askPin(onOk: () -> Unit) {
    val prefs = Prefs(this)
    val wait = prefs.lockoutMinutesLeft()
    if (wait > 0) { toast("יותר מדי ניסיונות שגויים. נסה שוב בעוד $wait דקות."); return }
    val f = pinField("קוד מנהל")
    AlertDialog.Builder(this).setTitle("הזן קוד מנהל").setView(f)
        .setPositiveButton("אישור") { _, _ ->
            if (prefs.checkPin(f.text.toString())) onOk() else toast("קוד שגוי")
        }
        .setNegativeButton("ביטול", null).show()
}

/** Asks for a new PIN twice. Minimum 6 digits. */
fun Activity.newPin(cancelable: Boolean, onDone: () -> Unit) {
    val box = column()
    val a = pinField("קוד חדש (לפחות 6 ספרות)")
    val b = pinField("הקלד שוב")
    box.addView(a); box.addView(b)
    AlertDialog.Builder(this).setTitle("הגדרת קוד מנהל")
        .setMessage("את הקוד מומלץ למסור לאדם אחר (רב / הורה / חבר) ולא לשמור אצלך.")
        .setView(box).setCancelable(cancelable)
        .setPositiveButton("שמור") { _, _ ->
            val p = a.text.toString()
            when {
                p.length < 6 -> { toast("הקוד חייב להכיל לפחות 6 ספרות"); newPin(cancelable, onDone) }
                p != b.text.toString() -> { toast("הקודים אינם תואמים"); newPin(cancelable, onDone) }
                else -> { Prefs(this).setPin(p); toast("הקוד נשמר"); onDone() }
            }
        }
        .apply { if (cancelable) setNegativeButton("ביטול", null) }
        .show()
}
