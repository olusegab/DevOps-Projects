#!/usr/bin/env python3
"""
AbayoNet Enterprise Network Monitor v4.0
Fixes: Database lock (per-thread connection pool)
New:   Login page, Admin/ReadOnly users, User management, Host import/export
"""
import os, sys, threading, time, json, sqlite3, subprocess, platform
import socket, re, smtplib, logging, csv, io, ipaddress, hashlib, secrets
import webbrowser
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
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
VERSION = '4.0.0'

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
        c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('PRAGMA synchronous=NORMAL')
        c.execute('PRAGMA foreign_keys=ON')
        c.execute('PRAGMA busy_timeout=30000')
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
    for attempt in range(5):
        try:
            conn = get_db()
            cur = conn.execute(sql, params)
            conn.commit()
            return cur
        except sqlite3.OperationalError as e:
            if 'locked' in str(e).lower() and attempt < 4:
                log.warning(f'DB lock retry {attempt+1}: {e}')
                time.sleep(0.4 * (attempt+1))
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
            created_at      TEXT DEFAULT (datetime('now')),
            notes           TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ping_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id     INTEGER NOT NULL,
            timestamp   TEXT DEFAULT (datetime('now')),
            status      TEXT NOT NULL,
            latency_ms  REAL,
            packet_loss REAL,
            jitter_ms   REAL,
            ttl         INTEGER,
            FOREIGN KEY (host_id) REFERENCES hosts(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ping_host_ts ON ping_results(host_id,timestamp DESC);

        CREATE TABLE IF NOT EXISTS port_results (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            host_id     INTEGER NOT NULL,
            timestamp   TEXT DEFAULT (datetime('now')),
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
            timestamp       TEXT DEFAULT (datetime('now')),
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
            created_at  TEXT DEFAULT (datetime('now'))
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
            created_at  TEXT DEFAULT (datetime('now')),
            last_login  TEXT DEFAULT '',
            active      INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token       TEXT PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            username    TEXT NOT NULL,
            role        TEXT NOT NULL,
            created_at  TEXT DEFAULT (datetime('now')),
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
    exp = (datetime.now()+timedelta(hours=24)).isoformat()
    db_exec('INSERT INTO sessions(token,user_id,username,role,expires_at,ip) VALUES(?,?,?,?,?,?)',(token,uid,uname,role,exp,ip))
    db_exec('UPDATE users SET last_login=? WHERE id=?',(datetime.now().isoformat(),uid))
    return token

def check_session(token):
    if not token: return None
    try:
        r = db_one('SELECT username,role,expires_at FROM sessions WHERE token=?',(token,))
        if not r: return None
        if datetime.fromisoformat(r['expires_at']) < datetime.now():
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
def ping(ip, count=4, timeout_ms=1000):
    sname = platform.system().lower()
    ts = max(1, timeout_ms//1000)
    try:
        cmd = (['ping','-n',str(count),'-w',str(timeout_ms),ip]
               if sname=='windows' else
               ['ping','-c',str(count),'-W',str(ts),ip])
        r = subprocess.run(cmd,capture_output=True,text=True,timeout=count*ts+8)
        return parse_ping(r.stdout+r.stderr,sname,count)
    except:
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
_astate = {}

def fire_alerts(host_id, hname, ip, result):
    try:
        rules = db_all('SELECT * FROM alert_rules WHERE (host_id=? OR host_id=0) AND enabled=1',(host_id,))
        now = datetime.now()
        for rule in rules:
            rule=dict(rule); rid=rule['id']; cond=rule['condition']
            thresh=rule['threshold']; cooldown=rule['cooldown_mins']*60
            triggered=False; msg=''; sev='warning'
            if cond=='offline' and result['status']=='offline':
                triggered=True; sev='critical'; msg=f'🔴 {hname} ({ip}) is OFFLINE'
            elif cond=='online' and result['status']=='online':
                triggered=True; sev='info'; msg=f'🟢 {hname} ({ip}) is back ONLINE'
            elif cond=='latency_gt' and result.get('latency') and result['latency']>thresh:
                triggered=True; msg=f'⚡ High latency on {hname} ({ip}): {result["latency"]:.1f}ms > {thresh}ms'
            elif cond=='loss_gt' and result['loss']>thresh:
                triggered=True; msg=f'📦 Packet loss on {hname} ({ip}): {result["loss"]:.1f}% > {thresh}%'
            elif cond=='jitter_gt' and result.get('jitter') and result['jitter']>thresh:
                triggered=True; msg=f'〰 Jitter on {hname} ({ip}): {result["jitter"]:.1f}ms > {thresh}ms'
            if not triggered: continue
            key=(host_id,rid)
            last=_astate.get(key)
            if last and (now-last).total_seconds()<cooldown: continue
            _astate[key]=now
            db_exec('INSERT INTO alerts(host_id,type,message,severity) VALUES(?,?,?,?)',(host_id,cond,msg,sev))
            db_exec('UPDATE alert_rules SET last_triggered=?,trigger_count=trigger_count+1 WHERE id=?',(now.isoformat(),rid))
            log.warning(f'ALERT [{sev}]: {msg}')
            em=rule.get('notify_email','')
            if em: threading.Thread(target=_send_email,args=(em,sev,hname,msg),daemon=True).start()
    except Exception as e:
        log.error(f'Alert error: {e}')

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
    except Exception as e:
        log.error(f'Email error: {e}')

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
    log.info(f'Monitor: {name} ({ip}) every {interval}s')
    while _running:
        try:
            result = ping(ip, pcount, timeout_ms)
            db_exec('INSERT INTO ping_results(host_id,status,latency_ms,packet_loss,jitter_ms,ttl) VALUES(?,?,?,?,?,?)',
                (host_id,result['status'],result.get('latency'),result['loss'],result.get('jitter'),result.get('ttl')))
            if not in_maintenance(host_id):
                fire_alerts(host_id, name, ip, result)
            if ports_str:
                for port in [int(p.strip()) for p in ports_str.split(',') if p.strip().isdigit()]:
                    pr=check_port(ip,port)
                    db_exec('INSERT INTO port_results(host_id,port,status,latency_ms) VALUES(?,?,?,?)',(host_id,port,pr['status'],pr.get('latency_ms')))
        except Exception as e:
            log.error(f'Monitor error {ip}: {e}')
        time.sleep(interval)
    close_thread_db()

def start_monitor(h):
    t = threading.Thread(
        target=monitor_host,
        args=(h['id'],h['ip'],h['name'] or h['ip'],h['ping_interval'],
              h['packet_count'],h.get('timeout_ms',1000),h.get('port_checks','')),
        daemon=True, name=f'mon-{h["ip"]}'
    )
    t.start(); _hthreads[h['id']]=t

def start_all():
    hosts = db_all('SELECT * FROM hosts WHERE enabled=1')
    for h in hosts: start_monitor(dict(h))
    log.info(f'Monitoring {len(hosts)} hosts')

def cleanup_loop():
    while True:
        time.sleep(3600)
        try:
            days=int(cfg('data_retention_days','30'))
            cutoff=(datetime.now()-timedelta(days=days)).isoformat()
            db_exec('DELETE FROM ping_results WHERE timestamp<?',(cutoff,))
            db_exec('DELETE FROM port_results WHERE timestamp<?',(cutoff,))
            db_exec('DELETE FROM alerts WHERE timestamp<? AND acknowledged=1',(cutoff,))
            db_exec('DELETE FROM sessions WHERE expires_at<?',(datetime.now().isoformat(),))
            log.info(f'Cleanup: {days}d retention applied')
        except Exception as e:
            log.error(f'Cleanup: {e}')
        close_thread_db()

# ── STATS ────────────────────────────────────────────────────────
def get_stats(host_id, hours):
    since=(datetime.now()-timedelta(hours=hours)).isoformat()
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

def get_report():
    hosts=db_all('SELECT * FROM hosts')
    out=[]
    for h in hosts:
        h=dict(h); hid=h['id']
        def up(d):
            s=(datetime.now()-timedelta(days=d)).isoformat()
            r=db_one('SELECT COUNT(*) t,SUM(CASE WHEN status="online" THEN 1 ELSE 0 END) u FROM ping_results WHERE host_id=? AND timestamp>?',(hid,s))
            return round((r[1] or 0)/(r[0] or 1)*100,3)
        inc=db_one('SELECT COUNT(*) FROM alerts WHERE host_id=? AND type="offline"',(hid,))[0]
        dwn=db_one("SELECT COUNT(*) FROM ping_results WHERE host_id=? AND status='offline' AND timestamp>datetime('now','-30 days')",(hid,))[0]
        last=db_one('SELECT status,latency_ms,timestamp FROM ping_results WHERE host_id=? ORDER BY timestamp DESC LIMIT 1',(hid,))
        out.append({'host_id':hid,'name':h['name'],'ip':h['ip'],'group':h['group_name'],'location':h.get('location',''),
            'uptime_1d':up(1),'uptime_7d':up(7),'uptime_30d':up(30),'incidents':inc,
            'downtime_mins':round(dwn*h['ping_interval']/60,1),
            'current_status':last['status'] if last else 'unknown',
            'current_latency':round(last['latency_ms'],2) if last and last['latency_ms'] else None,
            'last_check':last['timestamp'] if last else None})
    return out

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
    added=skipped=errors=0
    for h in data.get('hosts',[]):
        ip=h.get('ip','').strip()
        if not ip: errors+=1; continue
        try:
            if db_one('SELECT id FROM hosts WHERE ip=?',(ip,)):
                skipped+=1; continue
            db_exec('INSERT INTO hosts(ip,name,group_name,tags,description,location,alert_email,ping_interval,packet_count,timeout_ms,port_checks,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (ip,h.get('name',''),h.get('group_name','Default'),h.get('tags',''),h.get('description',''),
                 h.get('location',''),h.get('alert_email',''),int(h.get('ping_interval',30)),
                 int(h.get('packet_count',4)),int(h.get('timeout_ms',1000)),h.get('port_checks',''),h.get('notes','')))
            new=db_one('SELECT * FROM hosts WHERE ip=?',(ip,))
            if new: start_monitor(dict(new))
            added+=1
        except Exception as e:
            log.error(f'Import {ip}: {e}'); errors+=1
    return added,skipped,errors

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
    sname=platform.system().lower()
    try:
        cmd=(['tracert','-d','-h','20','-w','500',ip] if sname=='windows' else ['traceroute','-n','-m','20','-w','2',ip])
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
        return r.stdout or r.stderr or 'No output'
    except subprocess.TimeoutExpired: return 'Timed out'
    except Exception as e: return f'Error: {e}'

# ── HTTP HANDLER ─────────────────────────────────────────────────
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass

    def cors(self):
        self.send_header('Access-Control-Allow-Origin','*')
        self.send_header('Access-Control-Allow-Methods','GET,POST,PUT,DELETE,OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type,Authorization')

    def json(self, data, code=200):
        b=json.dumps(data,default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',len(b))
        self.cors(); self.end_headers(); self.wfile.write(b)

    def file_dl(self, data, mime, fname):
        if isinstance(data,str): data=data.encode()
        self.send_response(200)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Disposition',f'attachment; filename="{fname}"')
        self.send_header('Content-Length',len(data))
        self.cors(); self.end_headers(); self.wfile.write(data)

    def html(self, path):
        try:
            with open(path,'rb') as f: d=f.read()
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',len(d))
            self.end_headers(); self.wfile.write(d)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def body(self):
        n=int(self.headers.get('Content-Length',0))
        return json.loads(self.rfile.read(n)) if n else {}

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

        sess=auth(self)
        if not sess: return
        is_admin=sess['role']=='admin'

        try:
            # DASHBOARD
            if path=='/api/dashboard':
                total=db_one('SELECT COUNT(*) FROM hosts')[0]
                sts=[r[0] for r in db_all("SELECT (SELECT status FROM ping_results WHERE host_id=h.id ORDER BY timestamp DESC LIMIT 1) FROM hosts h")]
                online=sts.count('online'); offline=sts.count('offline')
                unack=db_one('SELECT COUNT(*) FROM alerts WHERE acknowledged=0')[0]
                avg_lat=db_one("SELECT ROUND(AVG(latency_ms),2) FROM ping_results WHERE timestamp>datetime('now','-1 hour') AND status='online'")[0]
                avg_loss=db_one("SELECT ROUND(AVG(packet_loss),2) FROM ping_results WHERE timestamp>datetime('now','-1 hour')")[0]
                degraded=db_one("SELECT COUNT(DISTINCT host_id) FROM ping_results WHERE timestamp>datetime('now','-5 minutes') AND packet_loss>5")[0]
                self.json({'total':total,'online':online,'offline':offline,'unknown':total-online-offline,
                    'unack_alerts':unack,'avg_latency_1h':avg_lat,'avg_loss_1h':avg_loss,'degraded':degraded}); return

            # HOSTS
            if path=='/api/hosts':
                hosts=[dict(h) for h in db_all('SELECT * FROM hosts ORDER BY group_name,name')]
                for h in hosts:
                    last=db_one('SELECT status,latency_ms,packet_loss,jitter_ms,ttl,timestamp FROM ping_results WHERE host_id=? ORDER BY timestamp DESC LIMIT 1',(h['id'],))
                    if last: h.update({'status':last['status'],'latency':last['latency_ms'],'loss':last['packet_loss'],'jitter':last['jitter_ms'],'ttl':last['ttl'],'last_check':last['timestamp']})
                    else: h.update({'status':'unknown','latency':None,'loss':None,'jitter':None,'ttl':None,'last_check':None})
                    up=db_one("SELECT CAST(SUM(CASE WHEN status='online' THEN 1 ELSE 0 END) AS REAL)/MAX(COUNT(*),1)*100 FROM ping_results WHERE host_id=? AND timestamp>datetime('now','-24 hours')",(h['id'],))[0]
                    h['uptime_24h']=round(up or 0,2)
                    h['in_maintenance']=in_maintenance(h['id'])
                self.json(hosts); return

            if path.startswith('/api/host/') and '/history' not in path and '/stats' not in path and '/ports' not in path:
                hid=int(path.split('/')[-1])
                h=dict(db_one('SELECT * FROM hosts WHERE id=?',(hid,)))
                last=db_one('SELECT status,latency_ms,packet_loss,jitter_ms,ttl,timestamp FROM ping_results WHERE host_id=? ORDER BY timestamp DESC LIMIT 1',(hid,))
                if last: h.update({'status':last['status'],'latency':last['latency_ms'],'loss':last['packet_loss'],'jitter':last['jitter_ms'],'ttl':last['ttl'],'last_check':last['timestamp']})
                h['in_maintenance']=in_maintenance(hid)
                self.json(h); return

            if '/history' in path:
                hid=int(path.split('/')[3]); hours=int(qp('hours','24'))
                since=(datetime.now()-timedelta(hours=hours)).isoformat()
                self.json([dict(r) for r in db_all('SELECT timestamp,status,latency_ms,packet_loss,jitter_ms,ttl FROM ping_results WHERE host_id=? AND timestamp>? ORDER BY timestamp ASC',(hid,since))]); return

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
                self.json({'last_24h':db_one("SELECT COUNT(*) FROM alerts WHERE timestamp>datetime('now','-24 hours')")[0],'last_7d':db_one("SELECT COUNT(*) FROM alerts WHERE timestamp>datetime('now','-7 days')")[0],'critical_unacked':db_one("SELECT COUNT(*) FROM alerts WHERE acknowledged=0 AND severity='critical'")[0]}); return

            # ALERT RULES
            if path=='/api/alert_rules':
                self.json([dict(r) for r in db_all('SELECT r.*,h.name host_name FROM alert_rules r LEFT JOIN hosts h ON r.host_id=h.id ORDER BY r.id')]); return

            # SETTINGS
            if path=='/api/settings':
                self.json({r['key']:r['value'] for r in db_all('SELECT key,value FROM settings')}); return

            # REPORT
            if path=='/api/report/uptime': self.json(get_report()); return
            if path=='/api/report/export':
                rows=get_report(); out=io.StringIO()
                w=csv.DictWriter(out,fieldnames=['name','ip','group','location','uptime_1d','uptime_7d','uptime_30d','incidents','downtime_mins','current_status','current_latency'])
                w.writeheader(); w.writerows(rows)
                self.file_dl(out.getvalue(),'text/csv','abayonet_report.csv'); return

            # HOST EXPORT
            if path=='/api/hosts/export/json':
                fname=f'abayonet_hosts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                self.file_dl(export_json(),'application/json',fname); return
            if path=='/api/hosts/export/csv':
                fname=f'abayonet_hosts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                self.file_dl(export_csv_hosts(),'text/csv',fname); return

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
        except Exception as e:
            log.error(f'GET {path}: {e}'); self.json({'error':str(e)},500)

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
                if 'abayonet_export' not in b:
                    self.json({'error':'Invalid file — must be AbayoNet JSON export'},400); return
                added,skipped,errors=import_json(b)
                self.json({'success':True,'added':added,'skipped':skipped,'errors':errors}); return

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
        except Exception as e:
            log.error(f'POST {path}: {e}'); self.json({'error':str(e)},500)

    def do_DELETE(self):
        path=urlparse(self.path).path
        sess=auth(self,admin=True)
        if not sess: return
        try:
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

def main():
    log.info(f'=== AbayoNet Enterprise v{VERSION} ===')
    init_db(); start_all()
    threading.Thread(target=cleanup_loop,daemon=True).start()
    PORT=8765
    for p in [8765,8766,8767,9000]:
        try: server=HTTPServer(('127.0.0.1',p),H); PORT=p; break
        except OSError: continue
    log.info(f'Dashboard → http://127.0.0.1:{PORT}')
    def _open():
        time.sleep(1.8); webbrowser.open(f'http://127.0.0.1:{PORT}')
    threading.Thread(target=_open,daemon=True).start()
    try: server.serve_forever()
    except KeyboardInterrupt:
        global _running; _running=False; log.info('AbayoNet stopped.')

if __name__=='__main__': main()
