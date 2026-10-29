#!/usr/bin/env bash
# One-shot install for a prepared bundle. Run on the Oracle server, from inside the extracted folder:
#     bash install_all.sh
# It installs the bridge service, connects your existing Yemot SIP account, creates/configures the Yemot
# extension, restarts the service and shows the log. Settings come from ./bundle.conf, ./.env and ./secrets/.
set -euo pipefail
cd "$(dirname "$0")"

# shellcheck disable=SC1091
source ./bundle.conf            # EXT, ACCOUNT, SIP_HOST
APP="${APP_DIR:-/opt/yemot-gemini-bridge}"
SVC=yemot-gemini-bridge
EXTRA=()
[ -n "${YEMOT_API_BASE:-}" ] && EXTRA+=(--api-base "$YEMOT_API_BASE")
[ -n "${USE_EXISTING:-}" ] && EXTRA+=(--use-existing)

echo "Bundle: $(cat BUILD 2>/dev/null || echo unknown)"
echo "################ 1/3  installing the bridge service"
BUNDLE_MODE=1 bash deploy/oracle_ubuntu_setup.sh

echo
echo "################ 2/3  connecting Yemot (account $ACCOUNT -> extension $EXT)"
set +e
(cd "$APP" && sudo ./venv/bin/python -m bridge.yemot_setup --extension "$EXT" --host "$SIP_HOST" \
    --use-account "$ACCOUNT" --token-file "$OLDPWD/secrets/yemot_api_token" --env "$APP/.env" "${EXTRA[@]}")
rc=$?
set -e
if [ "$rc" -eq 3 ]; then
    echo
    echo "Extension $EXT already exists in Yemot, so nothing was changed there."
    echo "To turn it into the Gemini line anyway:   USE_EXISTING=1 bash install_all.sh"
    exit 3
elif [ "$rc" -ne 0 ]; then
    echo "Yemot setup failed (see the message above). The bridge service is installed; fix the problem and re-run."
    exit "$rc"
fi

echo
echo "################ 3/3  starting and checking"
sudo systemctl restart "$SVC"
sleep 6
sudo journalctl -u "$SVC" -n 25 --no-pager -o cat || true
echo
if sudo journalctl -u "$SVC" -n 60 --no-pager -o cat | grep -q "registered with"; then
    echo "OK: the bridge is registered with Yemot. Call the system and dial extension $EXT."
else
    echo "NOT registered yet. Look at the lines above:"
    echo "  - 'rejected' / 'STOPPED'   -> wrong account details (do NOT keep retrying; Yemot blocks after 5 bad requests)"
    echo "  - 'no answer'              -> the Yemot SIP server is unreachable from here"
fi
cat <<MSG

Remaining by hand:
  1. Oracle Console -> your VCN -> Security List -> Add Ingress Rules (Source 0.0.0.0/0, protocol UDP):
        port 5060   and   port range 10000-10199        (without these a call connects with no sound)
  2. Delete the secrets that are still lying around in this folder and the uploaded zip:
        cd ~ && rm -rf "$(basename "$PWD")" ~/bundle.zip
     (the working copy with the keys is kept in $APP/.env, readable only by root and the service)
MSG
