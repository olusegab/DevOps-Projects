#!/usr/bin/env python3
"""
AbayoNet Enterprise Network Monitor v4.0
Fixes: Database lock (per-thread connection pool)
New:   Login page, Admin/ReadOnly users, User management, Host import/export
"""
import os, sys, threading, time, json, sqlite3, subprocess, platform, queue
import socket, re, smtplib, logging, csv, io, ipaddress, hashlib, secrets
import webbrowser
from datetime import datetime, timedelta
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

os.makedirs('data', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('data/abayonet.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger('AbayoNet')
DB_PATH = 'data/abayonet.db'
VERSION = '5.2.0-port8780'

# ═══════════════════════════════════════════════════════════════
# DATABASE LOCK FIX
# Root cause: each monitoring thread called sqlite3.connect() and
# never closed it. With dozens of threads all holding connections,
# SQLite WAL mode still locks on write contention.
#
# Fix: threading.local() gives each thread ONE persistent connection.
#      busy_timeout=30000 tells SQLite to wait 30s before giving up.
#      All writes go through db_execute() which retries on lock.
# ═══════════════════════════════════════════════════════════════
_tls = threading.local()

def get_db():
    if not getattr(_tls, 'conn', None):
        c = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=NORMAL')
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=60000')
        c.execute('PRAGMA cache_size=-8000')
        _tls.conn = c
    return _tls.conn

def close_thread_db():
    c = getattr(_tls, 'conn', None)
    if c:
        try: c.close()
        except: pass
        _tls.conn = None

def db_exec(sql, params=()):
    for attempt in range(8):
        try:
            conn = get_db()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() or 'busy' in str(e).lower():
                if attempt < 7:
                    wait = min(0.5 * (2 ** attempt), 10)  # exponential backoff, capped at 10s
                    log.warning(f'DB lock retry {attempt+1}/8 (waiting {wait:.1f}s): {e}')
                    time.sleep(wait)
                else:
                    log.error(f'DB write FAILED after 8 retries: {sql[:80]}')
                    raise
            else:
                raise

def db_one(sql, params=()):
    try:
        return get_db().execute(sql, params).fetchone()
    except sqlite3.OperationalError as e:
        if 'locked' in str(e).lower():
            time.sleep(0.5)
            return get_db().execute(sql, params).fetchone()
        raise

def db_all(sql, params=()):
    try:
        return get_db().execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        if 'locked' in str(e).lower():
            time.sleep(0.5)
            return get_db().execute(sql, params).fetchall()
        raise

# ── TIMESTAMP HELPERS ────────────────────────────────────────────
# IMPORTANT: SQLite's `datetime('now','localtime')` (used as the column DEFAULT for
# ping_results/alerts/port_results.timestamp) produces strings like
# '2026-06-21 13:55:40' — a SPACE between date and time.
# Python's datetime.isoformat() produces '2026-06-21T13:55:40.123456' — a
# 'T' separator (plus microseconds). When these two formats are compared
# as TEXT in SQL (e.g. "WHERE timestamp > ?"), SQLite does a plain
# lexicographic string comparison. Since ' ' (0x20) sorts before 'T'
# (0x54), any same-calendar-day comparison silently evaluates wrong
# (real, recent rows look "older" than the cutoff), while comparisons
# that cross a date boundary happen to still work because the YYYY-MM-DD
# prefix alone already differs. This is why narrow ranges like 1H/3H/6H/
# 12H came back empty while 24H+ worked. Always use these helpers (not
# .isoformat()) when building a `since`/`cutoff` value that gets compared
# against a column populated by SQLite's `datetime('now','localtime')` default.
def utc_now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def utc_since_str(hours=0, days=0):
    return (datetime.now() - timedelta(hours=hours, days=days)).strftime('%Y-%m-%d %H:%M:%S')

def cfg(key, default=''):
    try:
        r = db_one('SELECT value FROM settings WHERE key=?', (key,))
        return r['value'] if r else default
    except:
        return default

# ── DATABASE INIT ────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    c = conn.cursor()
    # Performance PRAGMAs — set before schema creation
    for pragma in [
        'PRAGMA journal_mode=WAL',
        'PRAGMA synchronous=NORMAL',
        'PRAGMA cache_size=-32000',      # 32MB page cache
        'PRAGMA temp_store=MEMORY',
        'PRAGMA mmap_size=536870912',    # 512MB memory-mapped I/O
        'PRAGMA wal_autocheckpoint=1000',
        'PRAGMA auto_vacuum=INCREMENTAL',
    ]:
        conn.execute(pragma)

    c.executescript('''
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS hosts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ip              TEXT UNIQUE NOT NULL,
            name            TEXT DEFAULT '',
            group_name      TEXT DEFAULT 'Default',
            tags            TEXT DEFAULT '',
            description     TEXT DEFAULT '',
            location        TEXT DEFAULT '',
            alert_email     TEXT DEFAULT '',
            ping_interval   INTEGER DEFAULT 30,
            packet_count    INTEGER DEFAULT 4,
            timeout_ms      INTEGER DEFAULT 1000,
            port_checks     TEXT DEFAULT '',
            snmp_community  TEXT DEFAULT 'public',
            enabled         INTEGER DEFAULT 1,
            created_at      TEXT DEFAULT (datetime('now', 'localtime')),
            notes           TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ping_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id     INTEGER NOT NULL,
            timestamp   TEXT DEFAULT (datetime('now', 'localtime')),
            status      TEXT NOT NULL,
            latency_ms  REAL,
            packet_loss REAL,
            jitter_ms   REAL,
            ttl         INTEGER,
            FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ping_host_ts  ON ping_results(host_id, timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_ping_ts       ON ping_results(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_ping_status   ON ping_results(host_id, status, timestamp DESC);

        -- Hourly rollup table: pre-aggregated stats per host per hour
        -- Keeps raw pings queryable for 30 days, rollup covers the rest (up to 6 months)
        CREATE TABLE IF NOT EXISTS ping_hourly (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id     INTEGER NOT NULL,
            hour_ts     TEXT NOT NULL,          -- '2026-01-15 14:00:00'
            total       INTEGER DEFAULT 0,
            online      INTEGER DEFAULT 0,
            avg_latency REAL,
            min_latency REAL,
            max_latency REAL,
            avg_loss    REAL,
            avg_jitter  REAL,
            UNIQUE(host_id, hour_ts),
            FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_hourly_host_ts ON ping_hourly(host_id, hour_ts DESC);

        -- Daily rollup table: pre-aggregated stats per host per day
        CREATE TABLE IF NOT EXISTS ping_daily (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id     INTEGER NOT NULL,
            day_ts      TEXT NOT NULL,          -- '2026-01-15'
            total       INTEGER DEFAULT 0,
            online      INTEGER DEFAULT 0,
            avg_latency REAL,
            min_latency REAL,
            max_latency REAL,
            avg_loss    REAL,
            avg_jitter  REAL,
            UNIQUE(host_id, day_ts),
            FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_daily_host_ts  ON ping_daily(host_id, day_ts DESC);

        -- Fast current-status table: one row per host, updated on every ping.
        -- Eliminates the need to query ping_results for current status anywhere.
        CREATE TABLE IF NOT EXISTS host_status (
            host_id     INTEGER PRIMARY KEY,
            status      TEXT    NOT NULL DEFAULT 'unknown',
            latency_ms  REAL,
            packet_loss REAL,
            jitter_ms   REAL,
            ttl         INTEGER,
            updated_at  TEXT    NOT NULL DEFAULT '',
            FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
        );

        -- Cover index so uptime queries never touch the main table body
        -- (host_id, timestamp, status) is all the uptime calc needs
        CREATE INDEX IF NOT EXISTS idx_ping_cover
            ON ping_results(host_id, timestamp DESC, status, latency_ms, packet_loss, jitter_ms);

        -- Report cache: pre-computed per-host stats, refreshed every 5 minutes
        CREATE TABLE IF NOT EXISTS report_cache (
            host_id     INTEGER PRIMARY KEY,
            cached_at   TEXT NOT NULL,
            uptime_1d   REAL DEFAULT 0,
            uptime_7d   REAL DEFAULT 0,
            uptime_30d  REAL DEFAULT 0,
            avg_latency REAL,
            min_latency REAL,
            max_latency REAL,
            avg_loss    REAL,
            avg_jitter  REAL,
            incidents   INTEGER DEFAULT 0,
            downtime_mins REAL DEFAULT 0,
            cur_status  TEXT DEFAULT 'unknown',
            cur_latency REAL,
            last_check  TEXT,
            FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS port_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id     INTEGER NOT NULL,
            timestamp   TEXT DEFAULT (datetime('now', 'localtime')),
            port        INTEGER NOT NULL,
            status      TEXT NOT NULL,
            latency_ms  REAL,
            FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id         INTEGER NOT NULL,
            type            TEXT NOT NULL,
            message         TEXT NOT NULL,
            severity        TEXT DEFAULT 'warning',
            timestamp       TEXT DEFAULT (datetime('now', 'localtime')),
            acknowledged    INTEGER DEFAULT 0,
            ack_by          TEXT DEFAULT '',
            ack_at          TEXT DEFAULT '',
            FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(timestamp DESC);

        CREATE TABLE IF NOT EXISTS alert_rules (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            host_id         INTEGER DEFAULT 0,
            condition       TEXT NOT NULL,
            threshold       REAL DEFAULT 0,
            duration_mins   INTEGER DEFAULT 0,
            notify_email    TEXT DEFAULT '',
            notify_webhook  TEXT DEFAULT '',
            enabled         INTEGER DEFAULT 1,
            cooldown_mins   INTEGER DEFAULT 5,
            last_triggered  TEXT,
            trigger_count   INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS maintenance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id     INTEGER,
            name        TEXT NOT NULL,
            start_time  TEXT NOT NULL,
            end_time    TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            role        TEXT DEFAULT 'readonly',
            full_name   TEXT DEFAULT '',
            email       TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            last_login  TEXT DEFAULT '',
            active      INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            username    TEXT NOT NULL,
            role        TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now', 'localtime')),
            expires_at  TEXT NOT NULL,
            ip          TEXT DEFAULT ''
        );
    ''')

    defaults = [
        ('smtp_host',''),('smtp_port','587'),('smtp_user',''),('smtp_pass',''),
        ('smtp_from',''),('smtp_tls','1'),('alert_cooldown','300'),
        ('data_retention_days','30'),('theme','dark'),('refresh_interval','10'),
        ('webhook_url',''),('company_name','AbayoNet Enterprise'),
    ]
    for k,v in defaults:
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))

    c.execute('SELECT COUNT(*) FROM alert_rules')
    if c.fetchone()[0] == 0:
        rules = [
            ('Host Offline',0,'offline',0,0,'','',1,5),
            ('High Latency >200ms',0,'latency_gt',200,0,'','',1,5),
            ('Packet Loss >10%',0,'loss_gt',10,0,'','',1,5),
        ]
        for r in rules:
            c.execute('INSERT INTO alert_rules(name,host_id,condition,threshold,duration_mins,notify_email,notify_webhook,enabled,cooldown_mins) VALUES(?,?,?,?,?,?,?,?,?)',r)

    c.execute('SELECT COUNT(*) FROM users')
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO users(username,password,role,full_name,email) VALUES('admin',?,'admin','Administrator','admin@abayonet.local')",(hashpw('admin123'),))
        log.info('='*55)
        log.info('DEFAULT ADMIN CREATED')
        log.info('  Username: admin')
        log.info('  Password: admin123')
        log.info('  CHANGE THIS PASSWORD after first login!')
        log.info('='*55)

    c.execute('SELECT COUNT(*) FROM hosts')
    if c.fetchone()[0] == 0:
        sample = [
            ('8.8.8.8','Google DNS','External DNS','dns,google','Primary Google DNS'),
            ('1.1.1.1','Cloudflare DNS','External DNS','dns,cloudflare','Cloudflare primary'),
            ('8.8.4.4','Google DNS 2','External DNS','dns,google','Secondary Google DNS'),
        ]
        for s in sample:
            c.execute('INSERT OR IGNORE INTO hosts(ip,name,group_name,tags,description) VALUES(?,?,?,?,?)',s)

    conn.commit()
    conn.close()
    log.info(f'AbayoNet v{VERSION} database ready')

