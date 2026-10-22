# SNMP Bandwidth Monitoring Status

## Current Status: ⚠️ Needs Service Restart

### What's Fixed
✅ SNMP interface discovery working (tested successfully)
✅ SNMP bandwidth counter retrieval working (tested successfully)  
✅ Code updated to check `snmp_enabled=1` flag properly
✅ 13 interfaces discovered and marked as monitored for WUSE II

### What's Pending
⚠️ **Service restart required** to apply the snmp_enabled fix

### The Issue
The bandwidth monitoring loop wasn't collecting data because:
1. Old code checked: `snmp_community IS NOT NULL`
2. New code checks: `snmp_enabled=1 AND monitored=1`
3. Current running process (PID 1189259) has old code
4. Service restart needed to load new code

### Test Results

**SNMP Discovery Test:**
```bash
$ python3 test_snmp.py 197.234.48.142 abayonet
✅ 13 interfaces discovered successfully
```

**Bandwidth Counter Test:**
```bash
$ python3 test_bandwidth.py 197.234.48.142 2 abayonet
✅ ifInOctets: 2,718,854,253
✅ ifOutOctets: 1,719,555,717
```

### Next Steps

1. **Restart the service:**
   ```bash
   sudo systemctl restart abayonet
   ```

2. **Wait 5-10 minutes** for bandwidth data collection:
   - First poll: Collects initial counters (no data yet)
   - Second poll (after 5 min): Calculates bandwidth rate → DATA APPEARS!

3. **Check if data is being collected:**
   ```bash
   mysql -u abayonet -p'Legendary+1' abayonetDB -e \
     "SELECT COUNT(*) as samples FROM bandwidth_results WHERE host_id=85;"
   ```

4. **View bandwidth data:**
   - Refresh WUSE II host page
   - Bandwidth graph should show data after 2nd poll

### How Bandwidth Monitoring Works

```
Time 00:00 - First poll:  in=1000, out=500  (stored in memory)
Time 05:00 - Second poll: in=1500, out=700  (calculate rate)
            Rate = (1500-1000) * 8 / 300s = 13.3 bps
            → Store in database
            → Graph shows data!
```

### Bandwidth Monitoring Schedule

- **Poll Interval:** Every 5 minutes (300 seconds)
- **Minimum Wait:** 5 minutes for first rate calculation
- **Data Retention:** Configurable (default: keep recent data)

### Database Query

The bandwidth monitoring loop now executes:
```sql
SELECT DISTINCT h.id, h.ip, h.snmp_community, h.snmp_port
FROM hosts h
JOIN interfaces i ON h.id = i.host_id
WHERE h.enabled=1 
  AND h.snmp_enabled=1   ← THIS WAS THE FIX!
  AND i.monitored=1
```

### Current SNMP-Enabled Hosts

```
ID  | IP              | Name      | Interfaces
----|-----------------|-----------|------------
4   | 102.222.118.238 | ABA       | 14 (3 monitored)
85  | 197.234.48.142  | WUSE II   | 13 (13 monitored)
88  | 197.234.39.74   | CSU-FIBER | 5+ discovered
```

### Troubleshooting

**If graph still shows "No bandwidth data"** after 10 minutes:

1. Check logs for errors:
   ```bash
   tail -50 /opt/abayonet/data/abayonet.log | grep -i "snmp\|bandwidth"
   ```

2. Check if data is in database:
   ```bash
   mysql -u abayonet -p'Legendary+1' abayonetDB -e \
     "SELECT * FROM bandwidth_results WHERE host_id=85 LIMIT 5;"
   ```

3. Verify SNMP is responding:
   ```bash
   python3 test_bandwidth.py 197.234.48.142 2 abayonet
   ```

4. Check monitoring loop is running:
   ```bash
   ps aux | grep abayonet | grep -v grep
   tail -f /opt/abayonet/data/abayonet.log
   ```

### Files Modified

- `abayonet.py` - Fixed bandwidth monitoring query
- `test_snmp.py` - Test script for interface discovery
- `test_bandwidth.py` - Test script for bandwidth counters

### Commits

- **ae90804** - Fix SNMP bandwidth monitoring to check snmp_enabled flag
- **31d71c6** - Fix SNMP interface discovery noSuchName error
- **0a2f27b** - Fix SNMP configuration not saving

---

**Current Process:** PID 1189259, started 15:12 UTC  
**Last Updated:** 2026-10-22 15:18 UTC  
**Action Required:** Restart service to load new code
