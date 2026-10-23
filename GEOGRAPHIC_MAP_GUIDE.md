# Geographic Map Feature

## Overview

The Geographic Map provides a visual overview of your network infrastructure across Nigerian cities, showing host distribution and health status at a glance.

## How to Access

1. Click **🗺 Geographic Map** in the sidebar navigation
2. View the schematic map of Nigeria with city bubbles

## Features

### Interactive Map
- **City Bubbles**: Size represents number of hosts
- **Color Coding**:
  - 🟢 **Green**: All hosts healthy
  - 🟠 **Orange**: Some hosts degraded (high latency/packet loss)
  - 🔴 **Red**: Some hosts offline
- **Click on any city** to view detailed host list

### Right Sidebar
- **Selected City Details**: Shows all hosts in clicked city with status
- **Sites by Severity**: Lists all cities sorted by health status

### Supported Cities

The map currently recognizes these Nigerian cities:
- **Lagos** (and suburbs: Lekki, Ikeja, Yaba, Victoria Island, etc.)
- **Abeokuta**
- **Ibadan**
- **Akure**
- **Benin City**
- **Asaba**
- **Awka**
- **Aba**
- **Calabar**
- **Port Harcourt**
- **Abuja** (and Wuse, Gwarimpa, Kubwa)
- **Kaduna**
- **Kano**
- **Jos**
- **Minna**
- **Yenagoa**

## City Detection

The system determines city location using:
1. **Location field** (if populated)
2. **Host name parsing** - Automatically detects city names in host names

### Examples:
- Host: "BODE THOMAS (COOLLINK)" → Detected as: Lagos
- Host: "WUSE II" → Detected as: Abuja
- Host: "AKURE MALL" → Detected as: Akure
- Location: "Lagos, Nigeria" → Detected as: Lagos

## Updating Host Locations

To ensure accurate city mapping:

### Method 1: Via Location Field
1. Go to **All Hosts** page
2. Click on a host
3. Click **Edit Host**
4. Enter city name in **Location** field
5. Save changes

### Method 2: Bulk Update
```sql
-- Example: Update multiple hosts to Lagos
UPDATE hosts SET location='Lagos' WHERE name LIKE '%LAGOS%';

-- Update to Abuja
UPDATE hosts SET location='Abuja' WHERE name LIKE '%WUSE%' OR name LIKE '%ABUJA%';
```

## Technical Details

### How It Works
- Uses HTML5 Canvas for rendering
- City coordinates are approximate (schematic view)
- Real-time status updates from host monitoring
- Fully responsive to window resizing
- Click detection using circular hit regions

### Status Determination
- **Offline**: Host status = 'offline'
- **Degraded**: Latency > 200ms OR Packet Loss > 10%
- **Healthy**: All other hosts

### Performance
- Lightweight canvas rendering
- No external dependencies
- Updates automatically when hosts change

## Troubleshooting

### City not showing on map
- Check host **Location** field contains valid city name
- Or ensure host name contains recognizable city name
- Supported cities must match list above

### Hosts showing as "Unknown"
- Location field is empty/invalid
- Host name doesn't contain recognizable city name
- **Solution**: Update location field manually

### Wrong city assignment
- Host name parsing may misidentify location
- **Solution**: Set explicit location field value

## Future Enhancements

Possible additions:
- **Real map overlay** using Leaflet/Google Maps
- **GPS coordinates** for exact positioning
- **Custom city definitions** via settings
- **Traffic flow visualization** between cities
- **Regional grouping** (South-West, North-Central, etc.)

## Comparing with Dashboard

| Feature | Dashboard (Cards) | Geographic Map |
|---------|------------------|----------------|
| View | List of all hosts | Visual city grouping |
| Best for | Detailed monitoring | Overview & distribution |
| Interaction | Click host for details | Click city for host list |
| Status | Individual hosts | City-level aggregation |

Both views complement each other - use Dashboard for detailed monitoring, Geographic Map for network overview.

---

**Added:** 2026-10-22  
**Status:** ✅ Active  
**No existing functionality disrupted**