# ── AUTH ─────────────────────────────────────────────────────────
def hashpw(p):
    return hashlib.sha256(('AbayoNet_salt_v4_'+p).encode()).hexdigest()

def make_session(uid, uname, role, ip=''):
    token = secrets.token_urlsafe(48)
    exp = (datetime.now()+timedelta(days=30)).isoformat()
    db_exec('INSERT INTO sessions(token,user_id,username,role,expires_at,ip) VALUES(?,?,?,?,?,?)',(token,uid,uname,role,exp,ip))
    db_exec('UPDATE users SET last_login=? WHERE id=?',(datetime.now().isoformat(),uid))
    return token

def renew_session(token):
    """Slide the expiry window forward on each heartbeat — keeps active sessions alive indefinitely."""
    exp = (datetime.now()+timedelta(days=30)).isoformat()
    db_exec('UPDATE sessions SET expires_at=? WHERE token=?',(exp,token))

def check_session(token):
    if not token: return None
    try:
        r = db_one('SELECT username,role,expires_at FROM sessions WHERE token=?',(token,))
        if not r: return None
        if datetime.fromisoformat(r["expires_at"]) < datetime.now():
            db_exec('DELETE FROM sessions WHERE token=?',(token,))
            return None
        return {'username':r['username'],'role':r['role']}
    except:
        return None

def get_token(handler):
    for part in handler.headers.get('Cookie','').split(';'):
        p = part.strip()
        if p.startswith('abn_token='):
            return p.split('=',1)[1].strip()
    a = handler.headers.get('Authorization','')
    if a.startswith('Bearer '): return a[7:].strip()
    return None

def auth(handler, admin=False):
    sess = check_session(get_token(handler))
    if not sess:
        handler.json({'error':'Unauthorized','login_required':True},401)
        return None
    if admin and sess['role']!='admin':
        handler.json({'error':'Admin access required'},403)
        return None
    return sess

# ── PING ENGINE ──────────────────────────────────────────────────
def ping(ip, count=2, timeout_ms=800):
    """
    Send ICMP ping. Defaults reduced to 2 packets × 800ms = max ~2s per call
    (was 4 packets × 1000ms = up to ~12s). Monitor threads pass their own
    count/timeout from host settings, but Ping Now always gets count=2.
    """
    sname = platform.system().lower()
    ts = max(1, timeout_ms // 1000)
    try:
        if sname == 'windows':
            cmd = ['ping', '-n', str(count), '-w', str(timeout_ms), ip]
        else:
            cmd = ['ping', '-c', str(count), '-W', str(ts), ip]
        # Timeout = per-packet-timeout × count + 4s headroom (was +8s)
        hard_timeout = (timeout_ms / 1000) * count + 4
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=hard_timeout)
        return parse_ping(r.stdout + r.stderr, sname, count)
    except subprocess.TimeoutExpired:
        return offline()
    except Exception:
        return offline()

def parse_ping(out, sname, count):
    lats = []
    ttl = None
    loss = 100.0
    if sname == 'windows':
        for m in re.finditer(r'time[=<](\d+)ms',out,re.I): lats.append(float(m.group(1)))
        m=re.search(r'TTL=(\d+)',out,re.I); ttl=int(m.group(1)) if m else None
        m=re.search(r'\((\d+)%\s*loss\)',out,re.I); loss=float(m.group(1)) if m else 100.0
    else:
        for m in re.finditer(r'time=(\d+\.?\d*)\s*ms',out): lats.append(float(m.group(1)))
        m=re.search(r'ttl=(\d+)',out,re.I); ttl=int(m.group(1)) if m else None
        m=re.search(r'(\d+)%\s*packet loss',out); loss=float(m.group(1)) if m else 100.0
    if not lats: return offline()
    avg = sum(lats)/len(lats)
    loss = max(0.0,(count-len(lats))/count*100)
    jitter = sum(abs(l-avg) for l in lats)/len(lats) if len(lats)>1 else 0.0
    return {'status':'online' if loss<100 else 'offline',
            'latency':round(avg,2),'loss':round(loss,1),
            'jitter':round(jitter,2),'ttl':ttl,
            'min_ms':round(min(lats),2),'max_ms':round(max(lats),2)}

def offline():
    return {'status':'offline','latency':None,'loss':100.0,'jitter':None,'ttl':None,'min_ms':None,'max_ms':None}

def check_port(ip, port, timeout=2):
    try:
        t0=time.time()
        with socket.create_connection((ip,port),timeout=timeout):
            return {'port':port,'status':'open','latency_ms':round((time.time()-t0)*1000,2)}
    except:
        return {'port':port,'status':'closed','latency_ms':None}

def resolve(ip):
    try: return socket.gethostbyaddr(ip)[0]
    except: return ''

# ── ALERT ENGINE ─────────────────────────────────────────────────
# _astate: {(host_id, rule_id): datetime of last fire}  — in-memory fast check
# _hstate: {host_id: last known status} — for edge-triggered recovery alerts
_astate = {}
_hstate = {}
_email_queue = None   # initialised in main()

def _prune_astate():
    """Keep _astate from growing forever — remove entries older than 24h."""
    cutoff = datetime.now() - timedelta(hours=24)
    stale = [k for k,v in _astate.items() if v < cutoff]
    for k in stale:
        del _astate[k]

def fire_alerts(host_id, hname, ip, result):
    try:
        rules = db_all(
            'SELECT * FROM alert_rules WHERE (host_id=? OR host_id=0) AND enabled=1',
            (host_id,))
        now    = datetime.now()
        status = result['status']
        prev   = _hstate.get(host_id)
        _hstate[host_id] = status   # update remembered state

        for rule in rules:
            rule = dict(rule)
            rid  = rule['id']
            cond = rule['condition']
            thresh   = rule['threshold']
            cooldown = rule['cooldown_mins'] * 60

            triggered = False; msg = ''; sev = 'warning'

            if cond == 'offline' and status == 'offline':
                triggered = True; sev = 'critical'
                msg = f'🔴 {hname} ({ip}) is OFFLINE'

            elif cond == 'online' and status == 'online' and prev == 'offline':
                # Edge-triggered: only fire ONCE on recovery, not every ping
                triggered = True; sev = 'info'
                msg = f'🟢 {hname} ({ip}) is back ONLINE'

            elif cond == 'latency_gt' and result.get('latency') and result['latency'] > thresh:
                triggered = True
                msg = f'⚡ High latency on {hname} ({ip}): {result["latency"]:.1f}ms > {thresh}ms'

            elif cond == 'loss_gt' and result['loss'] > thresh:
                triggered = True
                msg = f'📦 Packet loss on {hname} ({ip}): {result["loss"]:.1f}% > {thresh}%'

            elif cond == 'jitter_gt' and result.get('jitter') and result['jitter'] > thresh:
                triggered = True
                msg = f'〰 Jitter on {hname} ({ip}): {result["jitter"]:.1f}ms > {thresh}ms'

            if not triggered:
                continue

            # Cooldown check — in-memory first (fast), then also persist to DB
            key  = (host_id, rid)
            last = _astate.get(key)

            # Also check DB last_triggered for crash-restart cooldown persistence
            if not last:
                db_last = rule.get('last_triggered')
                if db_last:
                    try:
                        last = datetime.fromisoformat(db_last)
                        _astate[key] = last   # warm the cache
                    except Exception:
                        pass

            if last and (now - last).total_seconds() < cooldown:
                continue   # still within cooldown — suppress duplicate alert

            _astate[key] = now

            db_exec(
                'INSERT INTO alerts(host_id,type,message,severity,timestamp) VALUES(?,?,?,?,?)',
                (host_id, cond, msg, sev, now.strftime('%Y-%m-%d %H:%M:%S')))
            db_exec(
                'UPDATE alert_rules SET last_triggered=?,trigger_count=trigger_count+1 WHERE id=?',
                (now.isoformat(), rid))
            log.warning(f'ALERT [{sev}]: {msg}')

            em = rule.get('notify_email', '')
            if em and _email_queue:
                try:
                    _email_queue.put_nowait((em, sev, hname, msg))
                except Exception:
                    pass   # queue full — skip this email rather than crash

        # Prune stale _astate entries periodically (roughly every 200 calls)
        if len(_astate) > 500:
            _prune_astate()

    except Exception as e:
        log.error(f'Alert error host={host_id}: {e}')

def _send_email(to, sev, host, msg):
    try:
        h=cfg('smtp_host'); port=int(cfg('smtp_port','587'))
        u=cfg('smtp_user'); p=cfg('smtp_pass'); frm=cfg('smtp_from') or u
        if not h or not u: return
        mm=MIMEMultipart(); mm['From']=frm; mm['To']=to
        mm['Subject']=f'[AbayoNet] {sev.upper()}: {host}'
        mm.attach(MIMEText(msg,'plain'))
        s=smtplib.SMTP(h,port,timeout=10)
        if cfg('smtp_tls','1')=='1': s.starttls()
        s.login(u,p); s.send_message(mm); s.quit()
        log.info(f'Email sent to {to}: {host}')
    except Exception as e:
        log.error(f'Email error: {e}')

