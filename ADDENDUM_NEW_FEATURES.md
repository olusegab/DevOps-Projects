# AbayoNet — Addendum: New Features

Add this after the base install in SETUP_LINUX.md. It covers everything
added beyond the original release: pause reasons, delete-all-hosts,
SNMP bandwidth monitoring, and traceroute.

## 1. Extra system packages required

Two features shell out to external command-line tools. Install both —
each feature will fail silently (or with an error toast) without its
tool present:

    sudo apt-get install snmp        # required for SNMP bandwidth monitoring
    sudo apt-get install traceroute  # required for the Traceroute button

Nothing else changes — no new Python packages, `requirements.txt` is
unchanged (PyMySQL only).

## 2. Database changes

No manual SQL needed. All new tables/columns are created automatically
the first time the app starts, whether this is a fresh install or an
upgrade of an existing database:
  - `hosts` gains: `pause_reason`, `paused_at`, `paused_by`,
    `snmp_enabled`, `snmp_port`
  - two new tables: `interfaces`, `bandwidth_results`

## 3. Pausing a host now requires a reason

Admins pausing a host (from the host card or detail view) are prompted
for a short comment before it takes effect. Resuming does not require
one. The reason, who paused it, and when are shown on the paused badge
(hover) and in the host detail view.

## 4. Delete All Hosts (admin)

On the "All Hosts" page toolbar, admins have a red "Delete All Hosts"
button (type "DELETE ALL" to confirm). This is permanent — it cascades
to all ping/alert history for every host. Use it before a clean
re-import if host names/IPs need a full redo.

## 5. SNMP Bandwidth Monitoring (optional, per host)

To enable on a host: Edit Host → check "Enable SNMP Bandwidth
Monitoring" → enter the device's SNMP community string (default
`public`) and port (default `161`) → Save.

  - Interfaces are auto-discovered in the background right after
    saving, and re-discovered every 10 minutes.
  - A "📶 Bandwidth (SNMP)" card appears on that host's detail page
    with a per-interface chart (download/upload) and the same
    1H–90D range buttons used elsewhere.
  - Needs two poll cycles (~60–120s apart) before a rate can display
    — expect "No bandwidth data yet" briefly after first enabling.
  - Use "⚙ Manage Interfaces" to untick any interface you don't want
    polled or shown (e.g. unused switch ports) — this sticks across
    rediscoveries.
  - Polling runs every 60s globally for all SNMP-enabled hosts; not
    yet configurable per-host.

## 6. Traceroute

Already existed as a feature — just needed the system package above.
No configuration; click "Traceroute" on any host's detail page.
