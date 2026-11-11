# Runs on the device via its own adbd (self-ADB), after the user approves debugging.
# Prints VB_* status lines that the app parses. Does not disable or remove anything by itself.
USERS=$(pm list users 2>/dev/null | grep -c 'UserInfo{')
echo "VB_USERS:$USERS"
for t in $(dumpsys account 2>/dev/null | sed -n 's/^ *Account {.*type=\([^ ,}]*\).*/\1/p' | sort -u); do
  echo "VB_ACCOUNT:$t"
done
# Device Owner cannot be set while user accounts exist; report them instead of touching them.
pm grant org.videoblock android.permission.WRITE_SECURE_SETTINGS >/dev/null 2>&1
echo "VB_SET_OWNER_BEGIN"
dpm set-device-owner org.videoblock/.AdminReceiver 2>&1 | while IFS= read -r line; do
  echo "VB_OWNER_OUT:$line"
done
if dumpsys device_policy 2>/dev/null | grep -q 'Device Owner'; then
  echo "VB_RESULT:OK"
else
  echo "VB_RESULT:FAILED"
fi
