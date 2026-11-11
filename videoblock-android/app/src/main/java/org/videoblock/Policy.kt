package org.videoblock

import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.UserManager
import android.provider.Settings
import android.provider.Telephony
import android.telecom.TelecomManager
import android.util.Log
import java.util.concurrent.Executors

/**
 * Applies every restriction. Idempotent: safe to call at any time (boot, app installed,
 * settings changed, periodic job). Requires the app to be Device Owner.
 */
object Policy {
    private const val TAG = "VideoBlock"
    private val worker = Executors.newSingleThreadExecutor()

    fun admin(c: Context) = ComponentName(c, AdminReceiver::class.java)
    fun dpm(c: Context) = c.getSystemService(DevicePolicyManager::class.java)!!
    fun isDeviceOwner(c: Context) = dpm(c).isDeviceOwnerApp(c.packageName)

    /** User restrictions that keep the protection in place and close known bypasses. */
    private val restrictions = buildList {
        add(UserManager.DISALLOW_FACTORY_RESET)        // no reset from Settings
        add(UserManager.DISALLOW_SAFE_BOOT)            // safe mode would stop the filter
        add(UserManager.DISALLOW_DEBUGGING_FEATURES)   // no ADB / developer options
        add(UserManager.DISALLOW_ADD_USER)             // no clean secondary user / guest
        add(UserManager.DISALLOW_REMOVE_USER)
        add(UserManager.DISALLOW_APPS_CONTROL)         // can't force-stop, clear data, or un-suspend apps
        add(UserManager.DISALLOW_CONFIG_VPN)           // can't switch off or replace the filter VPN
        add(UserManager.DISALLOW_USB_FILE_TRANSFER)    // can't copy video files from a computer
        add(UserManager.DISALLOW_MOUNT_PHYSICAL_MEDIA) // no SD card / USB stick with videos
        add(UserManager.DISALLOW_CONFIG_DATE_TIME)     // protects the PIN lockout timer
        add(UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES)
        if (Build.VERSION.SDK_INT >= 29) {
            add(UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES_GLOBALLY)
            add(UserManager.DISALLOW_CONFIG_PRIVATE_DNS)
        }
    }

    fun enforceAsync(c: Context) {
        val app = c.applicationContext
        worker.execute { runCatching { enforce(app) }.onFailure { Log.e(TAG, "enforce failed", it) } }
    }

    @Synchronized
    fun enforce(c: Context) {
        if (!isDeviceOwner(c)) return
        val dpm = dpm(c)
        val admin = admin(c)
        val prefs = Prefs(c)

        dpm.setUninstallBlocked(admin, c.packageName, true)
        restrictions.forEach { dpm.addUserRestriction(admin, it) }
        if (Build.VERSION.SDK_INT >= 29) dpm.setGlobalPrivateDnsModeOpportunistic(admin)
        dpm.setCameraDisabled(admin, prefs.blockCamera)

        // Always-on VPN = the DNS filter is started by the system at boot and cannot be turned off.
        if (dpm.getAlwaysOnVpnPackage(admin) != c.packageName) {
            runCatching { dpm.setAlwaysOnVpnPackage(admin, c.packageName, false) }
                .onFailure { Log.e(TAG, "always-on VPN", it) }
        }

        // Chrome: turn off its built-in DNS-over-HTTPS so it must use our filter.
        runCatching {
            dpm.setApplicationRestrictions(admin, "com.android.chrome",
                Bundle().apply { putString("DnsOverHttpsMode", "off") })
        }

        applyAppBlocking(c, prefs)
    }

    /** Everything that should currently be blocked, minus packages that must never be touched. */
    fun computeTargets(c: Context, prefs: Prefs = Prefs(c)): Set<String> {
        val essential = essentialPackages(c)
        val installed = c.packageManager.getInstalledApplications(0).map { it.packageName }.toSet()
        val auto = detectVideoApps(c) + (Blocklist.videoPackages intersect installed)
        return ((auto - prefs.allowed) + (prefs.forceBlocked intersect installed)) - essential
    }