def _email_worker(q):
    """Single daemon thread drains the email queue — no unbounded thread creation."""
    while True:
        try:
            item = q.get(timeout=5)
            if item is None:
                break
            _send_email(*item)
        except Exception:
            pass  # queue.Empty timeout or send error — keep running

def in_maintenance(host_id):
    now=datetime.now().isoformat()
    try:
        r=db_one('SELECT id FROM maintenance WHERE (host_id=? OR host_id IS NULL) AND start_time<=? AND end_time>=?',(host_id,now,now))
        return r is not None
    except: return False

# ── MONITOR LOOPS ────────────────────────────────────────────────
_running = True
_hthreads = {}

def monitor_host(host_id, ip, name, interval, pcount, timeout_ms, ports_str):
    log.info(f'Monitor started: {name} ({ip}) every {interval}s')
    consecutive_errors = 0
    while _running:
        try:
            result = ping(ip, pcount, timeout_ms)
            _ts = utc_now_str()
            db_exec(
                'INSERT INTO ping_results(host_id,timestamp,status,latency_ms,packet_loss,jitter_ms,ttl) '
                'VALUES(?,?,?,?,?,?,?)',
                (host_id, _ts, result['status'], result.get('latency'),
                 result['loss'], result.get('jitter'), result.get('ttl')))
            # O(1) current-status — no more MAX(id) or ORDER BY DESC queries
            db_exec(
                'INSERT OR REPLACE INTO host_status'
                '(host_id,status,latency_ms,packet_loss,jitter_ms,ttl,updated_at) '
                'VALUES(?,?,?,?,?,?,?)',
                (host_id, result['status'], result.get('latency'),
                 result['loss'], result.get('jitter'), result.get('ttl'), _ts))
            if not in_maintenance(host_id):
                fire_alerts(host_id, name, ip, result)
            if ports_str:
                for port in [int(p.strip()) for p in ports_str.split(',') if p.strip().isdigit()]:
                    pr = check_port(ip, port)
                    db_exec(
                        'INSERT INTO port_results(host_id,timestamp,port,status,latency_ms) VALUES(?,?,?,?,?)',
                        (host_id, utc_now_str(), port, pr['status'], pr.get('latency_ms')))
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            log.error(f'Monitor error {ip} (#{consecutive_errors}): {e}')
            if consecutive_errors >= 5:
                time.sleep(min(interval * consecutive_errors, 300))
        time.sleep(interval)
    log.info(f'Monitor stopped: {name} ({ip})')
    close_thread_db()

def start_monitor(h):
    hid = h['id']
    existing = _hthreads.get(hid)
    if existing and existing.is_alive():
        log.warning(f'Monitor already running for host {hid} ({h["ip"]}) — skipping duplicate')
        return
    t = threading.Thread(
        target=monitor_host,
        args=(hid, h['ip'], h['name'] or h['ip'], h['ping_interval'],
              h['packet_count'], h.get('timeout_ms', 1000), h.get('port_checks', '')),
        daemon=True, name=f'mon-{h["ip"]}'
    )
    t.start()
    _hthreads[hid] = t

def start_all():
    hosts = db_all('SELECT * FROM hosts WHERE enabled=1')
    for h in hosts: start_monitor(dict(h))
    log.info(f'Monitoring {len(hosts)} hosts')
    # Warm report cache immediately in background — so first page load is instant
    # even if the 5-minute refresh cycle hasn't fired yet
    def _warm():
        global _report_cache, _report_cache_ts
        result = _build_report_cache()
        with _report_cache_lock:
            if result:
                _report_cache    = result
                _report_cache_ts = datetime.now()
        log.info(f'Report cache warmed: {len(result)} hosts ready')
    threading.Thread(target=_warm, daemon=True, name='cache-warmup').start()
    # Background 5-minute refresh cycle
    threading.Thread(target=_refresh_report_cache_bg,
                     daemon=True, name='report-cache').start()
    # Watchdog — restarts dead/stalled monitor threads every 60s
    threading.Thread(target=_monitor_watchdog, daemon=True, name='watchdog').start()
    log.info('Cache warmup, report-cache refresh, and watchdog started')

def _monitor_watchdog():
    """
    Safety net: every 2 minutes, check each host's last successful ping.
    If a host hasn't reported in 3x its expected interval (or its monitor
    thread has died), restart that host's monitor thread. This prevents
    a single stalled thread (e.g. from a long DB lock) from silently
    killing monitoring for that host forever.
    """
    while _running:
        time.sleep(60)
        try:
            hosts = db_all('SELECT * FROM hosts WHERE enabled=1')
            for h in hosts:
                h = dict(h)
                hid = h['id']
                t = _hthreads.get(hid)
                thread_dead = (t is None) or (not t.is_alive())

                last = db_one(
                    'SELECT timestamp FROM ping_results WHERE host_id=? '
                    'ORDER BY id DESC LIMIT 1', (hid,))
                stalled = False
                if last and last['timestamp']:
                    try:
                        last_ts = datetime.fromisoformat(last['timestamp'])
                        gap_secs = (datetime.now() - last_ts).total_seconds()
                        expected = max(h['ping_interval'] * 3, 90)
                        stalled = gap_secs > expected
                    except Exception:
                        pass

                if thread_dead or stalled:
                    reason = 'thread dead' if thread_dead else f'stalled ({int(gap_secs)}s since last ping)'
                    log.warning(f'Watchdog: restarting monitor for {h["name"]} ({h["ip"]}) — {reason}')
                    _hthreads.pop(hid, None)  # clear stale entry so start_monitor doesn't skip it
                    start_monitor(h)
        except Exception as e:
            log.error(f'Watchdog error: {e}')
        finally:
            close_thread_db()

def rollup_pings():
    """
    Tiered data retention — permanent solution to data growth:
    - Raw pings:     last 7 days   (full resolution for live graphs)
    - Hourly rollup: 7 - 30 days   (1 row/hour/host for weekly analysis)
    - Daily rollup:  30 - 180 days (1 row/day/host for monthly/6-month reports)

    With 87 hosts at 30s interval:
    OLD (30-day raw): 160K rows/day × 30 = 4.8M rows = ~580MB
    NEW (7-day raw):  160K rows/day × 7  = 1.1M rows + 87×24×23 hourly = tiny
    """
    try:
        cutoff_raw   = utc_since_str(days=7)    # raw pings older than 7 days → roll up
        cutoff_hour  = utc_since_str(days=30)   # hourly rows older than 30 days → roll to daily
        cutoff_keep  = utc_since_str(days=180)  # delete anything older than 180 days

        # Get hosts that have old raw data to process
        host_ids = [r['host_id'] for r in db_all(
            'SELECT DISTINCT host_id FROM ping_results WHERE timestamp<? AND timestamp>=?',
            (cutoff_raw, cutoff_keep))]

        total_archived = 0
        for hid in host_ids:
            try:
                db = get_db()
                # Raw → Hourly (7 to 30 days old)
                db.execute("""
                    INSERT OR IGNORE INTO ping_hourly
                        (host_id,hour_ts,total,online,avg_latency,min_latency,max_latency,avg_loss,avg_jitter)
                    SELECT host_id,
                        strftime('%Y-%m-%d %H:00:00',timestamp) AS hour_ts,
                        COUNT(*),
                        SUM(CASE WHEN status='online' THEN 1 ELSE 0 END),
                        AVG(latency_ms),MIN(latency_ms),MAX(latency_ms),
                        AVG(packet_loss),AVG(jitter_ms)
                    FROM ping_results
                    WHERE host_id=? AND timestamp<? AND timestamp>=?
                    GROUP BY host_id,hour_ts""", (hid, cutoff_raw, cutoff_keep))

                # Hourly → Daily (>30 days old)
                db.execute("""
                    INSERT OR IGNORE INTO ping_daily
                        (host_id,day_ts,total,online,avg_latency,min_latency,max_latency,avg_loss,avg_jitter)
                    SELECT host_id,
                        strftime('%Y-%m-%d',hour_ts) AS day_ts,
                        SUM(total),SUM(online),
                        AVG(avg_latency),MIN(min_latency),MAX(max_latency),
                        AVG(avg_loss),AVG(avg_jitter)
                    FROM ping_hourly
                    WHERE host_id=? AND hour_ts<? AND hour_ts>=?
                    GROUP BY host_id,day_ts""", (hid, cutoff_hour, cutoff_keep))

                db.commit()

                # Delete old raw pings for this host
                r = db.execute(
                    'DELETE FROM ping_results WHERE host_id=? AND timestamp<? AND timestamp>=?',
                    (hid, cutoff_raw, cutoff_keep))
                db.commit()
                total_archived += r.rowcount

                time.sleep(0.02)   # brief yield — lets monitor threads get a turn

            except Exception as e:
                log.error(f'Rollup error host {hid}: {e}')
                continue

        # Purge old hourly rows (>30 days) and old daily rows (>180 days)
        db = get_db()
        db.execute('DELETE FROM ping_hourly WHERE hour_ts<?', (cutoff_hour,))
        db.execute('DELETE FROM ping_daily  WHERE day_ts<?',  (cutoff_keep,))
        db.execute('DELETE FROM port_results WHERE timestamp<?', (cutoff_raw,))
        db.commit()

        if total_archived:
            log.info(f'Rollup: {total_archived} raw pings → hourly summaries '
                     f'across {len(host_ids)} hosts (7d raw / 30d hourly / 180d daily)')

    except Exception as e:
        log.error(f'Rollup error: {e}')
    finally:
        close_thread_db()

def run_cleanup(forced=False):
    """Rollup + purge + compact DB. Runs hourly. Each step is independently
    fault-tolerant so one slow/failed step never blocks the others or crashes the loop."""
    try:
        rollup_pings()
    except Exception as e:
        log.error(f'Cleanup: rollup step failed: {e}')

    try:
        cutoff6m = utc_since_str(days=180)
        r3 = db_exec(
            'DELETE FROM alerts WHERE timestamp<? AND acknowledged=1', (cutoff6m,)).rowcount
        db_exec('DELETE FROM sessions WHERE expires_at<?', (datetime.now().isoformat(),))
        if forced or r3:
            log.info(f'Cleanup: {r3} old alerts purged.')
    except Exception as e:
        log.error(f'Cleanup: purge step failed: {e}')

    try:
        # Small vacuum batch — won't hold the lock long even on a big DB
        db_exec('PRAGMA incremental_vacuum(200)')
    except Exception as e:
        log.error(f'Cleanup: vacuum step failed: {e}')
    finally:
        close_thread_db()

