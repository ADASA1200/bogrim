package org.videoblock

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputEditText
import com.google.android.material.textfield.TextInputLayout

/** Material UI builders shared by the activities, so the whole app reads as one modern surface. */

fun Activity.dp(v: Int) = (v * resources.displayMetrics.density).toInt()

/** Root vertical column with page padding and RTL layout. */
fun Activity.column(): LinearLayout = LinearLayout(this).apply {
    orientation = LinearLayout.VERTICAL
    layoutDirection = View.LAYOUT_DIRECTION_RTL
    setPadding(dp(16), dp(20), dp(16), dp(28))
}

/** Big page title with a short subtitle, styled as a header band. */
fun Activity.header(title: String, subtitle: String? = null): View {
    val box = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(12))
    }
    box.addView(TextView(this).apply {
        text = title; textSize = 28f; setTypeface(typeface, Typeface.BOLD)
        setTextColor(resources.getColor(R.color.on_surface))
        textDirection = View.TEXT_DIRECTION_RTL; gravity = Gravity.START
    })
    subtitle?.let {
        box.addView(TextView(this).apply {
            text = it; textSize = 14f
            setTextColor(resources.getColor(R.color.muted))
            textDirection = View.TEXT_DIRECTION_RTL; gravity = Gravity.START
            setPadding(0, dp(2), 0, 0)
        })
    }
    return box
}

/** A rounded card containing [build]'s views; returns it so callers can add it to the column. */
fun Activity.card(build: LinearLayout.() -> Unit): MaterialCardView {
    val inner = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        layoutDirection = View.LAYOUT_DIRECTION_RTL
        setPadding(dp(16), dp(16), dp(16), dp(16))
        build()
    }
    return MaterialCardView(this).apply {
        radius = dp(18).toFloat()
        cardElevation = dp(1).toFloat()
        setContentPadding(0, 0, 0, 0)
        useCompatPadding = true
        addView(inner)
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, dp(6), 0, dp(6)) }
    }
}

fun Activity.text(s: CharSequence, size: Float = 16f, bold: Boolean = false, color: Int? = null) =
    TextView(this).apply {
        text = s; textSize = size; gravity = Gravity.START
        textDirection = View.TEXT_DIRECTION_RTL
        setLineSpacing(dp(3).toFloat(), 1f)
        setTextColor(color ?: resources.getColor(R.color.on_surface))
        if (bold) setTypeface(typeface, Typeface.BOLD)
        setPadding(0, dp(5), 0, dp(5))
    }

/** Primary filled button spanning the width. */
fun Activity.button(s: String, onClick: () -> Unit) = MaterialButton(this).apply {
    text = s; isAllCaps = false; textSize = 16f
    cornerRadius = dp(14)
    layoutParams = LinearLayout.LayoutParams(
        ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
    ).apply { setMargins(0, dp(8), 0, dp(2)) }
    setOnClickListener { onClick() }
}

/** Outlined secondary button. */
fun Activity.outlinedButton(s: String, onClick: () -> Unit) =
    MaterialButton(this, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
        text = s; isAllCaps = false; textSize = 15f
        cornerRadius = dp(14)
        layoutParams = LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ).apply { setMargins(0, dp(6), 0, dp(2)) }
        setOnClickListener { onClick() }
    }

fun Activity.toast(s: String) = Toast.makeText(this, s, Toast.LENGTH_LONG).show()

/** A numeric, password-masked field wrapped in a Material text box. */
fun Activity.pinField(hint: String): Pair<TextInputLayout, TextInputEditText> {
    val edit = TextInputEditText(this).apply {
        inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
        textDirection = View.TEXT_DIRECTION_LTR
        gravity = Gravity.CENTER
        textSize = 22f
    }
    val layout = TextInputLayout(this).apply {
        this.hint = hint
        isCounterEnabled = false
        addView(edit)
    }
    return layout to edit
}

/** Asks for the removal password; calls [onOk] only if it is correct. */
fun Activity.askPin(onOk: () -> Unit) {
    val prefs = Prefs(this)
    val wait = prefs.lockoutMinutesLeft()
    if (wait > 0) { toast("יותר מדי ניסיונות שגויים. נסה שוב בעוד $wait דקות."); return }
    val (layout, edit) = pinField("סיסמת הסרה")
    val box = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(8), dp(20), 0)
        addView(layout)
    }
    MaterialAlertDialogBuilder(this)
        .setTitle("הזן סיסמה")
        .setView(box)
        .setPositiveButton("אישור") { _, _ ->
            if (prefs.checkPin(edit.text.toString())) onOk() else toast("סיסמה שגויה")
        }
        .setNegativeButton("ביטול", null)
        .show()
}

/** Asks for a new removal password twice (minimum 6 digits). */
fun Activity.newPin(cancelable: Boolean, onDone: () -> Unit) {
    val (l1, a) = pinField("סיסמה חדשה (לפחות 6 ספרות)")
    val (l2, b) = pinField("הקלד שוב")
    val box = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(8), dp(20), 0)
        addView(l1); addView(l2)
    }
    MaterialAlertDialogBuilder(this)
        .setTitle("הגדרת סיסמת הסרה")
        .setMessage("מומלץ למסור את הסיסמה לאדם אחר (רב / הורה / חבר) ולא לשמור אותה אצלך.")
        .setView(box)
        .setCancelable(cancelable)
        .setPositiveButton("שמור") { _, _ ->
            val p = a.text.toString()
            when {
                p.length < 6 -> { toast("הסיסמה חייבת להכיל לפחות 6 ספרות"); newPin(cancelable, onDone) }
                p != b.text.toString() -> { toast("הסיסמאות אינן תואמות"); newPin(cancelable, onDone) }
                else -> { Prefs(this).setPin(p); toast("הסיסמה נשמרה"); onDone() }
            }
        }
        .apply { if (cancelable) setNegativeButton("ביטול", null) }
        .show()
}
