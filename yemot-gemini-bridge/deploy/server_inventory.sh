#!/usr/bin/env bash
# Read-only inventory of the server: what runs, what starts at boot, which ports are open, which code exists.
# Changes nothing. Passwords, keys and tokens are masked in everything it prints.
#
#   bash server_inventory.sh > /tmp/inventory.txt 2>&1
#   bash server_inventory.sh quick        # short overview
#
mask() {
    sed -E \
        -e 's/AIza[0-9A-Za-z_-]{20,}/AIza***MASKED***/g' \
        -e 's/(sk-|ghp_|github_pat_|xox[bap]-)[0-9A-Za-z_-]{16,}/\1***MASKED***/g' \
        -e 's/([A-Za-z_]*(KEY|PASS|PASSWORD|PWD|TOKEN|SECRET|AUTH|CREDENTIAL)[A-Za-z_]*[[:space:]]*[=:][[:space:]]*).*/\1***MASKED***/I' \
        -e 's#(://[^/:@[:space:]]+:)[^@/[:space:]]+@#\1***MASKED***@#g' \
        -e 's/(Bearer|Basic)[[:space:]]+[A-Za-z0-9._~+\/=-]{12,}/\1 ***MASKED***/g' \
        -e 's/["'"'"'][A-Za-z0-9_\/+=.-]{24,}["'"'"']/"***MASKED-LONG-STRING***"/g'
}
section() { printf '\n\n########## %s ##########\n' "$1"; }
run() { printf '\n$ %s\n' "$*"; "$@" 2>&1 | mask; }
sh_() { printf '\n$ %s\n' "$1"; bash -c "$1" 2>&1 | mask; }

if [ "${1:-}" = quick ]; then   # short overview: bash server_inventory.sh quick
    section "RUNNING SERVICES"; sh_ 'systemctl list-units --type=service --state=running --no-pager --no-legend'
    section "OPEN PORTS"; sh_ 'sudo ss -lntup 2>/dev/null || ss -lntup'
    section "FOLDERS"; sh_ 'ls -la /opt /home/ubuntu /srv 2>/dev/null'
    printf '\n########## END ##########\n'; exit 0
fi

section "SYSTEM"
sh_ 'date; uptime; hostnamectl 2>/dev/null | head -8; nproc; free -h; df -h / /opt /home 2>/dev/null'
sh_ 'for p in python3 python3.11 python3.12 python3.13 node npm docker git; do printf "%-10s " $p; (command -v $p >/dev/null && $p --version 2>&1 | head -1) || echo "-"; done'
sh_ 'curl -fsS --max-time 5 https://api.ipify.org; echo'

section "SYSTEMD: RUNNING SERVICES"
sh_ 'systemctl list-units --type=service --state=running --no-pager --no-legend'
section "SYSTEMD: FAILED"
sh_ 'systemctl list-units --state=failed --no-pager --no-legend'
section "SYSTEMD: ENABLED AT BOOT"
sh_ 'systemctl list-unit-files --type=service --state=enabled --no-pager --no-legend'
section "SYSTEMD: CUSTOM UNIT FILES (/etc/systemd/system), secrets masked"
sh_ 'ls -la /etc/systemd/system/*.service 2>/dev/null'
sh_ 'for f in /etc/systemd/system/*.service; do [ -f "$f" ] && { echo "--- $f"; cat "$f"; }; done'
section "SYSTEMD TIMERS / CRON"
sh_ 'systemctl list-timers --all --no-pager | head -25'
sh_ 'crontab -l 2>/dev/null; sudo crontab -l 2>/dev/null; ls /etc/cron.d 2>/dev/null'

section "OPEN PORTS (who listens)"
sh_ 'sudo ss -lntup 2>/dev/null || ss -lntup'

section "PROCESSES"
sh_ 'ps -eo pid,user,%cpu,%mem,etime,args --sort=-%mem | head -30'
sh_ 'ps -eo pid,user,etime,args | grep -E "python|node|java|docker" | grep -v grep'
sh_ 'docker ps -a 2>/dev/null || echo "no docker"'

section "FIREWALL"
sh_ 'sudo iptables -L INPUT -n -v --line-numbers 2>/dev/null | head -30'
sh_ 'sudo ufw status 2>/dev/null || echo "ufw: not installed"'

section "FILES (outside venv / caches), size and date"
sh_ 'sudo find /opt /srv /var/www /home /root -maxdepth 4 -type f \( -path "*/venv/*" -o -path "*/.venv/*" -o -path "*/node_modules/*" -o -path "*/__pycache__/*" -o -path "*/.cache/*" -o -path "*/.git/*" -o -path "*/site-packages/*" \) -prune -o -type f -printf "%TY-%Tm-%Td %TH:%TM  %8s  %u  %p\n" 2>/dev/null | sort -k4 | head -400'
section "DIRECTORY SIZES"
sh_ 'sudo du -sh /opt/* /srv/* /home/* /var/www/* /root/* 2>/dev/null'

section "CODE FILES: lines + sha256"
sh_ 'sudo find /opt /srv /home /root -maxdepth 4 \( -path "*/venv/*" -o -path "*/.venv/*" -o -path "*/node_modules/*" -o -path "*/site-packages/*" -o -path "*/.cache/*" \) -prune -o \( -name "*.py" -o -name "*.js" -o -name "*.sh" -o -name "*.service" -o -name "*.ini" -o -name "*.conf" \) -type f -print 2>/dev/null | while read f; do printf "%6s lines  %s  %s\n" "$(sudo wc -l < "$f")" "$(sudo sha256sum "$f" | cut -c1-12)" "$f"; done'

section "CODE FILES: first 25 lines of each .py (masked)"
sh_ 'sudo find /opt /srv /home /root -maxdepth 4 \( -path "*/venv/*" -o -path "*/.venv/*" -o -path "*/site-packages/*" -o -path "*/.cache/*" \) -prune -o -name "*.py" -type f -print 2>/dev/null | head -60 | while read f; do echo; echo "=== $f"; sudo head -25 "$f"; done'

section "ENV FILES (names of settings only, values hidden)"
sh_ 'for f in $(sudo find /opt /srv /home /root -maxdepth 3 -name ".env*" -type f 2>/dev/null); do echo "--- $f"; sudo grep -vE "^\s*#|^\s*$" "$f" | cut -d= -f1; done'

section "PYTHON PACKAGES per venv (names + versions)"
sh_ 'for v in $(sudo find /opt /srv /home -maxdepth 3 -type d -name venv 2>/dev/null); do echo "--- $v"; sudo $v/bin/pip list --format=freeze 2>/dev/null | head -40; done'

section "RECENT ERRORS (last 24h, per custom service)"
sh_ 'for s in $(ls /etc/systemd/system/*.service 2>/dev/null | xargs -n1 basename 2>/dev/null); do echo "--- $s"; sudo journalctl -u $s --since "24 hours ago" -p warning --no-pager -o cat 2>/dev/null | tail -8; done'

section "NETWORK UDP FRAGMENT COUNTERS (Oracle drop check)"
sh_ 'grep -E "^Ip:" /proc/net/snmp | cut -d" " -f1,10,11,15,16,17 | head -2; awk "/^Ip:/ {for(i=1;i<=NF;i++) h[i]=\$i; getline; for(i=1;i<=NF;i++) if(h[i] ~ /Reasm|Frag/) print h[i], \$i}" /proc/net/snmp'

printf '\n\n########## END ##########\n'