def cleanup_loop():
    # Run first cleanup in background so server startup isn't delayed by a big rollup
    threading.Thread(target=run_cleanup, kwargs={'forced': True}, daemon=True, name='cleanup-initial').start()
    _hour = 0
    while True:
        time.sleep(3600)
        _hour += 1
        # Each hourly cleanup runs in its own thread — if one run takes long,
        # it doesn't delay the next scheduling tick or block monitor threads
        threading.Thread(target=run_cleanup, daemon=True, name=f'cleanup-{_hour}').start()
        if _hour % 24 == 0:
            def _vacuum_batch():
                try:
                    for _ in range(10):  # 10 small batches instead of one big unbounded vacuum
                        db_exec('PRAGMA incremental_vacuum(500)')
                        time.sleep(0.2)
                    log.info('24h vacuum batch complete')
                except Exception as e:
                    log.error(f'Vacuum error: {e}')
                finally:
                    close_thread_db()
            threading.Thread(target=_vacuum_batch, daemon=True, name='vacuum-24h').start()

# ── STATS ────────────────────────────────────────────────────────
def get_stats(host_id, hours):
    since=utc_since_str(hours=hours)
    r=db_one('SELECT COUNT(*) t,SUM(CASE WHEN status="online" THEN 1 ELSE 0 END) u,AVG(latency_ms) al,MIN(latency_ms) mn,MAX(latency_ms) mx,AVG(packet_loss) ap,AVG(jitter_ms) aj FROM ping_results WHERE host_id=? AND timestamp>?',(host_id,since))
    r=dict(r); total=r['t'] or 0; online=r['u'] or 0
    uptime=round(online/total*100,3) if total else 0.0
    lats=[row[0] for row in db_all('SELECT latency_ms FROM ping_results WHERE host_id=? AND status="online" AND timestamp>? AND latency_ms IS NOT NULL ORDER BY latency_ms',(host_id,since))]
    p95=lats[int(len(lats)*0.95)] if lats else None
    p99=lats[int(len(lats)*0.99)] if lats else None
    return {'total_checks':total,'online_count':online,'uptime_pct':uptime,
            'avg_latency':round(r['al'],2) if r['al'] else None,
            'min_latency':round(r['mn'],2) if r['mn'] else None,
            'max_latency':round(r['mx'],2) if r['mx'] else None,
            'avg_loss':round(r['ap'],2) if r['ap'] else None,
            'avg_jitter':round(r['aj'],2) if r['aj'] else None,
            'p95_latency':round(p95,2) if p95 else None,
            'p99_latency':round(p99,2) if p99 else None}

# ── REPORT CACHE ─────────────────────────────────────────────────
# Cache is rebuilt in a background thread every 5 minutes.
# API calls return instantly from cache — no live DB scan on page load.
_report_cache      = []          # list of dicts, one per host
_report_cache_ts   = None        # datetime of last successful build
_report_cache_lock = threading.Lock()
_CACHE_TTL_SECS    = 300         # rebuild every 5 minutes

