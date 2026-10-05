#!/bin/bash
# AbayoNet Manager — Linux
# Run this from the folder containing abayonet.py:
#   chmod +x AbayoNet.sh
#   ./AbayoNet.sh

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1

SERVICE_NAME="abayonet"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_BIN="$(command -v python3)"

# ── helpers ──────────────────────────────────────────────────────
need_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo
        echo "  This action needs root. Re-run with:"
        echo "    sudo ./AbayoNet.sh"
        echo
        read -rp "Press Enter to return to the menu..." _
        return 1
    fi
    return 0
}

check_python() {
    if [ -z "$PYTHON_BIN" ]; then
        echo
        echo "  [ERROR] python3 was not found on this system's PATH."
        echo "  Install it first, e.g.:"
        echo "    sudo apt-get install python3 python3-pip     # Debian/Ubuntu"
        echo "    sudo dnf install python3 python3-pip         # RHEL/Fedora"
        echo
        exit 1
    fi
}

check_deps() {
    if ! "$PYTHON_BIN" -c "import pymysql" >/dev/null 2>&1; then
        echo "  First-time setup: installing required Python package (pymysql)..."
        "$PYTHON_BIN" -m pip install --quiet pymysql --break-system-packages 2>/dev/null \
            || "$PYTHON_BIN" -m pip install --quiet pymysql
        echo "  Done."
    fi
}

pause() { read -rp "Press Enter to continue..." _; }

# ── actions ──────────────────────────────────────────────────────
run_now() {
    clear
    echo "============================================================"
    echo "  Running AbayoNet in this terminal."
    echo "  Press Ctrl+C to stop it."
    echo "  (This does NOT install anything or run in the background —"
    echo "   it only runs while this terminal stays open.)"
    echo "============================================================"
    echo
    check_deps
    "$PYTHON_BIN" abayonet.py --no-browser
    echo
    echo "  AbayoNet has stopped."
    pause
}

install_service() {
    clear
    echo "============================================================"
    echo "  Installing AbayoNet as a systemd service"
    echo "============================================================"
    need_root || return
    check_deps

    RUN_USER="${SUDO_USER:-root}"
    echo "  Service will run as user: $RUN_USER"
    echo "  Working directory: $DIR"
    echo

    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=AbayoNet Enterprise Network Monitor
After=network.target mysql.service mariadb.service
Wants=mysql.service mariadb.service

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$DIR
ExecStart=$PYTHON_BIN $DIR/abayonet.py --no-browser --service
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"
    echo
    echo "  Installed and started. AbayoNet will now also start"
    echo "  automatically on boot. Check status any time with:"
    echo "    systemctl status $SERVICE_NAME"
    echo "  View live logs with:"
    echo "    journalctl -u $SERVICE_NAME -f"
    echo "  Open your browser to http://<this-server-ip>:8080"
    pause
}

uninstall_service() {
    clear
    echo "============================================================"
    echo "  Uninstalling the AbayoNet systemd service"
    echo "============================================================"
    echo "  Your database and data files are NOT deleted — only the"
    echo "  systemd service registration is removed."
    echo
    need_root || return
    read -rp "Type YES to confirm uninstall: " confirm
    if [ "$confirm" != "YES" ]; then
        echo "  Cancelled — nothing was changed."
        pause
        return
    fi
    systemctl stop "$SERVICE_NAME" 2>/dev/null
    systemctl disable "$SERVICE_NAME" 2>/dev/null
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    echo
    echo "  Service uninstalled."
    pause
}

start_service() {
    clear
    echo "============================================================"
    echo "  Starting AbayoNet Service"
    echo "============================================================"
    need_root || return
    if [ ! -f "$SERVICE_FILE" ]; then
        echo "  Service is not installed yet — use option 2 first."
        pause
        return
    fi
    systemctl start "$SERVICE_NAME"
    systemctl status "$SERVICE_NAME" --no-pager
    pause
}

stop_service() {
    clear
    echo "============================================================"
    echo "  Stopping AbayoNet Service"
    echo "============================================================"
    need_root || return
    systemctl stop "$SERVICE_NAME"
    echo "  Stopped."
    pause
}

reset_admin() {
    clear
    echo "============================================================"
    echo "  Reset Admin Password"
    echo "============================================================"
    echo "  This connects to your configured MySQL database (see"
    echo "  abayonet.cfg) and resets the 'admin' account password"
    echo "  back to the default: admin123"
    echo "  Log in and change it immediately afterwards."
    echo
    read -rp "Type YES to confirm reset: " confirm
    if [ "$confirm" != "YES" ]; then
        echo "  Cancelled — nothing was changed."
        pause
        return
    fi
    check_deps
    "$PYTHON_BIN" abayonet.py --reset-admin
    pause
}

install_deps() {
    clear
    echo "============================================================"
    echo "  Installing/repairing Python dependencies"
    echo "============================================================"
    "$PYTHON_BIN" -m pip install --upgrade pip --break-system-packages 2>/dev/null \
        || "$PYTHON_BIN" -m pip install --upgrade pip
    "$PYTHON_BIN" -m pip install pymysql --break-system-packages 2>/dev/null \
        || "$PYTHON_BIN" -m pip install pymysql
    echo
    echo "  Done."
    pause
}

show_status() {
    clear
    echo "============================================================"
    echo "  Service status"
    echo "============================================================"
    if [ ! -f "$SERVICE_FILE" ]; then
        echo "  Not installed as a service. (Use option 2 to install.)"
    else
        systemctl status "$SERVICE_NAME" --no-pager
    fi
    pause
}

# ── menu ─────────────────────────────────────────────────────────
check_python

while true; do
    clear
    echo "============================================================"
    echo "  AbayoNet Enterprise Monitor - Manager (Linux)"
    echo "============================================================"
    echo
    echo "  1. Run now                (no install — runs in this terminal)"
    echo "  2. Install as Service     (systemd, auto-starts on boot)"
    echo "  3. Uninstall Service"
    echo "  4. Start Service"
    echo "  5. Stop Service"
    echo "  6. Service status / logs"
    echo "  7. Reset admin password   (back to: admin123)"
    echo "  8. Install/repair Python dependencies"
    echo "  9. Exit"
    echo
    read -rp "Choose an option (1-9): " choice

    case "$choice" in
        1) run_now ;;
        2) install_service ;;
        3) uninstall_service ;;
        4) start_service ;;
        5) stop_service ;;
        6) show_status ;;
        7) reset_admin ;;
        8) install_deps ;;
        9) echo; echo "  Goodbye."; exit 0 ;;
        *) echo; echo "  Not a valid option — pick a number from 1 to 9."; pause ;;
    esac
done
