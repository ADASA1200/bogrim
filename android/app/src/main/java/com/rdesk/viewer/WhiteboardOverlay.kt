package com.rdesk.viewer

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.view.MotionEvent
import android.view.View
import org.json.JSONArray
import org.json.JSONObject

/**
 * שכבת שיתוף סקיצות (כמו Whiteboard של AnyDesk) מעל המסך המרוחק - תואם
 * בדיוק לפרוטוקול ה-"wb" (ערוץ control: {"t":"wb","data":...}) ול-
 * webui/src/components/Whiteboard.jsx: נקודות מנורמלות (0..1) יחסית
 * ל-content rect של התמונה (לא לכל ה-View - חשוב כש-SCALE_ASPECT_FIT
 * משאיר פסי letterbox).
 */
class WhiteboardOverlay(
    context: Context,
    private val contentRect: () -> FloatArray,   // [left, top, w, h] בתוך ה-View, בפיקסלים
) : View(context) {

    private data class Stroke(val points: MutableList<FloatArray>, val color: String = "#FF3B30", val widthDp: Float = 3f)

    var active = false
    var onStroke: ((JSONObject) -> Unit)? = null

    private val strokes = mutableListOf<Stroke>()
    private var current: Stroke? = null
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val density = resources.displayMetrics.density

    private fun toNormalized(x: Float, y: Float): FloatArray {
        val r = contentRect()
        return floatArrayOf(((x - r[0]) / r[2]).coerceIn(0f, 1f), ((y - r[1]) / r[3]).coerceIn(0f, 1f))
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (!active) return false
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                current = Stroke(mutableListOf(toNormalized(event.x, event.y)))
                invalidate()
            }
            MotionEvent.ACTION_MOVE -> {
                current?.points?.add(toNormalized(event.x, event.y))
                invalidate()
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                val s = current ?: return true
                current = null
                if (s.points.size >= 2) {
                    strokes.add(s)
                    onStroke?.invoke(strokeToJson(s))
                }
                invalidate()
            }
            else -> return false
        }
        return true
    }

    private fun strokeToJson(s: Stroke): JSONObject {
        val pts = JSONArray()
        for (p in s.points) pts.put(JSONArray().put(p[0].toDouble()).put(p[1].toDouble()))
        return JSONObject().put("type", "stroke").put("points", pts).put("color", s.color).put("width", s.widthDp.toDouble())
    }

    /** הודעת "wb" שהתקבלה מהצד השני - stroke חדש או {"type":"clear"}. */
    fun applyRemote(data: JSONObject?) {
        if (data == null) return
        if (data.optString("type") == "clear") {
            strokes.clear()
            invalidate()
            return
        }
        val pointsJson = data.optJSONArray("points") ?: return
        val points = mutableListOf<FloatArray>()
        for (i in 0 until pointsJson.length()) {
            val p = pointsJson.optJSONArray(i) ?: continue
            points.add(floatArrayOf(p.optDouble(0).toFloat(), p.optDouble(1).toFloat()))
        }
        if (points.size < 2) return
        strokes.add(Stroke(points, data.optString("color", "#FF3B30"), data.optDouble("width", 3.0).toFloat()))
        invalidate()
    }

    fun clearLocal() {
        strokes.clear()
        current = null
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val r = contentRect()
        for (s in strokes) drawStroke(canvas, s, r)
        current?.let { drawStroke(canvas, it, r) }
    }

    private fun drawStroke(canvas: Canvas, s: Stroke, r: FloatArray) {
        if (s.points.size < 2) return
        paint.color = runCatching { Color.parseColor(s.color) }.getOrDefault(Color.RED)
        paint.strokeWidth = s.widthDp * density
        val path = Path()
        val p0 = s.points[0]
        path.moveTo(r[0] + p0[0] * r[2], r[1] + p0[1] * r[3])
        for (i in 1 until s.points.size) {
            val p = s.points[i]
            path.lineTo(r[0] + p[0] * r[2], r[1] + p[1] * r[3])
        }
        canvas.drawPath(path, paint)
    }
}
