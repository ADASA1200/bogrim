package org.videoblock

import android.app.admin.DeviceAdminReceiver
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.BroadcastReceiver
import android.content.ComponentName
import android.content.Context
import android.content.Intent

class AdminReceiver : DeviceAdminReceiver() {
    override fun onEnabled(context: Context, intent: Intent) = Policy.enforceAsync(context)
    override fun onProfileProvisioningComplete(context: Context, intent: Intent) =
        Policy.enforceAsync(context)
}

class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action !in setOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_LOCKED_BOOT_COMPLETED,
                Intent.ACTION_MY_PACKAGE_REPLACED)) return
        EnforceJob.schedule(context)
        Policy.enforceAsync(context)
    }
}

/** Safety net: re-applies the policy every 15 minutes even if a broadcast was missed. */
class EnforceJob : JobService() {
    override fun onStartJob(params: JobParameters): Boolean {
        Thread {
            runCatching { Policy.enforce(applicationContext) }
            jobFinished(params, false)
        }.start()
        return true
    }

    override fun onStopJob(params: JobParameters) = true

    companion object {
        fun schedule(c: Context) {
            val js = c.getSystemService(Context.JOB_SCHEDULER_SERVICE) as? JobScheduler ?: return
            if (js.getPendingJob(1) != null) return
            js.schedule(
                JobInfo.Builder(1, ComponentName(c, EnforceJob::class.java))
                    .setPeriodic(15 * 60 * 1000L)
                    .setPersisted(true)
                    .build()
            )
        }
    }
}
