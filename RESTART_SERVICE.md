# How to Restart AbayoNet Service

## The SNMP discovery fix is committed but requires a service restart

### Option 1: Via Terminal (Recommended)
```bash
sudo systemctl restart abayonet
```

Then check status:
```bash
sudo systemctl status abayonet
```

### Option 2: Kill and Let Systemd Restart
```bash
sudo pkill -f abayonet.py
```
Systemd will automatically restart it within a few seconds.

### Option 3: Via Web UI (If Available)
1. Login as Admin
2. Go to: Security Settings
3. Click: "🔄 Restart Service" (if you enabled then disabled HTTPS)

## After Restart

1. Go to WUSE II host detail page
2. Scroll to "Bandwidth (SNMP)" section
3. Click "🔄 Rediscover Interfaces"
4. You should see 13 interfaces discovered!
5. Click "⚙ Manage Interfaces"
6. Select which interfaces to monitor
7. Wait 60-120 seconds for bandwidth data

## Current Process PID
The old process is still running:
```
PID: 1069473 (started at 14:44)
```

You need to restart to apply the SNMP discovery fix.

## Verification
After restart, check logs:
```bash
tail -f /opt/abayonet/data/abayonet.log | grep SNMP
```

You should NOT see "noSuchName" errors anymore.
