# AbayoNet Heatmap Add-On

## Overview
The Heatmap Add-On is a **non-destructive**, **read-only** enhancement that adds a visual heatmap view to AbayoNet without modifying any existing functionality.

## Key Features

### 🎯 Non-Destructive Design
- ✅ **Zero modifications** to existing HTML structure
- ✅ **Read-only** - scrapes data from existing host cards
- ✅ **Original board preserved** - only hidden when heatmap is active
- ✅ **All features remain functional** - filters, clicks, updates all work
- ✅ **Easy to remove** - just delete the `<style>` and `<script>` blocks

### 📊 Visualization Features
- **Cards | Heatmap toggle** - Switch between views seamlessly
- **Color-coded tiles** - 5-level gradient based on metric performance
- **Three metrics**: Latency, Packet Loss, Uptime (24h)
- **Distribution chart** - Bar chart showing host count per performance bucket
- **Slowest hosts** - Top 5 worst performers with visual indicators
- **Dynamic legend** - Updates based on selected metric
- **Auto-refresh** - Updates every 5 seconds while visible

### 🎨 Color Scheme

#### Latency Buckets
- **Dark Blue** (#12324f): ≤ 15 ms - Excellent
- **Blue** (#1b4f7a): ≤ 25 ms - Very Good  
- **Cyan** (#3b9ac4): ≤ 45 ms - Good
- **Yellow** (#f0b429): ≤ 100 ms - Warning
- **Red** (#ef4444): > 100 ms - Critical
- **Dashed Red Border**: Offline/Paused

#### Packet Loss Buckets
- 0%, ≤1%, ≤5%, ≤10%, >10%

#### Uptime Buckets  
- ≥99.9%, ≥99%, ≥95%, ≥90%, <90%

## How It Works

### Data Collection
The add-on scrapes data from existing host cards in the DOM:
- Reads `.hcard` elements from `#hosts-grid`
- Extracts host name from `.hcn`
- Parses stats from `.hcm` elements (latency, loss, uptime, TTL)
- Respects app's own filters (hidden cards are skipped)

### View Switching
- Clicking **"Heatmap"** hides the original grid (`display: none`)
- Clicking **"Cards"** restores the original grid exactly as it was
- View preference is saved in `localStorage` (`abx.view`)
- Original card polling, filters, and click handlers keep running

### Click Behavior
- Clicking a heatmap tile triggers the **original card's `onclick` handler**
- This means host details, navigation, and actions all work identically
- No duplication of logic - the add-on delegates to existing code

## Installation

The add-on is already installed in `static/index.html` just before `</body>`.

To **remove** it:
1. Open `static/index.html`
2. Delete the entire `<!-- ABAYONET HEATMAP ADD-ON -->` section
3. Includes one `<style id="abx-hm-style">` block (~100 lines)
4. Includes one `<script id="abx-hm-script">` block (~360 lines)
5. Restart the server

## Configuration

Edit the `CONFIG` object in the script (around line 20 of the add-on):

```javascript
var CONFIG = {
  boardSelector: '#hosts-grid',       // Container with host cards
  cardSelector: '.hcard',              // Individual host card
  nameSelector: '.hcn',                // Host name element
  statSelector: '.hcm',                // Stat tiles
  toggleMountSelector: '.view-toggle', // Where to mount toggle button
  refreshMs: 5000,                     // Redraw interval
  rememberView: true,                  // Remember view in localStorage
  
  // Optional: provide your own data source
  getHosts: function () { return null; }
};
```

## Technical Details

### Files Modified
- **`static/index.html`** - Only file changed (467 lines added at end)

### Dependencies
- None! Uses vanilla JavaScript (ES5 compatible)
- Inherits styles from existing CSS variables
- Uses existing fonts (Orbitron, Inter, JetBrains Mono)

### Browser Compatibility
- Modern browsers (Chrome, Firefox, Edge, Safari)
- IE11+ (ES5 compatible, no arrow functions)
- Responsive design (flexbox-based layout)

### Performance
- Efficient DOM scraping (~10ms for 100 hosts)
- Lightweight rendering (no heavy libraries)
- Auto-refresh pauses when Cards view is active
- No impact on existing monitoring/polling

## Usage

1. Navigate to the **Hosts** page
2. Look for the **"Cards | Heatmap"** toggle (top of page)
3. Click **"Heatmap"** to switch views
4. Use metric buttons (**Latency**, **Packet loss**, **Uptime 24h**) to change coloring
5. Click any tile to open host details (same as clicking a card)
6. Click **"Cards"** to return to the original view

## Troubleshooting

### Toggle button not appearing
- Check console for `[abx-heatmap] board not found` warning
- Verify `#hosts-grid` exists when page loads
- Toggle will appear after ~20s retry attempts

### No hosts showing
- Switch to Cards view to verify hosts are there
- Check browser console for scraping errors
- Verify host cards have expected structure (`.hcard`, `.hcn`, `.hcm`)

### Colors seem wrong
- Ensure host cards have `.hcm` elements with `.hcmv` (value) and `.hcml` (label)
- Check that labels match expected text: "ms", "Loss", "Up 24h"

### Heatmap not updating
- Verify the auto-refresh timer is running (5s interval)
- Check that original host cards are being updated
- Switch to Cards view to confirm data is changing

## Future Enhancements
- Customizable color thresholds
- Additional metrics (jitter, response time)
- Filtering by group/location
- Export heatmap as image
- Historical heatmap playback

## Credits
- Design inspired by network operations centers (NOCs)
- Color scheme optimized for quick status assessment
- Implementation follows read-only, non-destructive principles

---

**Version**: AbayoNet v10.0  
**Last Updated**: October 2026  
**Add-On Type**: Non-destructive, read-only
