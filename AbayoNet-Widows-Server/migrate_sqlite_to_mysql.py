#!/usr/bin/env python3
"""
AbayoNet — one-time migration: old SQLite database -> new MySQL database.

Run this ONCE after setting up MySQL and abayonet.cfg, before starting
the MySQL-based abayonet.py for real use. It copies every table
(hosts, ping_results, ping_hourly, ping_daily, host_status, alerts,
alert_rules, maintenance, settings, users, sessions, report_cache,
port_results) from the old data/abayonet.db into MySQL, preserving IDs
so existing FOREIGN KEY relationships stay intact.

Usage:
    python3 migrate_sqlite_to_mysql.py [path/to/abayonet.db]

    (defaults to ./data/abayonet.db, same layout the old app used)

Safe to re-run: uses INSERT IGNORE, so already-migrated rows are
skipped rather than duplicated or erroring out.
"""
import sys, os, sqlite3, time

try:
    import pymysql
except ImportError:
    print("Missing dependency. Run:  pip install pymysql --break-system-packages")
    sys.exit(1)

# Reuse the same config file / env vars as the main app so this always
# migrates INTO whatever abayonet.py is configured to use.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import configparser

def read_db_config():
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'abayonet.cfg')
    conf = {
        'host':     os.environ.get('ABAYONET_DB_HOST', 'localhost'),
        'port':     int(os.environ.get('ABAYONET_DB_PORT', '3306')),
        'user':     os.environ.get('ABAYONET_DB_USER', 'abayonet'),
        'password': os.environ.get('ABAYONET_DB_PASSWORD', ''),
        'database': os.environ.get('ABAYONET_DB_NAME', 'abayonet'),
    }
    if os.path.exists(cfg_path):
        c = configparser.ConfigParser()
        c.read(cfg_path)
        if c.has_section('database'):
            conf['host']     = c.get('database', 'host', fallback=conf['host'])
            conf['port']     = c.getint('database', 'port', fallback=conf['port'])
            conf['user']     = c.get('database', 'user', fallback=conf['user'])
            conf['password'] = c.get('database', 'password', fallback=conf['password'])
            conf['database'] = c.get('database', 'name', fallback=conf['database'])
    return conf

# Tables in dependency order (hosts first — everything else FKs to it).
# Each entry: (table, [columns in the order to copy])
TABLES = [
    ('hosts', ['id','ip','name','group_name','tags','description','location',
               'alert_email','ping_interval','packet_count','timeout_ms',
               'port_checks','snmp_community','enabled','created_at','notes']),
    ('users', ['id','username','password','role','full_name','email',
               'created_at','last_login','active']),
    ('settings', ['key','value']),
    ('alert_rules', ['id','name','host_id','condition','threshold','duration_mins',
                      'notify_email','notify_webhook','enabled','cooldown_mins',
                      'last_triggered','trigger_count']),
    ('maintenance', ['id','host_id','name','start_time','end_time','created_at']),
    ('sessions', ['token','user_id','username','role','created_at','expires_at','ip']),
    ('host_status', ['host_id','status','latency_ms','packet_loss','jitter_ms','ttl','updated_at']),
    ('report_cache', ['host_id','cached_at','uptime_1d','uptime_7d','uptime_30d',
                       'avg_latency','min_latency','max_latency','avg_loss','avg_jitter',
                       'incidents','downtime_mins','cur_status','cur_latency','last_check']),
    ('alerts', ['id','host_id','type','message','severity','timestamp',
                'acknowledged','ack_by','ack_at']),
    ('port_results', ['id','host_id','timestamp','port','status','latency_ms']),
    ('ping_hourly', ['id','host_id','hour_ts','total','online','avg_latency',
                      'min_latency','max_latency','avg_loss','avg_jitter']),
    ('ping_daily', ['id','host_id','day_ts','total','online','avg_latency',
                     'min_latency','max_latency','avg_loss','avg_jitter']),
    # ping_results is by far the biggest table (potentially millions of
    # rows) — migrated last, in batches, with progress output.
    ('ping_results', ['id','host_id','timestamp','status','latency_ms',
                       'packet_loss','jitter_ms','ttl']),
]

RESERVED = {'key': '`key`', 'value': '`value`', 'condition': '`condition`'}
def qcol(c):
    return RESERVED.get(c, c)

BATCH = 5000

