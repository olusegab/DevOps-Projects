# AbayoNet Security for NAT Port Forwarding Setup

## Your Current Setup

**Router/Firewall**: `Public IP:8081` → NAT forward → `Server:8081`

External users connect directly to AbayoNet on port 8081 without a reverse proxy.

---

## ✅ HTTPS Setup for Direct NAT Forwarding

### Option 1: Self-Signed Certificate (Quick Setup - Testing Only)

**⚠️ WARNING**: Self-signed certificates show browser warnings. Only use for testing or internal networks where you can distribute the certificate.

```bash
# Create SSL directory
cd /opt/abayonet
mkdir -p ssl

# Generate self-signed certificate (valid for 365 days)
openssl req -newkey rsa:2048 -nodes -keyout ssl/key.pem -x509 -days 365 -out ssl/cert.pem \
  -subj "/C=NG/ST=Lagos/L=Lagos/O=Your Company/CN=yourdomain.com"

# Set proper permissions
chmod 600 ssl/key.pem
chmod 644 ssl/cert.pem

# Restart AbayoNet
sudo systemctl restart abayonet
```

**Result**: AbayoNet will automatically detect the certificate and enable HTTPS.

---

### Option 2: Let's Encrypt Certificate (Production - RECOMMENDED)

Let's Encrypt provides **free, trusted SSL certificates** that work in all browsers without warnings.

#### Step 1: Install Certbot

```bash
sudo apt update
sudo apt install certbot -y
```

#### Step 2: Stop AbayoNet Temporarily

```bash
sudo systemctl stop abayonet
```

#### Step 3: Get Certificate (Standalone Mode)

Replace `yourdomain.com` with your actual domain:

```bash
sudo certbot certonly --standalone -d yourdomain.com --preferred-challenges http --http-01-port 8081
```

**Important**: 
- Your domain MUST point to your public IP
- Port 8081 must be open in your NAT forwarding during certificate generation
- Certbot will temporarily listen on port 8081 to verify domain ownership

#### Step 4: Copy Certificates to AbayoNet

```bash
# Copy certificates
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /opt/abayonet/ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /opt/abayonet/ssl/key.pem

# Set ownership
sudo chown $(whoami):$(whoami) /opt/abayonet/ssl/*.pem
chmod 600 /opt/abayonet/ssl/key.pem
chmod 644 /opt/abayonet/ssl/cert.pem
```

#### Step 5: Start AbayoNet

```bash
sudo systemctl start abayonet
```

#### Step 6: Verify HTTPS

Check logs:
```bash
tail -20 /opt/abayonet/data/abayonet.log
```

You should see:
```
✓ SSL/TLS enabled - HTTPS mode active
Dashboard → https://127.0.0.1:8081  (local)
Network   → https://192.168.x.x:8081  (LAN / remote)
```

#### Step 7: Auto-Renewal Setup

Let's Encrypt certificates expire every 90 days. Set up auto-renewal:

```bash
# Create renewal script
sudo nano /opt/abayonet/renew-cert.sh
```

Paste this content:
```bash
#!/bin/bash
# Renew Let's Encrypt certificate and reload AbayoNet

# Stop AbayoNet
systemctl stop abayonet

# Renew certificate
certbot renew --standalone --http-01-port 8081

# Copy new certificates
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /opt/abayonet/ssl/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /opt/abayonet/ssl/key.pem
chown $(stat -c '%U' /opt/abayonet/abayonet.py):$(stat -c '%G' /opt/abayonet/abayonet.py) /opt/abayonet/ssl/*.pem
chmod 600 /opt/abayonet/ssl/key.pem
chmod 644 /opt/abayonet/ssl/cert.pem

# Start AbayoNet
systemctl start abayonet

echo "Certificate renewed and AbayoNet restarted"
```

Make executable:
```bash
sudo chmod +x /opt/abayonet/renew-cert.sh
```

Add to crontab (runs monthly):
```bash
sudo crontab -e
```

Add this line:
```
0 3 1 * * /opt/abayonet/renew-cert.sh >> /opt/abayonet/data/cert-renewal.log 2>&1
```

---

### Option 3: Commercial SSL Certificate

