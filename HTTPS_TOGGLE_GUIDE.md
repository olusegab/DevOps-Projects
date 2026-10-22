# HTTPS Toggle Guide

## Quick Overview

AbayoNet now includes a **Security Settings** page where admins can easily toggle HTTPS on/off without manual file operations or command-line work.

## Current Status

**HTTP Mode Active** - The application is currently running in HTTP mode (not encrypted).

- URL: `http://192.168.0.245:8081` or `http://197.234.39.74:8081`
- SSL certificates exist but are disabled (`/opt/abayonet/ssl.disabled/`)
- All security features (rate limiting, audit logging, password requirements, etc.) are active

## How to Toggle HTTPS

### Via Web UI (Recommended)

1. **Login as Admin**
2. **Navigate to:** Admin Menu → 🔒 Security Settings
3. **Click:** "🔒 Enable HTTPS" button
4. **Wait for confirmation message**
5. **Click:** "🔄 Restart Service" button (or manually restart)
6. **Browser will show certificate warning** - Click "Advanced" → "Proceed" (expected with self-signed certs)

### Via Command Line (Alternative)

```bash
# Enable HTTPS
cd /opt/abayonet
sudo mv ssl.disabled ssl
sudo systemctl restart abayonet

# Disable HTTPS  
cd /opt/abayonet
sudo mv ssl ssl.disabled
sudo systemctl restart abayonet
```

## What Happens When HTTPS is Enabled

1. Service loads SSL certificates from `/opt/abayonet/ssl/`
2. Server starts accepting HTTPS connections on port 8081
3. All traffic is encrypted with TLS 1.2+
4. Browsers show warning for self-signed certificates (users must accept)
5. HTTP connections will fail - only HTTPS works

## What Happens When HTTPS is Disabled

1. Service runs in standard HTTP mode (no encryption)
2. Port 8081 accepts unencrypted HTTP traffic
3. No browser certificate warnings
4. All security features still active (rate limiting, audit logs, etc.)

## Browser Certificate Warnings

When HTTPS is enabled with self-signed certificates:

- **Chrome/Edge:** "Your connection is not private" → Click "Advanced" → "Proceed to..."
- **Firefox:** "Warning: Potential Security Risk" → Click "Advanced" → "Accept the Risk and Continue"
- **Safari:** "This Connection is Not Private" → Click "Show Details" → "visit this website"

This is **expected and normal** for self-signed certificates. To eliminate warnings, you would need:
- A valid domain name (not just IP address)
- Let's Encrypt certificate (requires domain)
- Commercial SSL certificate

## SSL Certificate Information

**Current Certificates:**
- Location: `/opt/abayonet/ssl.disabled/` (disabled) or `/opt/abayonet/ssl/` (enabled)
- Type: Self-signed
- Valid for: 365 days
- Generated on: 2026-10-22

**Regenerate Certificates:**
```bash
cd /opt/abayonet
./setup-https.sh
# Select option 1 (Self-signed)
```

## Troubleshooting

### HTTPS Connection Timeout
- Check firewall: `sudo ufw status`
- Verify port 8081 is open for HTTPS
- Check NAT forwarding includes port 8081
- Review logs: `tail -50 /opt/abayonet/data/abayonet.log`

### Browser Shows "Connection Refused"
- Service may not have restarted: `sudo systemctl restart abayonet`
- Wrong protocol: Use `https://` not `http://`
- Check service status: `sudo systemctl status abayonet`

### Certificate Errors Persist
- Clear browser cache and SSL state
- Try incognito/private browsing mode
- Regenerate certificates with `./setup-https.sh`

## Security Notes

- **HTTP mode** (current): Not suitable for external access - traffic is unencrypted
- **HTTPS mode** (when enabled): Suitable for external access - traffic is encrypted
- Self-signed certificates provide encryption but no identity verification
- All other security features (rate limiting, audit logs, password requirements, ReadOnly enforcement) work in both modes

## Audit Trail

HTTPS toggle operations are logged in the Audit Log:
- Event Type: `https_toggled`
- Details include: username, IP address, enable/disable action
- View in: Admin Menu → 📋 Audit Log

## For Production Use

For production external access, we recommend:
1. **Keep HTTPS disabled** until the connection timeout issue is fully resolved
2. **Use HTTP mode** for now (current setup)
3. **All security features are active** even in HTTP mode
4. When HTTPS is working reliably, enable it via Security Settings page

## Next Steps

When you're ready to try HTTPS again:
1. Go to Security Settings page
2. Click "Enable HTTPS"
3. Restart service
4. Test from browser using `https://192.168.0.245:8081`
5. If it times out, disable again via Security Settings

---

**Last Updated:** 2026-10-22  
**AbayoNet Version:** 10.0  
**Status:** HTTP Mode Active, SSL Disabled
