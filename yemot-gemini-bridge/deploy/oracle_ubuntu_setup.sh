#!/usr/bin/env bash
# Installs the Yemot <-> Gemini bridge on an Oracle Cloud Ubuntu 24.04 VM (works on ARM/aarch64 and x86).
#
#   cd ~/bogrim/yemot-gemini-bridge && bash deploy/oracle_ubuntu_setup.sh
#
# What it does (and nothing else): installs python3-venv + netfilter-persistent, copies the code to
# /opt/yemot-gemini-bridge, creates a venv, writes /opt/yemot-gemini-bridge/.env (asks for the Gemini key),
# adds *additive* iptables ACCEPT rules for the SIP/RTP UDP ports, and installs one new systemd service.
# It does not touch any other service on the machine (telegram-detector, tzofar/pkp/bra dispatchers, ...).
# Safe to re-run: existing .env is kept, rules are only added when missing.
set -euo pipefail

APP=/opt/yemot-gemini-bridge
SRC="$(cd "$(dirname "$0")/.." && pwd)"
SVC=yemot-gemini-bridge

[ "$(id -u)" -ne 0 ] || { echo "Run as the normal 'ubuntu' user (it uses sudo where needed), not as root."; exit 1; }
[ -f "$SRC/bridge/main.py" ] || { echo "Run this from the repository (bridge/main.py not found in $SRC)."; exit 1; }

echo "== 1/6 packages"
sudo apt-get update -y
echo iptables-persistent iptables-persistent/autosave_v4 boolean false | sudo debconf-set-selections
echo iptables-persistent iptables-persistent/autosave_v6 boolean false | sudo debconf-set-selections
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip netfilter-persistent iptables-persistent curl

echo "== 2/6 code + virtualenv in $APP"
id bridge >/dev/null 2>&1 || sudo useradd --system --no-create-home --shell /usr/sbin/nologin bridge
sudo mkdir -p "$APP"
sudo cp -r "$SRC/bridge" "$SRC/requirements.txt" "$SRC/.env.example" "$APP/"
[ -d "$APP/venv" ] || sudo python3 -m venv "$APP/venv"
sudo "$APP/venv/bin/pip" install --quiet --upgrade pip
sudo "$APP/venv/bin/pip" install --quiet -r "$APP/requirements.txt"

echo "== 3/6 configuration ($APP/.env)"
if [ ! -f "$APP/.env" ]; then
    default_ip="$(curl -fsS --max-time 5 https://api.ipify.org || true)"
    read -r -p "Public IPv4 that Yemot will call [${default_ip}]: " PUBLIC_IP
    PUBLIC_IP="${PUBLIC_IP:-$default_ip}"
    read -r -s -p "Gemini API key (typing is hidden; use a NEW key from a billing-enabled project): " GEMINI_API_KEY
    echo
    TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    {
        echo "GEMINI_API_KEY=$GEMINI_API_KEY"
        echo "PUBLIC_IP=$PUBLIC_IP"
        echo "ACCESS_TOKEN=$TOKEN"
        grep -v -E '^(GEMINI_API_KEY|PUBLIC_IP|ACCESS_TOKEN)=' "$APP/.env.example" | grep -v -E '^\s*#|^\s*$' || true
    } | sudo tee "$APP/.env" >/dev/null
fi
sudo chown root:bridge "$APP/.env"
sudo chmod 640 "$APP/.env"

# shellcheck disable=SC1090
set -a; source <(sudo cat "$APP/.env"); set +a
SIP_PORT="${SIP_PORT:-5060}"; RTP_MIN="${RTP_PORT_MIN:-10000}"; RTP_MAX="${RTP_PORT_MAX:-10199}"

echo "== 4/6 firewall on this VM (UDP $SIP_PORT and $RTP_MIN-$RTP_MAX)"
sudo iptables-save | sudo tee "/root/iptables-backup-$(date +%Y%m%d-%H%M%S).rules" >/dev/null
add_rule() {  # insert before the catch-all REJECT so the rule is actually reached; skip if present
    if ! sudo iptables -C INPUT "$@" 2>/dev/null; then
        pos="$(sudo iptables -L INPUT --line-numbers -n | awk '/REJECT/ {print $1; exit}')"
        if [ -n "${pos:-}" ]; then sudo iptables -I INPUT "$pos" "$@"; else sudo iptables -A INPUT "$@"; fi
    fi
}
add_rule -p udp --dport "$SIP_PORT" -j ACCEPT
add_rule -p udp --dport "$RTP_MIN:$RTP_MAX" -j ACCEPT
sudo netfilter-persistent save >/dev/null

echo "== 5/6 systemd service $SVC"
sudo tee "/etc/systemd/system/$SVC.service" >/dev/null <<UNIT
[Unit]
Description=Yemot <-> Gemini Live SIP bridge
After=network-online.target
Wants=network-online.target

[Service]
User=bridge
WorkingDirectory=$APP
EnvironmentFile=$APP/.env
ExecStart=$APP/venv/bin/python -m bridge.main
Restart=always
RestartSec=3
TimeoutStopSec=15
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now "$SVC"
sleep 2
sudo systemctl --no-pager --lines=8 status "$SVC" || true

echo "== 6/6 done"
cat <<EOF

Still to do by hand (cannot be done from inside the VM):
  Oracle Console -> Networking -> Virtual cloud networks -> your VCN -> Security Lists (or the instance's NSG)
  -> Add Ingress Rules (Source CIDR 0.0.0.0/0, IP Protocol UDP):
        destination port $SIP_PORT
        destination port range $RTP_MIN-$RTP_MAX

Then, from ANOTHER computer (checks the ports; the second line is a test call for option B):
  python3 -m bridge.probe $PUBLIC_IP
  python3 -m bridge.probe $PUBLIC_IP --token <ACCESS_TOKEN>

Yemot, option A (recommended) - extension type=sip with a registered SIP account:
  sudo $APP/venv/bin/python -m bridge.yemot_setup --extension 5 --host <SIP server from the site's
      business-switchboard tab> --env $APP/.env
  sudo systemctl restart $SVC        # then look for "registered with ..." in the log

Yemot, option B - extension type=routing_ip (no account; the token goes in routing_extension):
  type=routing_ip
  routing_ip=$PUBLIC_IP
  routing_ip_port=$SIP_PORT
  routing_extension=<ACCESS_TOKEN>
  routing_ip_cancel_star_next=yes

Your ACCESS_TOKEN is in $APP/.env (sudo cat $APP/.env | grep ACCESS_TOKEN). Logs: sudo journalctl -u $SVC -f
EOF
