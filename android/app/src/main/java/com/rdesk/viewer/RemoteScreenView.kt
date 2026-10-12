package com.rdesk.viewer

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.HapticFeedbackConstants
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.widget.FrameLayout
import org.json.JSONObject
import org.webrtc.RendererCommon
import org.webrtc.SurfaceViewRenderer
import org.webrtc.VideoTrack
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min

/**
 * מציג את המסך המרוחק ותרגם מגע לעכבר:
 *  - מצב טאצ'פד (ברירת מחדל): אצבע זזה = הסמן זז יחסית; הקשה = קליק שמאלי;
 *    לחיצה ארוכה = קליק ימני; הקשה והחזקה (פעמיים) וגרירה = גרירה; שתי אצבעות = גלילה.
 *  - מצב ישיר: הסמן קופץ למקום האצבע; גרירה = לחיצה וגרירה.
 */
class RemoteScreenView(
    context: Context,
    private val sendEvent: (JSONObject) -> Unit,
) : FrameLayout(context), RendererCommon.RendererEvents {

    val renderer = SurfaceViewRenderer(context)
    private val cursor = CursorView(context)
    private val handler = Handler(Looper.getMainLooper())
    private val slop = ViewConfiguration.get(context).scaledTouchSlop
    private val density = resources.displayMetrics.density

    var directMode = false
    var viewOnly = false

    private var videoW = 0
    private var videoH = 0
    private var track: VideoTrack? = null

    // מיקום הסמן, מנורמל (0..1) ביחס לתמונה
    private var cx = 0.5f
    private var cy = 0.5f

    private var downX = 0f
    private var downY = 0f
    private var lastX = 0f
    private var lastY = 0f
    private var moved = false
    private var longFired = false
    private var dragging = false
    private var directDown = false
    private var twoFinger = false
    private var lastAvgY = 0f
    private var scrollAccum = 0f
    private var lastTapUp = 0L
    private var lastMoveSent = 0L

    private val longPress = Runnable {
        if (!moved && !twoFinger) {
            longFired = true
            performHapticFeedback(HapticFeedbackConstants.LONG_PRESS)
            click("right")
        }
    }

    init {
        setBackgroundColor(Color.BLACK)
        renderer.init(RDeskClient.eglBase!!.eglBaseContext, this)
        renderer.setScalingType(RendererCommon.ScalingType.SCALE_ASPECT_FIT)
        renderer.setEnableHardwareScaler(true)
        addView(renderer, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        addView(cursor, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        layoutDirection = LAYOUT_DIRECTION_LTR      // התמונה והמגע אף פעם לא מתהפכים
    }

    fun attach(t: VideoTrack) {
        track?.removeSink(renderer)
        track = t
        t.addSink(renderer)
    }

    fun release() {
        track?.removeSink(renderer)
        track = null
        renderer.release()
    }

    override fun onFirstFrameRendered() {}

    override fun onFrameResolutionChanged(w: Int, h: Int, rotation: Int) {
        videoW = if (rotation % 180 == 0) w else h
        videoH = if (rotation % 180 == 0) h else w
        post { updateCursor() }
    }

    // ---- מלבן התמונה בתוך ה-View (SCALE_ASPECT_FIT, ממורכז)
    private fun contentRect(): FloatArray {
        val vw = width.toFloat()
        val vh = height.toFloat()
        if (videoW <= 0 || videoH <= 0 || vw <= 0 || vh <= 0) return floatArrayOf(0f, 0f, max(vw, 1f), max(vh, 1f))
        val s = min(vw / videoW, vh / videoH)
        val cw = videoW * s
        val ch = videoH * s
        return floatArrayOf((vw - cw) / 2f, (vh - ch) / 2f, cw, ch)
    }

    private fun updateCursor() {
        val r = contentRect()
        cursor.setPos(r[0] + cx * r[2], r[1] + cy * r[3])
    }

    private fun setCursorFromView(x: Float, y: Float) {
        val r = contentRect()
        cx = ((x - r[0]) / r[2]).coerceIn(0f, 1f)
        cy = ((y - r[1]) / r[3]).coerceIn(0f, 1f)
        updateCursor()
    }

    private fun moveCursorBy(dx: Float, dy: Float) {
        val r = contentRect()
        val gain = 1.7f
        cx = (cx + dx / r[2] * gain).coerceIn(0f, 1f)
        cy = (cy + dy / r[3] * gain).coerceIn(0f, 1f)
        updateCursor()
    }

    // ---- שליחת אירועים
    private fun ev(t: String): JSONObject = JSONObject().put("t", t).put("x", cx.toDouble()).put("y", cy.toDouble())

    private fun sendMove(force: Boolean = false) {
        val now = SystemClock.uptimeMillis()
        if (!force && now - lastMoveSent < 16) return
        lastMoveSent = now
        sendEvent(ev("mm"))
    }

    private fun button(down: Boolean, b: String) = sendEvent(ev(if (down) "md" else "mu").put("b", b))

    private fun click(b: String) {
        button(true, b)
        button(false, b)
    }

    override fun onTouchEvent(e: MotionEvent): Boolean {
        if (viewOnly) return true
        when (e.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = e.x; downY = e.y; lastX = e.x; lastY = e.y
                moved = false; longFired = false; twoFinger = false; directDown = false
                dragging = !directMode && lastTapUp != 0L && e.eventTime - lastTapUp < 300
                if (directMode) {
                    setCursorFromView(e.x, e.y)
                    sendMove(force = true)
                }
                if (dragging) button(true, "left")
                handler.postDelayed(longPress, 500)
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                if (e.pointerCount == 2) {
                    twoFinger = true
                    handler.removeCallbacks(longPress)
                    lastAvgY = (e.getY(0) + e.getY(1)) / 2f
                    scrollAccum = 0f
                }
            }
            MotionEvent.ACTION_MOVE -> {
                if (twoFinger) {
                    if (e.pointerCount >= 2) {
                        val avg = (e.getY(0) + e.getY(1)) / 2f
                        scrollAccum += avg - lastAvgY
                        lastAvgY = avg
                        val step = 28f * density
                        while (abs(scrollAccum) >= step) {
                            val dir = if (scrollAccum > 0) 1 else -1
                            sendEvent(JSONObject().put("t", "ms").put("dx", 0).put("dy", dir))
                            scrollAccum -= dir * step
                        }
                    }
                } else {
                    if (!moved && hypot(e.x - downX, e.y - downY) > slop) {
                        moved = true
                        handler.removeCallbacks(longPress)
                        if (directMode && !longFired) {
                            button(true, "left")
                            directDown = true
                        }
                    }
                    if (moved) {
                        if (directMode) setCursorFromView(e.x, e.y) else moveCursorBy(e.x - lastX, e.y - lastY)
                        sendMove()
                    }
                    lastX = e.x; lastY = e.y
                }
            }
            MotionEvent.ACTION_UP -> {
                handler.removeCallbacks(longPress)
                when {
                    twoFinger -> Unit
                    dragging -> { button(false, "left"); dragging = false; lastTapUp = 0L }
                    directDown -> { button(false, "left"); directDown = false }
                    !moved && !longFired && e.eventTime - e.downTime < 300 -> {
                        click("left")
                        lastTapUp = e.eventTime
                    }
                }
            }
            MotionEvent.ACTION_CANCEL -> {
                handler.removeCallbacks(longPress)
                if (dragging || directDown) button(false, "left")
                dragging = false; directDown = false; twoFinger = false
            }
        }
        return true
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        updateCursor()
    }

    /** חץ קטן שמראה איפה הסמן המרוחק (הוא לא כלול בווידאו). */
    private class CursorView(context: Context) : View(context) {
        private var px = 0f
        private var py = 0f
        private val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE; style = Paint.Style.FILL }
        private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.BLACK; style = Paint.Style.STROKE; strokeWidth = 2f * resources.displayMetrics.density
        }
        private val path = Path()

        fun setPos(x: Float, y: Float) { px = x; py = y; invalidate() }

        override fun onDraw(canvas: Canvas) {
            val d = resources.displayMetrics.density
            path.reset()
            path.moveTo(px, py)
            path.lineTo(px, py + 20f * d)
            path.lineTo(px + 5f * d, py + 15f * d)
            path.lineTo(px + 10f * d, py + 24f * d)
            path.lineTo(px + 13f * d, py + 22.5f * d)
            path.lineTo(px + 8f * d, py + 14f * d)
            path.lineTo(px + 15f * d, py + 14f * d)
            path.close()
            canvas.drawPath(path, fill)
            canvas.drawPath(path, stroke)
        }
    }
}
