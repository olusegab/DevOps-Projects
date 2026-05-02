╔══════════════════════════════════════════════════════════════╗
║      AbayoNet Enterprise Monitor v4.0 — Install Guide       ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  WHAT'S NEW IN v4.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ DATABASE LOCK FIX
   Root cause identified and fixed: each monitoring thread was
   opening a new SQLite connection and never closing it properly.
   Fix: per-thread connection pool (threading.local) + 30s busy
   timeout + WAL mode + automatic retry on lock.

✅ LOGIN PAGE
   Secure login with username/password before accessing dashboard.
   Session tokens expire after 24 hours.

✅ USER ROLES
   Admin:     Full access — add/edit/delete hosts, manage users,
              change settings, import/export.
   Read-Only: View-only — dashboard, hosts, alerts, reports.
              Cannot add, edit, or delete anything.

✅ USER MANAGEMENT (Admin Dashboard)
   Create users, reset passwords, enable/disable accounts.
   Cannot delete the primary admin (user ID 1).

✅ HOST IMPORT / EXPORT
   Export all monitored hosts as JSON or CSV.
   Import JSON on another laptop to copy your host list.
   Transferred hosts start monitoring immediately.

✅ CHARTS FIXED
   - Dashboard: latency multi-line chart (up to 6 hosts)
   - Detail: dual-axis latency + packet loss chart
   - Detail: jitter bar chart
   - 24h uptime timeline bar (48 blocks × 30 min)
   Charts properly destroy/recreate when switching hosts
   or changing time range (1H/3H/6H/12H/24H).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STEP 1 — INSTALL PYTHON (one time only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Go to: https://python.org/downloads
2. Click "Download Python 3.x" (latest)
3. Run the installer
4. ✅ CHECK: "Add Python to PATH" on the first screen
5. Click "Install Now" → wait → Close

Verify: open CMD and type:  python --version
Should show: Python 3.x.x

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STEP 2 — EXTRACT THE ZIP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Right-click AbayoNet.zip → "Extract All..."
2. Choose a permanent folder: e.g. C:\AbayoNet\
3. Click Extract
4. You will see:
      abayonet.py          ← Main server engine
      START_ABAYONET.bat   ← Double-click to launch
      static\index.html    ← Dashboard UI
      INSTALL_GUIDE.txt    ← This file
      data\                ← Created automatically on first run

⚠ Do NOT delete this folder after extracting.
  AbayoNet loads from this location every time it starts.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STEP 3 — LAUNCH ABAYONET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Right-click START_ABAYONET.bat → "Run as administrator"
(Run as admin gives full ICMP ping access on Windows)

A terminal window opens and your browser loads automatically:
  http://127.0.0.1:8765

Keep the terminal open while using AbayoNet.
To stop: close the terminal, or press Ctrl+C.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STEP 4 — FIRST LOGIN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Default credentials:
  Username: admin
  Password: admin123

⚠ CHANGE THIS PASSWORD immediately after first login!
  Settings → Change My Password

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  STEP 5 — ADD YOUR HOSTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Click "+ Add Host" in the top bar:
  • Enter IP address (e.g. 192.168.1.1)
  • Give it a name (e.g. "Core Router")
  • Choose a group (e.g. "Network", "Servers")
  • Set ping interval (default: 30 seconds)
  • Click "Add & Start Monitoring"

Or use 🔭 Scan to auto-discover all live hosts on a subnet.

Test IPs to try right now:
  8.8.8.8       Google DNS
  1.1.1.1       Cloudflare DNS
  192.168.1.1   Your home/office router
  127.0.0.1     Localhost

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CREATING A DESKTOP SHORTCUT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Right-click START_ABAYONET.bat
→ Send to → Desktop (create shortcut)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  FEATURES GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DASHBOARD
  • Live stats: online/offline/degraded host counts
  • Average latency across all hosts (last hour)
  • Multi-line latency chart for top 6 hosts
  • Active alerts panel
  • Full host status board with search filter

HOST STATUS INDICATORS
  🟢 Solid green   = Online, responding normally
  🔴 Pulsing red   = Offline, not responding
  ⚪ Grey          = Unknown (not yet pinged)
  🟡 Yellow border = In maintenance window

HOST DETAIL (click any host card)
  • 9 live metrics: uptime%, avg/min/max/P95/P99 latency,
    avg packet loss, avg jitter, total checks
  • Time range selector: 1H / 3H / 6H / 12H / 24H
  • Dual-axis chart: latency (ms) + packet loss (%) over time
  • Jitter bar chart
  • 24-hour uptime timeline (48 blocks, each = 30 min)
  • Built-in traceroute
  • Host-specific alert history

ALERT RULES
  Conditions: offline, online (recovery), latency >, loss >, jitter >
  Per-rule email notifications (requires SMTP settings)
  Per-rule cooldown to prevent alert spam
  Enable/disable rules without deleting them

ALERTS CENTER
  All alerts with severity (critical/warning/info)
  Acknowledge individual alerts or all at once
  Alert stats: last 24h, last 7d, critical unacknowledged

UPTIME REPORT
  Per-host uptime: 24h, 7d, 30d
  Incident count and total downtime in minutes
  Export to CSV for client reports

MAINTENANCE WINDOWS
  Schedule time windows where alerts are suppressed
  Per-host or all-hosts maintenance
  Status shows: UPCOMING / ACTIVE / ENDED

USER MANAGEMENT (Admin only)
  Create Read-Only or Admin users
  Reset passwords
  Enable/disable user accounts
  Cannot delete primary admin account

IMPORT / EXPORT
  Export hosts as JSON (for transfer to another machine)
  Export hosts as CSV (for spreadsheet viewing)
  Import JSON on another AbayoNet instance
  Imported hosts start monitoring immediately

NETWORK SCAN
  Scans an entire subnet (e.g. 192.168.1.0/24)
  Shows live hosts with latency and hostname
  One-click add any discovered host

THEMES
  Dark (default), Light, Matrix, Slate
  Persists between sessions

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  KEYBOARD SHORTCUTS (in the dashboard)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  None required — everything is click-based.
  Press Escape to close any open modal or dialog.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  EMAIL ALERTS SETUP (Gmail example)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Go to Settings → Email Alerts
2. Fill in:
     SMTP Host:  smtp.gmail.com
     SMTP Port:  587
     Username:   your-email@gmail.com
     Password:   your App Password (NOT your main password)

   To get a Gmail App Password:
   • Go to: myaccount.google.com
   • Security → 2-Step Verification → App Passwords
   • Create a password for "Mail" → copy the 16-char code
   • Paste that code as your Password in AbayoNet

3. When adding a host, enter an Alert Email address
4. Create an Alert Rule (Alert Rules page) with notify email
5. AbayoNet will email you when that rule triggers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TROUBLESHOOTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Problem: "python is not recognized"
Fix:     Reinstall Python — check "Add Python to PATH"
         Then RESTART your computer

Problem: Browser opens but shows "Cannot connect to server"
Fix:     Make sure the terminal (START_ABAYONET.bat) is still open
         If closed, re-launch START_ABAYONET.bat

Problem: All hosts show offline when they are online
Fix:     Run as Administrator:
         Right-click START_ABAYONET.bat → Run as administrator
         Windows Firewall may block ICMP ping without admin rights

Problem: Port 8765 in use
Fix:     AbayoNet tries 8765, 8766, 8767, 9000 automatically
         Check terminal window — it shows the actual port used
         Open browser to that port manually

Problem: Charts show "No data yet"
Fix:     Normal for new hosts. Data appears after the first
         ping cycles complete (within 30–60 seconds).
         If it persists, check data\abayonet.log for errors.

Problem: "database is locked" (v3 issue — fixed in v4)
Fix:     This was fixed in v4.0 with per-thread connections.
         If it still occurs, restart AbayoNet.

Problem: Forgot admin password
Fix:     1. Stop AbayoNet (close terminal)
         2. Delete data\abayonet.db
         3. Restart AbayoNet
         4. A fresh database is created with admin/admin123
         ⚠ This deletes ALL data (hosts, history, alerts)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  DATA FILES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  data\abayonet.db   SQLite database (hosts, pings, alerts)
  data\abayonet.log  Application log

  To back up: copy the entire AbayoNet folder.
  To move to another PC: copy folder + run as usual.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  TECHNICAL SPECS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Engine:       Python 3.8+  (stdlib only — no pip needed)
  Database:     SQLite with WAL mode + per-thread connections
  Protocol:     ICMP Ping + TCP port check
  Memory:       ~20–40 MB
  CPU:          <1% per 50 hosts
  Storage:      ~10 MB per host per month of history
  Auth:         SHA-256 hashed passwords, 48-byte session tokens
  Retention:    Auto-cleanup, default 30 days
  Privacy:      100% local, no cloud, no telemetry
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