def _build_report_cache():
    """
    Full report computation — runs in background thread every 5 minutes.
    Performance design:
    - Uses ONE mega-query across ALL hosts (not per-host loops)
    - 1d/7d uptime from raw ping_results (7-day retention window)
    - 30d uptime from ping_daily rollup (no raw scan needed)
    - Current status from host_status table (O(1), always fresh)
    - All writes batched into ONE transaction (87 hosts = 1 commit, not 87)
    """
    try:
        hosts = db_all('SELECT * FROM hosts ORDER BY group_name, name')
        if not hosts:
            return []

        since_1d = utc_since_str(days=1)
        since_7d = utc_since_str(days=7)

        # Mega-query on raw ping_results — only 7 days of data max now
        rows = db_all("""
            SELECT
                host_id,
                COUNT(*)                                                      AS total,
                SUM(CASE WHEN status="online" THEN 1 ELSE 0 END)             AS online_all,
                SUM(CASE WHEN status="online" AND timestamp>? THEN 1 ELSE 0 END) AS online_1d,
                SUM(CASE WHEN timestamp>? THEN 1 ELSE 0 END)                 AS total_1d,
                SUM(CASE WHEN status="offline" THEN 1 ELSE 0 END)            AS offline_cnt,
                AVG(CASE WHEN status="online" THEN latency_ms END)           AS avg_lat,
                MIN(CASE WHEN status="online" THEN latency_ms END)           AS min_lat,
                MAX(CASE WHEN status="online" THEN latency_ms END)           AS max_lat,
                AVG(packet_loss)                                              AS avg_loss,
                AVG(jitter_ms)                                                AS avg_jit
            FROM ping_results
            WHERE timestamp > ?
            GROUP BY host_id
        """, (since_1d, since_1d, since_7d))
        stats_map = {r['host_id']: dict(r) for r in rows}

        # 30-day uptime from ping_daily rollup — tiny table, very fast
        since_30d = utc_since_str(days=30)
        daily_rows = db_all(
            'SELECT host_id, SUM(total) t, SUM(online) u '
            'FROM ping_daily WHERE day_ts>? GROUP BY host_id', (since_30d,))
        daily_map = {r['host_id']: (r['u'] or 0, r['t'] or 1) for r in daily_rows}

        # Current status from host_status — O(1), no ping_results scan at all
        status_map = {r['host_id']: dict(r) for r in db_all('SELECT * FROM host_status')}

        # Incident count — alerts table is small
        inc_map = {r['host_id']: r['c'] for r in db_all(
            'SELECT host_id, COUNT(*) c FROM alerts '
            'WHERE type="offline" AND timestamp>? GROUP BY host_id', (since_7d,))}

        out = []
        cache_rows = []
        now_str = datetime.now().isoformat()

        for h in hosts:
            hid = h['id']; h = dict(h)
            s   = stats_map.get(hid, {})
            hs  = status_map.get(hid, {})
            inc = inc_map.get(hid, 0)
            dwn = s.get('offline_cnt', 0) or 0

            up1  = round((s.get('online_1d') or 0) / max(s.get('total_1d') or 1, 1) * 100, 3)
            up7  = round((s.get('online_all') or 0) / max(s.get('total') or 1, 1) * 100, 3)
            d_u, d_t = daily_map.get(hid, (0, 1))
            r_u = s.get('online_all', 0) or 0
            r_t = s.get('total', 0) or 0
            up30 = round((r_u + d_u) / max(r_t + d_t, 1) * 100, 3)

            row = {
                'host_id':        hid,
                'name':           h['name'],
                'ip':             h['ip'],
                'group':          h['group_name'],
                'location':       h.get('location', ''),
                'uptime_1d':      up1,
                'uptime_7d':      up7,
                'uptime_30d':     up30,
                'incidents':      inc,
                'downtime_mins':  round(dwn * h['ping_interval'] / 60, 1),
                'avg_latency':    round(s['avg_lat'], 2) if s.get('avg_lat') else None,
                'min_latency':    round(s['min_lat'], 2) if s.get('min_lat') else None,
                'max_latency':    round(s['max_lat'], 2) if s.get('max_lat') else None,
                'avg_loss':       round(s['avg_loss'], 2) if s.get('avg_loss') else None,
                'avg_jitter':     round(s['avg_jit'], 2) if s.get('avg_jit') else None,
                'current_status':  hs.get('status', 'unknown'),
                'current_latency': round(hs['latency_ms'], 2) if hs.get('latency_ms') else None,
                'last_check':     hs.get('updated_at'),
            }
            out.append(row)
            cache_rows.append((
                hid, now_str, up1, up7, up30,
                row['avg_latency'], row['min_latency'], row['max_latency'],
                row['avg_loss'], row['avg_jitter'],
                inc, row['downtime_mins'],
                row['current_status'], row['current_latency'], row['last_check']
            ))

        # One batched transaction — 87 hosts = 1 commit, not 87
        if cache_rows:
            try:
                conn = get_db()
                conn.executemany("""INSERT OR REPLACE INTO report_cache
                    (host_id,cached_at,uptime_1d,uptime_7d,uptime_30d,
                     avg_latency,min_latency,max_latency,avg_loss,avg_jitter,
                     incidents,downtime_mins,cur_status,cur_latency,last_check)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", cache_rows)
                conn.commit()
            except Exception as e:
                log.error(f'Report cache batch write error: {e}')

        return out

    except Exception as e:
        log.error(f'Report cache build error: {e}')
        return []
    finally:
        close_thread_db()
def _refresh_report_cache_bg():
    """Background thread: rebuild cache every 5 minutes."""
    global _report_cache, _report_cache_ts
    while _running:
        result = _build_report_cache()
        with _report_cache_lock:
            if result:
                _report_cache    = result
                _report_cache_ts = datetime.now()
        time.sleep(_CACHE_TTL_SECS)

def get_report(days=30):
    """Return report from in-memory cache — instant response."""
    global _report_cache, _report_cache_ts
    with _report_cache_lock:
        cached = list(_report_cache)

    if cached:
        return cached

    # Cache empty (first startup) — try DB cache table
    hosts = db_all('SELECT * FROM hosts ORDER BY group_name, name')
    if not hosts:
        return []

    host_map = {h['id']: dict(h) for h in hosts}
    rows = db_all('SELECT * FROM report_cache')
    if rows:
        out = []
        for r in rows:
            h = host_map.get(r['host_id'], {})
            if not h: continue
            out.append({
                'host_id':       r['host_id'],
                'name':          h['name'],     'ip': h['ip'],
                'group':         h['group_name'], 'location': h.get('location',''),
                'uptime_1d':     r['uptime_1d'],
                'uptime_7d':     r['uptime_7d'],
                'uptime_30d':    r['uptime_30d'],
                'incidents':     r['incidents'],
                'downtime_mins': r['downtime_mins'],
                'avg_latency':   r['avg_latency'],
                'min_latency':   r['min_latency'],
                'max_latency':   r['max_latency'],
                'avg_loss':      r['avg_loss'],
                'avg_jitter':    r['avg_jitter'],
                'current_status':  r['cur_status'],
                'current_latency': r['cur_latency'],
                'last_check':    r['last_check'],
            })
        # Warm the in-memory cache from DB so next call is instant
        with _report_cache_lock:
            _report_cache    = out
            _report_cache_ts = datetime.now()
        return out

    # Truly first run — build synchronously this one time
    log.info('First report build — computing now (subsequent loads will be instant)...')
    result = _build_report_cache()
    with _report_cache_lock:
        _report_cache    = result
        _report_cache_ts = datetime.now()
    return result

def get_period_report_html(period_days=7, period_label='Weekly', uptime_key='uptime_7d'):
    """Generate a self-contained HTML report (weekly or monthly) suitable for printing or saving as PDF."""
    company = cfg('company_name', 'AbayoNet Enterprise')
    report  = get_report(period_days)
    now_str = datetime.now().strftime('%A, %d %B %Y  %H:%M')
    period_start = (datetime.now()-timedelta(days=period_days)).strftime('%d %b %Y')
    period_end   = datetime.now().strftime('%d %b %Y')
    total   = len(report)
    online  = sum(1 for h in report if h['current_status']=='online')
    avg_up  = round(sum(h[uptime_key] for h in report)/total,2) if total else 0
    total_inc = sum(h['incidents'] for h in report)

    rows = ''
    for h in report:
        up = h[uptime_key]
        up_color = '#16a34a' if up>=99 else '#d97706' if up>=95 else '#dc2626'
        st_color = '#16a34a' if h['current_status']=='online' else '#dc2626' if h['current_status']=='offline' else '#6b7280'
        rows += f"""
        <tr>
          <td><strong>{h['name']}</strong></td>
          <td style="font-family:monospace;font-size:11px;">{h['ip']}</td>
          <td>{h['group']}</td>
          <td>{h['location'] or '—'}</td>
          <td style="color:{st_color};font-weight:700;text-transform:uppercase;">{h['current_status']}</td>
          <td style="color:{up_color};font-weight:700;">{up:.3f}%</td>
          <td>{h['uptime_1d']:.3f}%</td>
          <td style="font-family:monospace;">{h['avg_latency'] if h['avg_latency'] else '—'} ms</td>
          <td style="font-family:monospace;">{h['min_latency'] if h['min_latency'] else '—'} ms</td>
          <td style="font-family:monospace;">{h['max_latency'] if h['max_latency'] else '—'} ms</td>
          <td style="font-family:monospace;">{h['avg_loss'] if h['avg_loss'] else '0.0'}%</td>
          <td style="{'color:#dc2626;font-weight:700;' if h['incidents']>0 else ''}">{h['incidents']}</td>
          <td style="font-family:monospace;">{h['downtime_mins']} min</td>
        </tr>"""

    # Recent alerts for the past 7 days
    alert_rows = ''
    since_period = utc_since_str(days=period_days)
    alerts = db_all("""
        SELECT a.timestamp, a.type, a.message, a.severity, h.name host_name
        FROM alerts a LEFT JOIN hosts h ON a.host_id=h.id
        WHERE a.timestamp > ?
        ORDER BY a.timestamp DESC LIMIT 100""", (since_period,))
    for a in alerts:
        sev_color = '#dc2626' if a['severity']=='critical' else '#d97706' if a['severity']=='warning' else '#2563eb'
        alert_rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:11px;white-space:nowrap;">{a['timestamp']}</td>
          <td>{a['host_name'] or '—'}</td>
          <td style="color:{sev_color};font-weight:700;text-transform:uppercase;">{a['severity']}</td>
          <td>{a['message']}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{period_label} NOC Report — {company}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0;}}
  body{{font-family:'Segoe UI',Arial,sans-serif;font-size:12px;color:#1e293b;background:#f8fafc;}}
  .page{{max-width:1200px;margin:0 auto;padding:28px 24px;}}
  .header{{background:linear-gradient(135deg,#0f172a,#1e3a5f);color:#fff;border-radius:10px;padding:24px 28px;margin-bottom:20px;}}
  .header h1{{font-size:22px;font-weight:700;letter-spacing:1px;margin-bottom:4px;}}
  .header .sub{{color:#94a3b8;font-size:12px;}}
  .header .period{{color:#38bdf8;font-size:13px;font-weight:600;margin-top:6px;}}
  .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;}}
  .kpi{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;text-align:center;box-shadow:0 1px 3px #0001;}}
  .kpi .val{{font-size:26px;font-weight:700;margin-bottom:2px;}}
  .kpi .lbl{{font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;}}
  .section{{background:#fff;border:1px solid #e2e8f0;border-radius:8px;margin-bottom:20px;overflow:hidden;box-shadow:0 1px 3px #0001;}}
  .section-title{{background:#f1f5f9;padding:10px 16px;font-weight:700;font-size:12px;color:#334155;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #e2e8f0;}}
  table{{width:100%;border-collapse:collapse;font-size:11px;}}
  th{{background:#f8fafc;padding:8px 10px;text-align:left;font-weight:600;color:#475569;border-bottom:2px solid #e2e8f0;white-space:nowrap;}}
  td{{padding:7px 10px;border-bottom:1px solid #f1f5f9;vertical-align:middle;}}
  tr:last-child td{{border-bottom:none;}}
  tr:hover td{{background:#f8fafc;}}
  .footer{{text-align:center;color:#94a3b8;font-size:10px;margin-top:16px;}}
  @media print{{
    body{{background:#fff;}}
    .page{{max-width:100%;padding:10px;}}
    .print-btn{{display:none!important;}}
  }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;">
      <div>
        <h1>📡 {period_label.upper()} NOC UPTIME REPORT</h1>
        <div class="sub">{company} · Generated: {now_str}</div>
        <div class="period">Report Period: {period_start} → {period_end} ({period_days} days)</div>
      </div>
      <button class="print-btn" onclick="window.print()" style="background:#38bdf8;color:#0f172a;border:none;padding:9px 18px;border-radius:6px;font-weight:700;cursor:pointer;font-size:12px;">🖨 Print / Save PDF</button>
    </div>
  </div>

  <div class="kpis">
    <div class="kpi"><div class="val" style="color:#0f172a;">{total}</div><div class="lbl">Total Hosts</div></div>
    <div class="kpi"><div class="val" style="color:#16a34a;">{online}</div><div class="lbl">Currently Online</div></div>
    <div class="kpi"><div class="val" style="color:{'#16a34a' if avg_up>=99 else '#d97706' if avg_up>=95 else '#dc2626'};">{avg_up:.2f}%</div><div class="lbl">Avg Uptime ({period_days}d)</div></div>
    <div class="kpi"><div class="val" style="color:{'#dc2626' if total_inc>0 else '#16a34a'};">{total_inc}</div><div class="lbl">Total Incidents ({period_days}d)</div></div>
  </div>

  <div class="section">
    <div class="section-title">📋 Host Uptime Summary</div>
    <div style="overflow-x:auto;">
    <table>
      <thead><tr>
        <th>Host</th><th>IP Address</th><th>Group</th><th>Location</th>
        <th>Status</th><th>Uptime {period_days}d</th><th>Uptime 24h</th>
        <th>Avg Lat</th><th>Min Lat</th><th>Max Lat</th>
        <th>Pkt Loss</th><th>Incidents</th><th>Downtime</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
  </div>

  <div class="section">
    <div class="section-title">🔔 Alert Log (Last {period_days} Days — up to 100 events)</div>
    <div style="overflow-x:auto;">
    <table>
      <thead><tr><th>Timestamp</th><th>Host</th><th>Severity</th><th>Message</th></tr></thead>
      <tbody>{alert_rows if alert_rows else f'<tr><td colspan="4" style="text-align:center;padding:16px;color:#94a3b8;">No alerts in the last {period_days} days ✓</td></tr>'}</tbody>
    </table>
    </div>
  </div>

  <div class="footer">
    AbayoNet Enterprise NOC Monitor · Report generated {now_str} · {total} hosts monitored
  </div>
</div>
</body>
</html>"""

def get_weekly_report_html():
    return get_period_report_html(7, 'Weekly', 'uptime_7d')

def get_monthly_report_html():
    return get_period_report_html(30, 'Monthly', 'uptime_30d')

# ── HOST IMPORT / EXPORT ─────────────────────────────────────────
def export_json():
    hosts=db_all('SELECT ip,name,group_name,tags,description,location,alert_email,ping_interval,packet_count,timeout_ms,port_checks,notes FROM hosts ORDER BY group_name,name')
    return json.dumps({'abayonet_export':True,'version':VERSION,'exported_at':datetime.now().isoformat(),'host_count':len(hosts),'hosts':[dict(h) for h in hosts]},indent=2)

def export_csv_hosts():
    hosts=db_all('SELECT ip,name,group_name,tags,description,location,alert_email,ping_interval,packet_count,timeout_ms,port_checks,notes FROM hosts ORDER BY group_name,name')
    out=io.StringIO()
    w=csv.DictWriter(out,fieldnames=['ip','name','group_name','tags','description','location','alert_email','ping_interval','packet_count','timeout_ms','port_checks','notes'])
    w.writeheader()
    for h in hosts: w.writerow(dict(h))
    return out.getvalue()

def import_json(data):
    added = skipped = errors = 0
    # Accept: AbayoNet export {"abayonet_export":true,"hosts":[...]}
    # OR plain list [{ip:...}]  OR {"ips":[...]}  OR plain IP strings
    if isinstance(data, list):
        host_list = data
    elif isinstance(data, dict):
        host_list = data.get('hosts', data.get('data', data.get('ips', [])))
    else:
        return 0, 0, 1

    for h in host_list:
        if isinstance(h, str):          # plain IP string in list
            h = {'ip': h.strip()}
        ip = str(h.get('ip', h.get('address', h.get('host', '')))).strip()
        if not ip:
            errors += 1; continue
        try:
            if db_one('SELECT id FROM hosts WHERE ip=?', (ip,)):
                skipped += 1; continue
            db_exec(
                'INSERT INTO hosts(ip,name,group_name,tags,description,location,alert_email,ping_interval,packet_count,timeout_ms,port_checks,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (ip,
                 h.get('name', ''),
                 h.get('group_name', h.get('group', 'Default')),
                 h.get('tags', ''),
                 h.get('description', ''),
                 h.get('location', ''),
                 h.get('alert_email', ''),
                 int(h.get('ping_interval', 30)),
                 int(h.get('packet_count', 4)),
                 int(h.get('timeout_ms', 1000)),
                 h.get('port_checks', ''),
                 h.get('notes', '')))
            new = db_one('SELECT * FROM hosts WHERE ip=?', (ip,))
            if new: start_monitor(dict(new))
            added += 1
        except Exception as e:
            log.error(f'Import {ip}: {e}'); errors += 1
    return added, skipped, errors

def scan_subnet(subnet):
    results=[]; lock=threading.Lock()
    def scan_ip(ip):
        r=ping(str(ip),1,1000)
        if r['status']=='online':
            with lock: results.append({'ip':str(ip),'latency_ms':r.get('latency'),'hostname':resolve(str(ip)),'ttl':r.get('ttl')})
    threads=[]
    try:
        for ip in list(ipaddress.ip_network(subnet,strict=False).hosts())[:254]:
            t=threading.Thread(target=scan_ip,args=(ip,),daemon=True); t.start(); threads.append(t)
        for t in threads: t.join(timeout=6)
    except Exception as e: log.error(f'Scan: {e}')
    return sorted(results,key=lambda x:int(x['ip'].split('.')[-1]))

