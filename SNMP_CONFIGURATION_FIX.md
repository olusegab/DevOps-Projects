# SNMP Configuration Fix

## Issue
When editing a host and configuring SNMP settings (Enable SNMP Bandwidth Monitoring checkbox, SNMP Community, SNMP Port), clicking "Save Changes" appeared to save but the settings were not persisting in the database.

## Root Cause
The backend database had only `snmp_community` column but the UI was sending three fields:
- `snmp_enabled` (checkbox)
- `snmp_community` (text input)
- `snmp_port` (number input)

The host UPDATE and INSERT queries were missing these fields, so they were never saved to the database.

## Fix Applied

### 1. Database Schema
Added missing columns to `hosts` table:
```sql
ALTER TABLE hosts ADD COLUMN snmp_enabled TINYINT DEFAULT 0
ALTER TABLE hosts ADD COLUMN snmp_port INT DEFAULT 161
```

These columns are automatically added on service restart if they don't exist.

### 2. Host UPDATE Query (Edit Host)
**Before:**
```python
UPDATE hosts SET ip=?,name=?,group_name=?,tags=?,description=?,location=?,
                 alert_email=?,ping_interval=?,packet_count=?,timeout_ms=?,
                 port_checks=?,notes=? WHERE id=?
```

**After:**
```python
UPDATE hosts SET ip=?,name=?,group_name=?,tags=?,description=?,location=?,
                 alert_email=?,ping_interval=?,packet_count=?,timeout_ms=?,
                 port_checks=?,snmp_enabled=?,snmp_community=?,snmp_port=?,
                 notes=? WHERE id=?
```

### 3. Host INSERT Query (Add New Host)
**Before:**
```python
INSERT INTO hosts(ip,name,group_name,tags,description,location,alert_email,
                  ping_interval,packet_count,timeout_ms,port_checks,notes) 
VALUES(...)
```

**After:**
```python
INSERT INTO hosts(ip,name,group_name,tags,description,location,alert_email,
                  ping_interval,packet_count,timeout_ms,port_checks,
                  snmp_enabled,snmp_community,snmp_port,notes) 
VALUES(...)
```

### 4. Bulk Import
Updated bulk import query to include SNMP fields when importing hosts from JSON.

## How to Use SNMP Configuration

### Step 1: Enable SNMP on a Host
1. Click on a host in the dashboard
2. Click "Edit Host" button
3. Check ☑ **Enable SNMP Bandwidth Monitoring**
4. Enter SNMP Community (default: `public`)
5. Enter SNMP Port (default: `161`)
6. Click **Save Changes**

### Step 2: Discover Interfaces
After enabling SNMP and saving:
1. The host detail page will show a **Bandwidth (SNMP)** card
2. Click **⚙ Manage Interfaces** button
3. Click **🔄 Rediscover Interfaces** to query the device
4. Select which interfaces to monitor (check/uncheck boxes)
5. Click **Done**

### Step 3: View Bandwidth Data
- Bandwidth data appears after 2+ SNMP polls (60-120 seconds)
- Use the dropdown to select different interfaces
- Chart shows inbound/outbound traffic over time
- Stats show current utilization, speed, and totals

## Verification

To verify SNMP settings are saving:

### Method 1: Via UI
1. Edit a host and set SNMP settings
2. Click Save
3. Refresh the page
4. Edit the same host again
5. SNMP settings should still be there

### Method 2: Via Database
```bash
mysql -u abayonet -p'Legendary+1' abayonetDB -e "SELECT ip, name, snmp_enabled, snmp_community, snmp_port FROM hosts WHERE snmp_enabled=1;"
```

### Method 3: Via Log
Check that SNMP polling is working:
```bash
tail -f /opt/abayonet/data/abayonet.log | grep SNMP
```

## Database Columns

The `hosts` table now includes:

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `snmp_enabled` | TINYINT | 0 | 1 if SNMP monitoring enabled, 0 if disabled |
| `snmp_community` | VARCHAR(100) | 'public' | SNMP community string (usually "public" or "private") |
| `snmp_port` | INT | 161 | SNMP port number (standard is 161) |

## SNMP Requirements

For SNMP bandwidth monitoring to work, the target device must:

1. **Have SNMP enabled** - Enable SNMP service on the device
2. **Allow SNMP queries** - Configure firewall to allow UDP port 161
3. **Have correct community string** - Match the community string in AbayoNet
4. **Support IF-MIB** - Standard interface MIB for bandwidth data (most devices support this)

## Troubleshooting

### "No interfaces discovered yet"
- **Cause:** Device doesn't respond to SNMP queries
- **Fix:** 
  - Verify SNMP is enabled on device
  - Check firewall allows UDP port 161
  - Verify correct community string
  - Test with: `snmpwalk -v2c -c public <device-ip> system`

### "No bandwidth data yet"
- **Cause:** Need 2 polls to calculate rate
- **Fix:** Wait 60-120 seconds, data will appear automatically

### Settings not saving
- **Cause:** Old code without fix
- **Fix:** Applied - service restarted with updated queries

### SNMP checkbox unchecked after edit
- **Cause:** Missing snmp_enabled in UPDATE query
- **Fix:** Applied - field now saved correctly

## Test Devices

Common devices that work well with SNMP:
- **Routers:** Cisco, Mikrotik, Ubiquiti
- **Switches:** Cisco, HP, Netgear, Dell
- **Firewalls:** FortiGate, pfSense, Sophos
- **Servers:** Linux (net-snmp), Windows (SNMP Service)
- **Access Points:** Ubiquiti UniFi, Cisco

## Related Files Modified

- `/opt/abayonet/abayonet.py` - Backend database schema and queries
- Database: `hosts` table - Added columns

## Commits

- **0a2f27b** - Fix SNMP configuration not saving
- **757eb78** - Update HTTP mode warning to mention Security Settings UI
- **13c62dc** - Add Security Settings UI with HTTPS toggle

---

**Fixed:** 2026-10-22  
**Version:** AbayoNet 10.0  
**Status:** ✅ SNMP settings now save correctly