def _migrate_ping_results_resilient(sconn, mcur, mconn, cols):
    """ping_results is the table hit by the pre-existing SQLite corruption
    (freelist / b-tree damage reported by PRAGMA integrity_check on the
    source file). A plain sequential scan aborts the instant the cursor
    walks onto a damaged page — which loses every row after that point,
    not just the damaged ones.

    Instead, walk the table by id range (SELECT ... WHERE id BETWEEN a
    AND b), so a damaged page only costs the rows in that specific id
    window. On failure, halve the window and retry; a window that still
    fails at width 1 is a single unrecoverable row — skip just that id
    and continue. This maximises how much genuine ping history survives
    the corruption instead of truncating history at the first bad page.
    """
    col_list = ','.join(qcol(c) for c in cols)
    placeholders = ','.join(['%s'] * len(cols))
    insert_sql = f"INSERT IGNORE INTO ping_results({col_list}) VALUES({placeholders})"

    try:
        min_id, max_id = sconn.execute("SELECT MIN(id), MAX(id) FROM ping_results").fetchone()
    except Exception as e:
        print(f"  [skip] ping_results: cannot even read id range: {e}")
        return 0
    if min_id is None:
        print("  ping_results: 0 rows (empty)")
        return 0

    total = 0
    lost_rows = 0
    lost_ranges = []
    t0 = time.time()
    STEP = BATCH  # start with normal-size windows; shrink on failure

    lo = min_id
    while lo <= max_id:
        hi = min(lo + STEP - 1, max_id)
        try:
            rows = sconn.execute(
                f"SELECT {','.join(cols)} FROM ping_results WHERE id BETWEEN ? AND ?",
                (lo, hi)
            ).fetchall()
            mcur.executemany(insert_sql, [tuple(r) for r in rows])
            mconn.commit()
            total += len(rows)
            lo = hi + 1
            print(f"  ping_results: {total} rows migrated (up to id {hi})...", end='\r')
        except sqlite3.DatabaseError:
            if hi > lo:
                # Shrink the window and retry the SAME starting id — don't
                # advance lo, so we re-attempt this range at finer granularity.
                STEP = max(1, (hi - lo + 1) // 4)
                continue
            else:
                # Single row is unreadable — nothing more to try, skip it.
                lost_rows += 1
                lost_ranges.append(lo)
                lo += 1
                STEP = BATCH  # reset window size for the next stretch
    elapsed = time.time() - t0
    print(f"  ping_results: {total} rows migrated, {lost_rows} unrecoverable ({elapsed:.1f}s)" + " " * 10)
    if lost_rows:
        # Summarise as ranges rather than dumping every id
        ranges = []
        for rid in lost_ranges:
            if ranges and rid == ranges[-1][1] + 1:
                ranges[-1] = (ranges[-1][0], rid)
            else:
                ranges.append((rid, rid))
        preview = ', '.join(f"{a}-{b}" if a != b else str(a) for a, b in ranges[:20])
        more = '' if len(ranges) <= 20 else f' (+{len(ranges)-20} more ranges)'
        print(f"    Unrecoverable ping_results id(s) — pre-existing SQLite corruption, not this script: {preview}{more}")
    return total

def migrate(sqlite_path):
    if not os.path.exists(sqlite_path):
        print(f"SQLite file not found: {sqlite_path}")
        sys.exit(1)

    conf = read_db_config()
    print(f"Source (SQLite): {sqlite_path}")
    print(f"Target (MySQL) : {conf['user']}@{conf['host']}:{conf['port']}/{conf['database']}")
    print()

    sconn = sqlite3.connect(sqlite_path)
    sconn.row_factory = sqlite3.Row

    mconn = pymysql.connect(
        host=conf['host'], port=conf['port'], user=conf['user'],
        password=conf['password'], database=conf['database'],
        charset='utf8mb4', autocommit=False,
    )
    mcur = mconn.cursor()
    # Disable FK checks during load — some rows may reference a host_id
    # briefly out of order (harmless, we control the table order above,
    # but this makes the script robust even if that order is imperfect).
    mcur.execute("SET FOREIGN_KEY_CHECKS=0")

    grand_total = 0
    for table, cols in TABLES:
        if table == 'ping_results':
            grand_total += _migrate_ping_results_resilient(sconn, mcur, mconn, cols)
            continue
        try:
            scur = sconn.execute(f"SELECT {','.join(cols)} FROM {table}")
        except sqlite3.OperationalError as e:
            print(f"  [skip] {table}: {e}")
            continue

        col_list = ','.join(qcol(c) for c in cols)
        placeholders = ','.join(['%s'] * len(cols))
        insert_sql = f"INSERT IGNORE INTO {table}({col_list}) VALUES({placeholders})"

        batch = []
        table_total = 0
        t0 = time.time()
        while True:
            rows = scur.fetchmany(BATCH)
            if not rows:
                break
            batch = [tuple(r) for r in rows]
            mcur.executemany(insert_sql, batch)
            mconn.commit()
            table_total += len(batch)
            print(f"  {table}: {table_total} rows...", end='\r')
        elapsed = time.time() - t0
        print(f"  {table}: {table_total} rows migrated ({elapsed:.1f}s)" + " " * 10)
        grand_total += table_total

    mcur.execute("SET FOREIGN_KEY_CHECKS=1")
    mconn.commit()
    mcur.close()
    mconn.close()
    sconn.close()

    print()
    print(f"Done. {grand_total} total rows migrated.")
    print("Verify row counts against the old app before decommissioning the SQLite file.")

if __name__ == '__main__':
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'abayonet.db')
    path = sys.argv[1] if len(sys.argv) > 1 else default_path
    migrate(path)
