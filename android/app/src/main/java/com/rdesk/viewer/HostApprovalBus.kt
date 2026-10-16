package com.rdesk.viewer

import kotlinx.coroutines.CompletableDeferred

/** פרטי בקשת החיבור הנכנסת, לתצוגה במסך האישור - תואם למה שמוצג בחלון
 * האישור בצד שולחן-העבודה (HostAPI._approval: peer/ip/username/computer). */
data class ApprovalInfo(val peer: String, val ip: String?, val username: String?, val computer: String?)

/**
 * מעביר בקשת-אישור חיבור בין RDeskHostService (שרץ ברקע, בלי UI) לבין
 * HostApprovalActivity (שהשירות מרים כדי להציג למשתמש) - תהליך אחד בכל
 * רגע נתון, כמו שהמארח מקבל סשן אחד בלבד.
 */
object HostApprovalBus {
    @Volatile var info: ApprovalInfo? = null
        private set
    @Volatile private var pending: CompletableDeferred<Boolean>? = null

    fun request(approvalInfo: ApprovalInfo): CompletableDeferred<Boolean> {
        val d = CompletableDeferred<Boolean>()
        info = approvalInfo
        pending = d
        return d
    }

    /** אם כבר נענתה (או שלא הייתה בקשה פעילה) - קריאה חזרה היא no-op בטוח. */
    fun resolve(allow: Boolean) {
        pending?.complete(allow)
        pending = null
        info = null
    }
}
