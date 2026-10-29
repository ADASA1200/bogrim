#!/usr/bin/env bash
# Read-only diagnosis of the Yemot <-> Gemini bridge on the server. Prints no passwords or keys.
#
#   bash diagnose.sh            # includes a 45-second SIP capture: CALL THE EXTENSION when it says so
#   bash diagnose.sh 90         # longer capture
#   bash diagnose.sh 0          # skip the capture
#   NO_PROBE=1 bash diagnose.sh # skip the local Gemini test call (it costs a few cents of Gemini usage)
#
# Paste the whole output back. Changes nothing except installing tcpdump if it is missing.
APP="${APP_DIR:-/opt/yemot-gemini-bridge}"
SVC=yemot-gemini-bridge
SECONDS_TO_CAPTURE="${1:-45}"

section() { printf '\n===== %s =====\n' "$1"; }

section "service"
systemctl is-active "$SVC"
sudo journalctl -u "$SVC" --since "30 min ago" --no-pager -o cat | tail -20

section "code version (should show 'yes' on all four)"
for pat in "def punch:bridge/rtp.py" "def noise_gate:bridge/audio.py" "hangup_on_hash:bridge/config.py" "def flush:bridge/audio.py"; do
    printf '%-18s %s\n' "${pat%%:*}" "$(sudo grep -q "${pat%%:*}" "$APP/${pat#*:}" 2>/dev/null && echo yes || echo NO)"
done

section "settings (no secrets)"
sudo grep -E '^(PUBLIC_IP|SIP_PORT|RTP_PORT_MIN|RTP_PORT_MAX|YEMOT_REGISTER_HOST|YEMOT_SIP_USER|CODEC_PREFERENCE|GEMINI_VOICE|VAD_SILENCE_MS|OUTPUT_VOLUME|INPUT_NOISE_GATE_RMS)=' "$APP/.env"
echo "password present: $(sudo grep -c '^YEMOT_SIP_PASSWORD=.' "$APP/.env")   gemini key present: $(sudo grep -c '^GEMINI_API_KEY=.' "$APP/.env")"
echo "public IP seen from this server: $(curl -fsS --max-time 5 https://api.ipify.org || echo unknown)"

section "sockets (UDP 5060 and RTP range)"
sudo ss -lunp 2>/dev/null | grep -E ':5060 |:10[0-9]{3} ' || echo "nothing listening on 5060 -> the service is not running"

section "VM firewall, INPUT chain with packet counters"
sudo iptables -L INPUT -n -v --line-numbers | head -20

if [ -z "${NO_PROBE:-}" ]; then
    section "local end-to-end test call (SIP + RTP + real Gemini), ~8 seconds"
    TOKEN="$(sudo grep '^ACCESS_TOKEN=' "$APP/.env" | cut -d= -f2-)"
    if [ -n "$TOKEN" ]; then
        (cd "$APP" && timeout 40 ./venv/bin/python -m bridge.probe 127.0.0.1 --token "$TOKEN" --seconds 8 --rtp-port 41000 2>&1 | sed "s/$TOKEN/<token>/g")
    else
        echo "no ACCESS_TOKEN in .env, skipped"
    fi
fi

if [ "$SECONDS_TO_CAPTURE" -gt 0 ] 2>/dev/null; then
    command -v tcpdump >/dev/null || sudo apt-get install -y tcpdump >/dev/null 2>&1
    section "SIP traffic for ${SECONDS_TO_CAPTURE}s  >>> CALL THE EXTENSION NOW <<<"
    sudo timeout "$SECONDS_TO_CAPTURE" tcpdump -ni any -l -A -s0 "udp port 5060" 2>/dev/null \
        | grep -E "^[0-9:.]+ IP|^(INVITE|REGISTER|OPTIONS|SIP/2.0|CANCEL|BYE|ACK)" | head -80
    echo "(end of capture)"
    section "bridge log during the capture"
    sudo journalctl -u "$SVC" --since "$((SECONDS_TO_CAPTURE + 20)) seconds ago" --no-pager -o cat | tail -30
fi
echo; echo "===== done ====="