def run_trace(ip):
    sname = platform.system().lower()
    try:
        if sname == 'windows':
            # -d: no DNS, -h 15: max 15 hops, -w 300: 300ms per hop timeout
            cmd = ['tracert', '-d', '-h', '15', '-w', '300', ip]
            timeout = 25
        else:
            cmd = ['traceroute', '-n', '-m', '15', '-w', '1', ip]
            timeout = 25
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout or r.stderr or 'No output'
    except subprocess.TimeoutExpired:
        return 'Timed out after 25s'
    except Exception as e:
        return f'Error: {e}'

# ── HTTP HANDLER ─────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass

    def cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type,Authorization')

    def json(self, data, code=200):
        try:
            b = json.dumps(data, default=str).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(b))
            self.cors(); self.end_headers(); self.wfile.write(b)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass  # client disconnected before response sent — ignore

    def file_dl(self, data, mime, fname):
        try:
            if isinstance(data, str): data = data.encode()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Disposition', f'attachment; filename="{fname}"')
            self.send_header('Content-Length', len(data))
            self.cors(); self.end_headers(); self.wfile.write(data)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass

    def html(self, path):
        try:
            with open(path,'rb') as f: d=f.read()
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',len(d))
            # Always serve the latest file from disk — never let the browser
            # cache a stale copy of the SPA shell after an update.
            self.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
            self.send_header('Pragma','no-cache')
            self.end_headers(); self.wfile.write(d)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def body(self):
        try:
            n = int(self.headers.get('Content-Length') or 0)
            if n > 0:
                raw = self.rfile.read(n)
            else:
                # No Content-Length header — read all available bytes
                chunks = []
                while True:
                    chunk = self.rfile.read(8192)
                    if not chunk:
                        break
                    chunks.append(chunk)
                raw = b''.join(chunks)
            return json.loads(raw.decode('utf-8')) if raw and raw.strip() else {}
        except Exception as e:
            log.error(f'POST body parse error: {e}')
            return {}

    def do_OPTIONS(self):
        self.send_response(200); self.cors(); self.end_headers()

    def do_GET(self):
        path=urlparse(self.path).path
        qs=parse_qs(urlparse(self.path).query)
        def qp(k,d=''): return qs.get(k,[d])[0]

        if path in ('/','/index.html','/login'):
            self.html('static/index.html'); return
        if path=='/api/version':
            self.json({'version':VERSION,'uptime':round(time.time()-_t0)}); return
        if path=='/api/auth/check':
            sess=check_session(get_token(self))
            self.json({'authenticated':bool(sess),'username':sess['username'] if sess else None,'role':sess['role'] if sess else None}); return
        if path=='/api/auth/renew':
            token=get_token(self); sess=check_session(token)
            if sess: renew_session(token)
            self.json({'ok':bool(sess)}); return

        sess=auth(self)
        if not sess: return
        is_admin=sess['role']=='admin'

        try:
            # DASHBOARD
            if path=='/api/dashboard':
                total   = db_one('SELECT COUNT(*) FROM hosts')[0]
                online  = db_one("SELECT COUNT(*) FROM host_status WHERE status='online'")[0]
                offline = db_one("SELECT COUNT(*) FROM host_status WHERE status='offline'")[0]
                unack   = db_one('SELECT COUNT(*) FROM alerts WHERE acknowledged=0')[0]
                since_1h = utc_since_str(hours=1)
                avg_lat  = db_one("SELECT ROUND(AVG(latency_ms),2) FROM ping_results WHERE timestamp>? AND status='online'",(since_1h,))[0]
                avg_loss = db_one("SELECT ROUND(AVG(packet_loss),2) FROM ping_results WHERE timestamp>?",(since_1h,))[0]
                degraded = db_one("SELECT COUNT(*) FROM host_status WHERE packet_loss>5")[0]
                self.json({'total':total,'online':online,'offline':offline,
                    'unknown':max(0,total-online-offline),
                    'unack_alerts':unack,'avg_latency_1h':avg_lat,
                    'avg_loss_1h':avg_loss,'degraded':degraded}); return

            # DASHBOARD CHART — single query for top-6 hosts with most recent data
            if path=='/api/dashboard/chart':
                since_1h = utc_since_str(hours=1)
                active = db_all(
                    "SELECT p.host_id, h.name, h.ip "
                    "FROM ping_results p JOIN hosts h ON h.id=p.host_id "
                    "WHERE p.timestamp > ? "
                    "GROUP BY p.host_id ORDER BY MAX(p.timestamp) DESC LIMIT 6", (since_1h,))
                if not active:
                    self.json([]); return
                ids = [r['host_id'] for r in active]
                placeholders = ','.join('?' * len(ids))
                rows = db_all(
                    f"SELECT host_id, timestamp, latency_ms, packet_loss, status "
                    f"FROM ping_results WHERE host_id IN ({placeholders}) "
                    f"AND timestamp > ? "
                    f"ORDER BY host_id, timestamp ASC", ids + [since_1h])
                host_data = {}
                for a in active:
                    host_data[a['host_id']] = {'name': a['name'], 'ip': a['ip'], 'points': []}
                for r in rows:
                    if r['host_id'] in host_data:
                        host_data[r['host_id']]['points'].append({
                            'ts': r['timestamp'],
                            'lat': r['latency_ms'],
                            'loss': r['packet_loss'],
                            'status': r['status']
                        })
                self.json(list(host_data.values())); return

            # HOSTS — uses host_status table for O(1) per-host status (no ping_results scan)
            if path=='/api/hosts':
                since_24h = utc_since_str(hours=24)
                hosts = [dict(h) for h in db_all('SELECT * FROM hosts ORDER BY group_name,name')]
                # ONE join query for all current statuses — no per-host loop
                status_map = {r['host_id']: dict(r) for r in db_all(
                    'SELECT * FROM host_status')}
                # ONE bulk uptime query using cover index
                uptime_rows = db_all(
                    "SELECT host_id, "
                    "CAST(SUM(CASE WHEN status='online' THEN 1 ELSE 0 END) AS REAL)"
                    "/MAX(COUNT(*),1)*100 AS up "
                    "FROM ping_results WHERE timestamp>? GROUP BY host_id", (since_24h,))
                uptime_map = {r['host_id']: round(r['up'] or 0, 2) for r in uptime_rows}
                for h in hosts:
                    hid = h['id']
                    s = status_map.get(hid, {})
                    h.update({
                        'status':     s.get('status', 'unknown'),
                        'latency':    s.get('latency_ms'),
                        'loss':       s.get('packet_loss'),
                        'jitter':     s.get('jitter_ms'),
                        'ttl':        s.get('ttl'),
                        'last_check': s.get('updated_at'),
                        'uptime_24h': uptime_map.get(hid, 0.0),
                        'in_maintenance': in_maintenance(hid),
                    })
                self.json(hosts); return

            if path.startswith('/api/host/') and '/history' not in path and '/stats' not in path and '/ports' not in path and '/latest' not in path:
                hid = int(path.split('/')[-1])
                h = dict(db_one('SELECT * FROM hosts WHERE id=?', (hid,)))
                s = db_one('SELECT * FROM host_status WHERE host_id=?', (hid,))
                if s: h.update({'status':s['status'],'latency':s['latency_ms'],'loss':s['packet_loss'],
                                'jitter':s['jitter_ms'],'ttl':s['ttl'],'last_check':s['updated_at']})
                h['in_maintenance'] = in_maintenance(hid)
                self.json(h); return

            if '/history' in path:
                hid=int(path.split('/')[3])
                from_p=qp('from',''); to_p=qp('to','')
                if from_p and to_p:
                    since=from_p; until=to_p
                    try:
                        span_hours=(datetime.fromisoformat(to_p)-datetime.fromisoformat(from_p)).total_seconds()/3600
                    except Exception:
                        span_hours=24
                else:
                    hours=int(qp('hours','24'))
                    since=utc_since_str(hours=hours)
                    until=None
                    span_hours=hours

                # For short windows (<=7 days), use a Python-computed cutoff —
                # SQLite's localtime modifier is unreliable on some Windows builds
                if span_hours <= 168 and not from_p:
                    since_window = utc_since_str(hours=span_hours)
                    rows = db_all(
                        "SELECT timestamp,status,latency_ms,packet_loss,jitter_ms,ttl "
                        "FROM ping_results WHERE host_id=? "
                        "AND timestamp > ? "
                        "ORDER BY timestamp ASC", (hid, since_window))
                    if len(rows) > 800:
                        step = max(1, len(rows)//800)
                        rows = rows[::step]
                    self.json([dict(r) for r in rows]); return

                # Decide data source based on age of requested window:
                cutoff_raw  = utc_since_str(days=30)
                cutoff_keep = utc_since_str(days=180)

                if since >= cutoff_raw:
                    # Recent window — raw data
                    if until:
                        rows = db_all(
                            'SELECT timestamp,status,latency_ms,packet_loss,jitter_ms,ttl '
                            'FROM ping_results WHERE host_id=? AND timestamp>=? AND timestamp<=? '
                            'ORDER BY timestamp ASC', (hid,since,until))
                    else:
                        rows = db_all(
                            'SELECT timestamp,status,latency_ms,packet_loss,jitter_ms,ttl '
                            'FROM ping_results WHERE host_id=? AND timestamp>? '
                            'ORDER BY timestamp ASC', (hid,since))
                    if len(rows) > 800:
                        step = max(1, len(rows)//800)
                        rows = rows[::step]
                    self.json([dict(r) for r in rows]); return

                elif since >= cutoff_keep:
                    # Historical window — use hourly rollup
                    if until:
                        rows = db_all(
                            'SELECT hour_ts timestamp,'
                            '  CASE WHEN online=total THEN "online" ELSE "offline" END status,'
                            '  ROUND(avg_latency,2) latency_ms, ROUND(avg_loss,2) packet_loss,'
                            '  ROUND(avg_jitter,2) jitter_ms, NULL ttl '
                            'FROM ping_hourly WHERE host_id=? AND hour_ts>=? AND hour_ts<=? '
                            'ORDER BY hour_ts ASC', (hid,since,until))
                    else:
                        rows = db_all(
                            'SELECT hour_ts timestamp,'
                            '  CASE WHEN online=total THEN "online" ELSE "offline" END status,'
                            '  ROUND(avg_latency,2) latency_ms, ROUND(avg_loss,2) packet_loss,'
                            '  ROUND(avg_jitter,2) jitter_ms, NULL ttl '
                            'FROM ping_hourly WHERE host_id=? AND hour_ts>? '
                            'ORDER BY hour_ts ASC', (hid,since))
                    self.json([dict(r) for r in rows]); return

                else:
                    # Very old window — use daily rollup
                    if until:
                        rows = db_all(
                            'SELECT day_ts timestamp,'
                            '  CASE WHEN online=total THEN "online" ELSE "offline" END status,'
                            '  ROUND(avg_latency,2) latency_ms, ROUND(avg_loss,2) packet_loss,'
                            '  ROUND(avg_jitter,2) jitter_ms, NULL ttl '
                            'FROM ping_daily WHERE host_id=? AND day_ts>=? AND day_ts<=? '
                            'ORDER BY day_ts ASC', (hid,since,until))
                    else:
                        rows = db_all(
                            'SELECT day_ts timestamp,'
                            '  CASE WHEN online=total THEN "online" ELSE "offline" END status,'
                            '  ROUND(avg_latency,2) latency_ms, ROUND(avg_loss,2) packet_loss,'
                            '  ROUND(avg_jitter,2) jitter_ms, NULL ttl '
                            'FROM ping_daily WHERE host_id=? AND day_ts>? '
                            'ORDER BY day_ts ASC', (hid,since))
                    self.json([dict(r) for r in rows]); return

            if '/latest' in path:
                hid=int(path.split('/')[3])
                n=int(qp('n','120'))
                since_ts=qp('since','')
                if since_ts:
                    rows=db_all('SELECT timestamp,status,latency_ms,packet_loss,jitter_ms,ttl FROM ping_results WHERE host_id=? AND timestamp>? ORDER BY timestamp ASC',(hid,since_ts))
                else:
                    rows=list(reversed(db_all('SELECT timestamp,status,latency_ms,packet_loss,jitter_ms,ttl FROM ping_results WHERE host_id=? ORDER BY timestamp DESC LIMIT ?',(hid,n))))
                self.json([dict(r) for r in rows]); return

            if '/stats' in path:
                hid=int(path.split('/')[3]); hours=int(qp('hours','24'))
                self.json(get_stats(hid,hours)); return

            if '/ports' in path:
                hid=int(path.split('/')[3])
                self.json([dict(r) for r in db_all('SELECT port,status,latency_ms,timestamp FROM port_results WHERE host_id=? ORDER BY timestamp DESC LIMIT 50',(hid,))]); return

            # ALERTS
            if path=='/api/alerts':
                limit=int(qp('limit','100')); unack=qp('unack','0')=='1'
                wh='WHERE a.acknowledged=0' if unack else ''
                self.json([dict(r) for r in db_all(f'SELECT a.*,h.name host_name,h.ip FROM alerts a LEFT JOIN hosts h ON a.host_id=h.id {wh} ORDER BY a.timestamp DESC LIMIT ?',(limit,))]); return
            if path=='/api/alerts/count':
                self.json({'count':db_one('SELECT COUNT(*) FROM alerts WHERE acknowledged=0')[0]}); return
            if path=='/api/alerts/stats':
                since_24h_a = utc_since_str(hours=24); since_7d_a = utc_since_str(days=7)
                self.json({'last_24h':db_one("SELECT COUNT(*) FROM alerts WHERE timestamp>?",(since_24h_a,))[0],'last_7d':db_one("SELECT COUNT(*) FROM alerts WHERE timestamp>?",(since_7d_a,))[0],'critical_unacked':db_one("SELECT COUNT(*) FROM alerts WHERE acknowledged=0 AND severity='critical'")[0]}); return

            # ALERT RULES
            if path=='/api/alert_rules':
                self.json([dict(r) for r in db_all('SELECT r.*,h.name host_name FROM alert_rules r LEFT JOIN hosts h ON r.host_id=h.id ORDER BY r.id')]); return

            # SETTINGS
            if path=='/api/settings':
                self.json({r['key']:r['value'] for r in db_all('SELECT key,value FROM settings')}); return

            # REPORT
            if path=='/api/report/uptime':
                self.json(get_report(30)); return
            if path=='/api/report/cache-age':
                age = None
                with _report_cache_lock:
                    ts  = _report_cache_ts
                    cnt = len(_report_cache)
                if ts:
                    age = round((datetime.now() - ts).total_seconds())
                self.json({'cached_at': ts.isoformat() if ts else None,
                           'age_secs': age, 'host_count': cnt,
                           'next_refresh_secs': max(0, _CACHE_TTL_SECS - (age or _CACHE_TTL_SECS))}); return
            if path=='/api/report/weekly':
                html = get_weekly_report_html()
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length', len(html.encode()))
                self.cors(); self.end_headers()
                self.wfile.write(html.encode()); return
            if path=='/api/report/monthly':
                html = get_monthly_report_html()
                self.send_response(200)
                self.send_header('Content-Type','text/html; charset=utf-8')
                self.send_header('Content-Length', len(html.encode()))
                self.cors(); self.end_headers()
                self.wfile.write(html.encode()); return
            if path=='/api/report/export':
                rows=get_report(30); out=io.StringIO()
                w=csv.DictWriter(out,fieldnames=['name','ip','group','location','uptime_1d','uptime_7d','uptime_30d','avg_latency','min_latency','max_latency','avg_loss','avg_jitter','incidents','downtime_mins','current_status','current_latency'],extrasaction='ignore')
                w.writeheader(); w.writerows(rows)
                fname=f'abayonet_report_{datetime.now().strftime("%Y%m%d")}.csv'
                self.file_dl(out.getvalue(),'text/csv',fname); return
            if path=='/api/report/weekly/csv':
                rows=get_report(7); out=io.StringIO()
                w=csv.DictWriter(out,fieldnames=['name','ip','group','location','uptime_1d','uptime_7d','avg_latency','min_latency','max_latency','avg_loss','incidents','downtime_mins','current_status'],extrasaction='ignore')
                w.writeheader(); w.writerows(rows)
                fname=f'abayonet_weekly_{datetime.now().strftime("%Y%m%d")}.csv'
                self.file_dl(out.getvalue(),'text/csv',fname); return
            if path=='/api/report/monthly/csv':
                rows=get_report(30); out=io.StringIO()
                w=csv.DictWriter(out,fieldnames=['name','ip','group','location','uptime_1d','uptime_7d','uptime_30d','avg_latency','min_latency','max_latency','avg_loss','incidents','downtime_mins','current_status'],extrasaction='ignore')
                w.writeheader(); w.writerows(rows)
                fname=f'abayonet_monthly_{datetime.now().strftime("%Y%m%d")}.csv'
                self.file_dl(out.getvalue(),'text/csv',fname); return

            # HOST EXPORT
            if path=='/api/hosts/export/json':
                fname=f'abayonet_hosts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                self.file_dl(export_json(),'application/json',fname); return
            if path=='/api/hosts/export/csv':
                fname=f'abayonet_hosts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                self.file_dl(export_csv_hosts(),'text/csv',fname); return

            # MULTI-HOST HISTORY (for analysis page)
            if path=='/api/history/multi':
                ids_raw=qp('ids',''); hours=int(qp('hours','24'))
                ids=[int(x) for x in ids_raw.split(',') if x.strip().isdigit()]
                if not ids: self.json([]); return
                since=utc_since_str(hours=hours)
                out={}
                for hid in ids:
                    h=db_one('SELECT name,ip FROM hosts WHERE id=?',(hid,))
                    if not h: continue
                    rows=db_all('SELECT timestamp,status,latency_ms,packet_loss,jitter_ms FROM ping_results WHERE host_id=? AND timestamp>? ORDER BY timestamp ASC',(hid,since))
                    out[hid]={'name':h['name'],'ip':h['ip'],'data':[dict(r) for r in rows]}
                self.json(out); return

            # TRACEROUTE
            if path.startswith('/api/traceroute/'):
                self.json({'output':run_trace(path.split('/')[-1])}); return

            # MAINTENANCE
            if path=='/api/maintenance':
                self.json([dict(r) for r in db_all('SELECT m.*,h.name host_name,h.ip FROM maintenance m LEFT JOIN hosts h ON m.host_id=h.id ORDER BY m.start_time DESC')]); return

            # GROUPS / TAGS
            if path=='/api/groups':
                self.json([r[0] for r in db_all('SELECT DISTINCT group_name FROM hosts ORDER BY group_name')]); return
            if path=='/api/tags':
                tags=set()
                for r in db_all('SELECT tags FROM hosts'):
                    for t in (r[0] or '').split(','):
                        if t.strip(): tags.add(t.strip())
                self.json(sorted(tags)); return

            # USERS (admin)
            if path=='/api/users':
                if not is_admin: self.json({'error':'Admin only'},403); return
                self.json([dict(r) for r in db_all('SELECT id,username,role,full_name,email,created_at,last_login,active FROM users ORDER BY id')]); return
            if path=='/api/users/me':
                u=db_one('SELECT id,username,role,full_name,email,created_at,last_login FROM users WHERE username=?',(sess['username'],))
                self.json(dict(u) if u else {}); return

            self.json({'error':'Not found'},404)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass  # client disconnected — normal, not an error
        except Exception as e:
            log.error(f'GET {path}: {e}')
            try: self.json({'error': str(e)}, 500)
            except Exception: pass

    def do_POST(self):
        path=urlparse(self.path).path

        # PUBLIC: Login
        if path=='/api/auth/login':
            try:
                b=self.body(); ip=self.client_address[0]
                u=db_one('SELECT * FROM users WHERE username=? AND active=1',(b.get('username','').strip(),))
                if not u or u['password']!=hashpw(b.get('password','')):
                    log.warning(f'Failed login: {b.get("username")} from {ip}')
                    self.json({'error':'Invalid username or password'},401); return
                token=make_session(u['id'],u['username'],u['role'],ip)
                log.info(f'Login: {u["username"]} ({u["role"]}) from {ip}')
                self.json({'success':True,'token':token,'username':u['username'],'role':u['role'],'full_name':u['full_name']})
            except Exception as e: self.json({'error':str(e)},500)
            return

        # PUBLIC: Logout
        if path=='/api/auth/logout':
            token=get_token(self)
            if token: db_exec('DELETE FROM sessions WHERE token=?',(token,))
            self.json({'success':True}); return

        sess=auth(self)
        if not sess: return
        b=self.body(); is_admin=sess['role']=='admin'

        try:
            # ADD HOST
            if path=='/api/hosts':
                if not is_admin: self.json({'error':'Admin only'},403); return
                ip=b.get('ip','').strip()
                if not ip: self.json({'error':'IP required'},400); return
                name=b.get('name','').strip() or resolve(ip) or ip
                db_exec('INSERT INTO hosts(ip,name,group_name,tags,description,location,alert_email,ping_interval,packet_count,timeout_ms,port_checks,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ip,name,b.get('group','Default'),b.get('tags',''),b.get('description',''),b.get('location',''),
                     b.get('alert_email',''),max(10,int(b.get('interval',30))),min(20,max(1,int(b.get('packet_count',4)))),
                     int(b.get('timeout_ms',1000)),b.get('port_checks',''),b.get('notes','')))
                h=dict(db_one('SELECT * FROM hosts WHERE ip=?',(ip,)))
                start_monitor(h); self.json({'success':True,'host':h}); return

            # UPDATE HOST
            if path.startswith('/api/hosts/') and '/toggle' not in path and '/bulk' not in path:
                if not is_admin: self.json({'error':'Admin only'},403); return
                hid=int(path.split('/')[-1])
                db_exec('UPDATE hosts SET name=?,group_name=?,tags=?,description=?,location=?,alert_email=?,ping_interval=?,packet_count=?,timeout_ms=?,port_checks=?,notes=? WHERE id=?',
                    (b.get('name',''),b.get('group','Default'),b.get('tags',''),b.get('description',''),b.get('location',''),
                     b.get('alert_email',''),max(10,int(b.get('interval',30))),min(20,max(1,int(b.get('packet_count',4)))),
                     int(b.get('timeout_ms',1000)),b.get('port_checks',''),b.get('notes',''),hid))
                self.json({'success':True}); return

            # TOGGLE HOST
            if '/toggle' in path and path.startswith('/api/hosts/'):
                if not is_admin: self.json({'error':'Admin only'},403); return
                hid=int(path.split('/')[-2])
                db_exec('UPDATE hosts SET enabled=? WHERE id=?',(b.get('enabled',1),hid))
                self.json({'success':True}); return

            # BULK DELETE
            if path=='/api/hosts/bulk_delete':
                if not is_admin: self.json({'error':'Admin only'},403); return
                for hid in b.get('ids',[]): db_exec('DELETE FROM hosts WHERE id=?',(hid,))
                self.json({'success':True}); return

            # IMPORT HOSTS
            if path=='/api/hosts/import':
                if not is_admin: self.json({'error':'Admin only'},403); return
                if not b:
                    self.json({'error':'Empty request body — no data received. Try again.'},400); return
                added,skipped,errors=import_json(b)
                if added==0 and skipped==0 and errors==0:
                    self.json({'error':'No hosts found in file. Check file format.'},400); return
                self.json({'success':True,'added':added,'skipped':skipped,'errors':errors}); return

            # FORCE-REFRESH REPORT CACHE
            if path=='/api/report/refresh':
                def _do_refresh():
                    global _report_cache, _report_cache_ts
                    result = _build_report_cache()
                    with _report_cache_lock:
                        if result:
                            _report_cache    = result
                            _report_cache_ts = datetime.now()
                threading.Thread(target=_do_refresh, daemon=True, name='report-refresh').start()
                self.json({'ok': True, 'message': 'Cache refresh started in background'}); return

            # PING NOW
            if path.startswith('/api/ping/'):
                self.json(ping(path.split('/')[-1],4)); return

            # SCAN
            if path=='/api/scan':
                if not is_admin: self.json({'error':'Admin only'},403); return
                self.json(scan_subnet(b.get('subnet','192.168.1.0/24'))); return

            # ACK ALERTS
            if path.startswith('/api/alerts/') and path.endswith('/ack'):
                aid=int(path.split('/')[-2])
                db_exec("UPDATE alerts SET acknowledged=1,ack_by=?,ack_at=? WHERE id=?",(sess['username'],datetime.now().isoformat(),aid))
                self.json({'success':True}); return
            if path=='/api/alerts/ack_all':
                db_exec("UPDATE alerts SET acknowledged=1,ack_by=?,ack_at=?",(sess['username'],datetime.now().isoformat()))
                self.json({'success':True}); return

            # ALERT RULES
            if path=='/api/alert_rules':
                if not is_admin: self.json({'error':'Admin only'},403); return
                db_exec('INSERT INTO alert_rules(name,host_id,condition,threshold,duration_mins,notify_email,notify_webhook,cooldown_mins,enabled) VALUES(?,?,?,?,?,?,?,?,1)',
                    (b.get('name','Rule'),int(b.get('host_id',0)),b.get('condition','offline'),
                     float(b.get('threshold',0)),int(b.get('duration_mins',0)),
                     b.get('notify_email',''),b.get('notify_webhook',''),max(1,int(b.get('cooldown_mins',5)))))
                self.json({'success':True}); return
            if path.startswith('/api/alert_rules/') and '/toggle' in path:
                if not is_admin: self.json({'error':'Admin only'},403); return
                rid=int(path.split('/')[-2])
                db_exec('UPDATE alert_rules SET enabled=? WHERE id=?',(int(b.get('enabled',1)),rid))
                self.json({'success':True}); return

            # SETTINGS
            if path=='/api/settings':
                if not is_admin: self.json({'error':'Admin only'},403); return
                for k,v in b.items(): db_exec('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,str(v)))
                self.json({'success':True}); return

            # MAINTENANCE
            if path=='/api/maintenance':
                if not is_admin: self.json({'error':'Admin only'},403); return
                db_exec('INSERT INTO maintenance(host_id,name,start_time,end_time) VALUES(?,?,?,?)',
                    (b.get('host_id'),b.get('name','Maintenance'),b.get('start_time'),b.get('end_time')))
                self.json({'success':True}); return

            # CREATE USER (admin)
            if path=='/api/users':
                if not is_admin: self.json({'error':'Admin only'},403); return
                uname=b.get('username','').strip()
                if not uname: self.json({'error':'Username required'},400); return
                pwd=b.get('password','')
                if len(pwd)<6: self.json({'error':'Password must be at least 6 characters'},400); return
                role=b.get('role','readonly')
                if role not in ('admin','readonly'): self.json({'error':'Role must be admin or readonly'},400); return
                if db_one('SELECT id FROM users WHERE username=?',(uname,)):
                    self.json({'error':'Username already exists'},409); return
                db_exec('INSERT INTO users(username,password,role,full_name,email) VALUES(?,?,?,?,?)',
                    (uname,hashpw(pwd),role,b.get('full_name',''),b.get('email','')))
                log.info(f'User created: {uname} ({role}) by {sess["username"]}')
                self.json({'success':True}); return

            # TOGGLE USER (admin)
            if path.startswith('/api/users/') and path.endswith('/toggle'):
                if not is_admin: self.json({'error':'Admin only'},403); return
                uid=int(path.split('/')[-2])
                db_exec('UPDATE users SET active=? WHERE id=?',(int(b.get('active',1)),uid))
                self.json({'success':True}); return

            # RESET PASSWORD (admin)
            if path.startswith('/api/users/') and path.endswith('/reset_password'):
                if not is_admin: self.json({'error':'Admin only'},403); return
                uid=int(path.split('/')[-2])
                pwd=b.get('password','')
                if len(pwd)<6: self.json({'error':'Password too short'},400); return
                db_exec('UPDATE users SET password=? WHERE id=?',(hashpw(pwd),uid))
                db_exec('DELETE FROM sessions WHERE user_id=?',(uid,))
                self.json({'success':True}); return

            # CHANGE OWN PASSWORD
            if path=='/api/users/change_password':
                old=b.get('old_password',''); new=b.get('new_password','')
                if len(new)<6: self.json({'error':'Password too short'},400); return
                u=db_one('SELECT * FROM users WHERE username=?',(sess['username'],))
                if not u or u['password']!=hashpw(old):
                    self.json({'error':'Current password incorrect'},401); return
                db_exec('UPDATE users SET password=? WHERE username=?',(hashpw(new),sess['username']))
                self.json({'success':True}); return

            self.json({'error':'Not found'},404)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass  # client disconnected — normal, not an error
        except Exception as e:
            log.error(f'POST {path}: {e}')
            try: self.json({'error': str(e)}, 500)
            except Exception: pass

    def do_DELETE(self):
        path=urlparse(self.path).path
        # Alerts can be cleared by any logged-in user (same as acknowledging) —
        # admin is only required for destructive host/user/rule operations below.
        sess=auth(self)
        if not sess: return
        is_admin=sess['role']=='admin'
        try:
            if path=='/api/alerts':
                qs=parse_qs(urlparse(self.path).query)
                only_ack=qs.get('acknowledged',[''])[0]=='1'
                if only_ack:
                    n=db_exec('DELETE FROM alerts WHERE acknowledged=1').rowcount
                else:
                    n=db_exec('DELETE FROM alerts').rowcount
                self.json({'success':True,'deleted':n}); return
            if path.startswith('/api/alerts/'):
                aid=int(path.split('/')[-1])
                n=db_exec('DELETE FROM alerts WHERE id=?',(aid,)).rowcount
                self.json({'success':True,'deleted':n}); return

            if not is_admin: self.json({'error':'Admin access required'},403); return
            if path.startswith('/api/hosts/'):
                db_exec('DELETE FROM hosts WHERE id=?',(int(path.split('/')[-1]),)); self.json({'success':True}); return
            if path.startswith('/api/alert_rules/'):
                db_exec('DELETE FROM alert_rules WHERE id=?',(int(path.split('/')[-1]),)); self.json({'success':True}); return
            if path.startswith('/api/maintenance/'):
                db_exec('DELETE FROM maintenance WHERE id=?',(int(path.split('/')[-1]),)); self.json({'success':True}); return
            if path.startswith('/api/users/'):
                uid=int(path.split('/')[-1])
                if uid==1: self.json({'error':'Cannot delete primary admin'},403); return
                db_exec('DELETE FROM users WHERE id=?',(uid,)); self.json({'success':True}); return
            self.json({'error':'Not found'},404)
        except Exception as e:
            self.json({'error':str(e)},500)

_t0=time.time()

def get_local_ip():
    """Get the server's primary LAN IP address for display purposes."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '0.0.0.0'

def main():
    global _email_queue
    log.info(f'=== AbayoNet Enterprise v{VERSION} ===')
    init_db(); start_all()

    # Start email worker — single thread drains queue, no unbounded thread spawning
    _email_queue = queue.Queue(maxsize=100)
    threading.Thread(target=_email_worker, args=(_email_queue,), daemon=True, name='email-worker').start()

    threading.Thread(target=cleanup_loop, daemon=True).start()

    PORT = 8780
    for p in [8780, 8781, 8782, 9100]:
        try:
            server = ThreadingHTTPServer(('0.0.0.0', p), H)
            server.timeout = 30          # request timeout — prevents slow clients blocking threads
            server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            PORT = p; break
        except OSError:
            continue

    local_ip = get_local_ip()
    log.info(f'Dashboard → http://127.0.0.1:{PORT}  (local)')
    log.info(f'Network   → http://{local_ip}:{PORT}  (LAN / remote)')
    log.info(f'Listening on all interfaces, port {PORT}')

    def _open():
        time.sleep(1.8); webbrowser.open(f'http://127.0.0.1:{PORT}')
    threading.Thread(target=_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        global _running
        _running = False
        if _email_queue: _email_queue.put(None)   # signal worker to stop
        log.info('AbayoNet stopped.')

if __name__ == '__main__': main()

if __name__=='__main__': main()