If you purchased a commercial SSL certificate:

1. **Get the certificate files** from your provider:
   - Certificate file (usually `.crt` or `.pem`)
   - Private key file (usually `.key` or `.pem`)
   - Intermediate/chain certificates (if provided)

2. **Combine if needed**:
```bash
# If you have separate certificate and chain files
cat your-cert.crt intermediate.crt > /opt/abayonet/ssl/cert.pem
cp your-private.key /opt/abayonet/ssl/key.pem
```

3. **Set permissions and restart**:
```bash
chmod 600 /opt/abayonet/ssl/key.pem
chmod 644 /opt/abayonet/ssl/cert.pem
sudo systemctl restart abayonet
```

---

## 🔧 NAT Port Forwarding Configuration

### Router/Firewall Settings

Configure your router to forward:

**External**: `Public_IP:443` → **Internal**: `Server_IP:8081`

**Why port 443?**
- Standard HTTPS port (users don't need to type `:8081`)
- Less likely to be blocked by corporate firewalls
- Professional appearance

**Example configurations:**

**pfSense/OPNsense:**
```
Interface: WAN
Protocol: TCP
Destination: WAN address
Destination port: 443
Redirect target IP: 192.168.x.x (your server)
Redirect target port: 8081
Description: AbayoNet HTTPS
```

**MikroTik:**
```
/ip firewall nat
add chain=dstnat action=dst-nat to-addresses=192.168.x.x to-ports=8081 \
    protocol=tcp dst-port=443 in-interface=ether1
```

**iptables (Linux firewall):**
```bash
iptables -t nat -A PREROUTING -p tcp --dport 443 -j DNAT --to-destination 192.168.x.x:8081
iptables -t nat -A POSTROUTING -j MASQUERADE
```

### Firewall Rules

Allow incoming HTTPS on WAN:
```bash
# Allow port 443 from internet
sudo ufw allow 443/tcp comment 'AbayoNet HTTPS'

# Block direct access to 8081 from internet (optional extra security)
# Allow only from local network
sudo ufw allow from 192.168.0.0/16 to any port 8081
sudo ufw allow from 172.16.0.0/12 to any port 8081
sudo ufw allow from 10.0.0.0/8 to any port 8081

# Enable firewall
sudo ufw enable
```

---

## 🧪 Testing Your Setup

### 1. Test Locally First

```bash
# Check if HTTPS is working locally
curl -k https://localhost:8081/api/version

# Expected output:
# {"version":"10.0","uptime":123}
```

### 2. Test from LAN

```bash
# From another computer on your network
curl -k https://192.168.x.x:8081/api/version
```

### 3. Test from Internet

```bash
# From your phone (disconnect from WiFi) or external server
curl https://yourdomain.com/api/version

# Or open in browser:
https://yourdomain.com
```

### 4. Check SSL Certificate

```bash
# Test SSL certificate validity
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com

# Should show certificate details
```

### 5. Verify in Browser

Open `https://yourdomain.com` and:
- ✅ Should show padlock icon (🔒) in address bar
- ✅ No certificate warnings (if using Let's Encrypt or commercial cert)
- ✅ Click padlock → Should show "Connection is secure"

---

## 📊 SSL/TLS Security Test

After setup, test your SSL configuration:

1. **SSL Labs Test** (comprehensive):
   https://www.ssllabs.com/ssltest/analyze.html?d=yourdomain.com

2. **Quick Security Check**:
```bash
nmap --script ssl-enum-ciphers -p 8081 yourdomain.com
```

**Target Grade**: A or A+ on SSL Labs

---

## 🔍 Troubleshooting

### Certificate Not Loading

**Check logs:**
```bash
tail -50 /opt/abayonet/data/abayonet.log | grep -i ssl
```

**Common issues:**

1. **"SSL certificate found but could not be loaded"**
   - Check file permissions: `ls -la /opt/abayonet/ssl/`
   - Verify certificate format: `openssl x509 -in ssl/cert.pem -text -noout`
   - Check private key: `openssl rsa -in ssl/key.pem -check`

2. **"Certificate and private key do not match"**
```bash
# Check if cert and key match
openssl x509 -noout -modulus -in ssl/cert.pem | openssl md5
openssl rsa -noout -modulus -in ssl/key.pem | openssl md5
# Output should be identical
```

3. **Certificate expired**
```bash
# Check expiration
openssl x509 -in ssl/cert.pem -noout -dates
```

4. **Browser shows "Not Secure"**
   - Using self-signed certificate? Expected behavior
   - Certificate not trusted? Install CA certificate in browser
   - Mixed content? Check browser console for HTTP resources on HTTPS page

### Port Not Accessible from Internet

1. **Check NAT forwarding** in router admin panel
2. **Test port forwarding**:
```bash
# From external server or phone
nc -zv your-public-ip 443
```
3. **Check firewall rules**:
```bash
sudo ufw status numbered
```

### Performance Issues

1. **SSL handshake slow?** 
   - Normal for first connection
   - Consider HTTP/2 upgrade (requires newer Python)

2. **High CPU usage?**
   - SSL encryption is CPU-intensive
   - Monitor with: `top` or `htop`

---

## 🚨 Security Best Practices

### 1. Keep Certificates Secure

```bash
# Restrict access to private key
chmod 600 /opt/abayonet/ssl/key.pem
chown root:root /opt/abayonet/ssl/key.pem  # Or service user
```

### 2. Monitor Certificate Expiration

Add to your monitoring:
```bash
# Check days until expiration
openssl x509 -in /opt/abayonet/ssl/cert.pem -noout -enddate

# Alert when < 30 days
DAYS_LEFT=$(( ($(date -d "$(openssl x509 -in /opt/abayonet/ssl/cert.pem -noout -enddate | cut -d= -f2)" +%s) - $(date +%s)) / 86400 ))
if [ $DAYS_LEFT -lt 30 ]; then
    echo "WARNING: SSL certificate expires in $DAYS_LEFT days!"
fi
```

### 3. Use Strong Passwords

With HTTPS enabled, you're still vulnerable if passwords are weak:
- Minimum 12 characters (enforced: 8)
- Use password manager
- Enable 2FA if implementing in future

### 4. Regular Security Audits

```bash
# Check audit log weekly
tail -500 /opt/abayonet/data/abayonet.log | grep "AUDIT:"

# Check for failed logins
grep "login_failed" /opt/abayonet/data/abayonet.log | tail -50
```

### 5. Backup SSL Certificates

```bash
# Backup certificates
tar -czf ssl-backup-$(date +%Y%m%d).tar.gz /opt/abayonet/ssl/
```

---

## 📋 Quick Setup Checklist

For Let's Encrypt certificate:

- [ ] Domain name pointing to public IP
- [ ] Port 8081 open in NAT forwarding temporarily
- [ ] AbayoNet stopped during certificate generation
- [ ] Certbot installed
- [ ] Certificate generated successfully
- [ ] Certificates copied to `/opt/abayonet/ssl/`
- [ ] Permissions set correctly (600 for key, 644 for cert)
- [ ] AbayoNet restarted
- [ ] HTTPS confirmed in logs
- [ ] NAT forwarding changed to 443 → 8081
- [ ] Tested from external network
- [ ] Auto-renewal script created
- [ ] Cron job scheduled

---

## 🆘 Emergency HTTP Fallback

If HTTPS causes issues and you need to temporarily disable:

```bash
# Move certificates out of the way
sudo mv /opt/abayonet/ssl /opt/abayonet/ssl.backup

# Restart AbayoNet (will run in HTTP mode)
sudo systemctl restart abayonet

# Access via HTTP
http://yourdomain.com:8081
```

⚠️ **Do not use HTTP mode for internet access in production!**

---

## 📞 Support

- **HTTPS not working?** Check `/opt/abayonet/data/abayonet.log`
- **Certificate errors?** Run: `openssl x509 -in ssl/cert.pem -text -noout`
- **Need help?** Include log output from: `tail -100 /opt/abayonet/data/abayonet.log`

---

**Last Updated**: October 2026
**Tested with**: Ubuntu 20.04/22.04, Debian 11/12, CentOS/Rocky Linux 8+