    private fun applyAppBlocking(c: Context, prefs: Prefs) {
        val dpm = dpm(c)
        val admin = admin(c)
        val targets = computeTargets(c, prefs)

        val release = prefs.suspendedByUs - targets
        if (release.isNotEmpty()) dpm.setPackagesSuspended(admin, release.toTypedArray(), false)
        val failed = dpm.setPackagesSuspended(admin, targets.toTypedArray(), true).toSet()
        prefs.suspendedByUs = targets - failed
        if (failed.isNotEmpty()) Log.w(TAG, "could not suspend: $failed")

        // Known video apps are also hidden from the launcher entirely.
        val hideTargets = targets intersect (Blocklist.videoPackages + prefs.forceBlocked)
        (prefs.hiddenByUs - hideTargets).forEach { dpm.setApplicationHidden(admin, it, false) }
        prefs.hiddenByUs = hideTargets.filter { dpm.setApplicationHidden(admin, it, true) }.toSet()
    }

    /** Every installed app that can open a video file, plus every web browser. */
    fun detectVideoApps(c: Context): Set<String> {
        val pm = c.packageManager
        val flags = PackageManager.MATCH_ALL or PackageManager.MATCH_DISABLED_COMPONENTS
        val probes = listOf(
            Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("content://x/v.mp4"), "video/mp4"),
            Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("content://x/v"), "video/*"),
            Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("file:///sdcard/v.mkv"), "video/x-matroska"),
            Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("https://x/v.m3u8"), "application/x-mpegURL"),
            Intent(Intent.ACTION_VIEW).setDataAndType(Uri.parse("https://x/v.mp4"), "video/mp4"),
            Intent("com.android.camera.action.REVIEW").setDataAndType(Uri.parse("content://x/v"), "video/*"),
            // Web browsers can play any video on the web.
            Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com"))
                .addCategory(Intent.CATEGORY_BROWSABLE),
        )
        return probes.flatMap { pm.queryIntentActivities(it, flags) }
            .map { it.activityInfo.packageName }.toSet()
    }

    /** Packages that must never be suspended or the phone would stop working. */
    fun essentialPackages(c: Context): Set<String> {
        val pm = c.packageManager
        val out = mutableSetOf(
            c.packageName, "android", "com.android.systemui", "com.android.settings",
            "com.android.phone", "com.android.server.telecom", "com.google.android.gms",
            "com.android.vending", "com.google.android.packageinstaller", "com.android.packageinstaller",
            "com.google.android.permissioncontroller", "com.android.permissioncontroller",
            "com.android.providers.media", "com.google.android.providers.media.module",
            "com.android.documentsui", "com.google.android.documentsui",
            "com.google.android.webview", "com.android.webview",
        )
        fun resolve(i: Intent) = pm.resolveActivity(i, PackageManager.MATCH_DEFAULT_ONLY)
            ?.activityInfo?.packageName?.let { if (it != "android") out += it }
        resolve(Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME))
        resolve(Intent(Settings.ACTION_SETTINGS))
        resolve(Intent(Intent.ACTION_DIAL))
        c.getSystemService(TelecomManager::class.java)?.defaultDialerPackage?.let { out += it }
        Telephony.Sms.getDefaultSmsPackage(c)?.let { out += it }
        pm.queryIntentServices(Intent("android.view.InputMethod"), 0)
            .forEach { out += it.serviceInfo.packageName }
        return out
    }

    /** Removes all protection and gives up Device Owner. Only reachable with the PIN and if not permanent. */
    fun release(c: Context) {
        val dpm = dpm(c)
        val admin = admin(c)
        val prefs = Prefs(c)
        check(!prefs.permanent)
        dpm.setPackagesSuspended(admin, prefs.suspendedByUs.toTypedArray(), false)
        prefs.hiddenByUs.forEach { dpm.setApplicationHidden(admin, it, false) }
        prefs.suspendedByUs = emptySet(); prefs.hiddenByUs = emptySet()
        restrictions.forEach { dpm.clearUserRestriction(admin, it) }
        dpm.setCameraDisabled(admin, false)
        runCatching { dpm.setAlwaysOnVpnPackage(admin, null, false) }
        dpm.setUninstallBlocked(admin, c.packageName, false)
        c.stopService(Intent(c, DnsVpnService::class.java))
        @Suppress("DEPRECATION") dpm.clearDeviceOwnerApp(c.packageName)
    }
}
