# AbayoNet Security Quick Start

## 🚨 BEFORE External Access - CRITICAL STEPS

### 1. Enable HTTPS (MANDATORY for internet access)
```bash
# Install nginx and certbot
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx -y

# Get free SSL certificate
sudo certbot --nginx -d yourdomain.com

# Configure nginx (see full config in SECURITY.md)
sudo nano /etc/nginx/sites-available/abayonet

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
```

### 2. Change Default Admin Password
```bash
# Login to AbayoNet web interface
# Go to: User Menu → Change Password
# Use strong password:
#   - Minimum 8 characters (recommend 12+)
#   - Must contain letters AND numbers
#   - Mix uppercase and lowercase
```

### 3. Configure Firewall
```bash
# Allow HTTPS from internet
sudo ufw allow 443/tcp

# Block direct access to AbayoNet port from internet
sudo ufw deny from any to any port 8081 proto tcp

# Allow local network access
sudo ufw allow from 192.168.0.0/16 to any port 8081 proto tcp
sudo ufw allow from 172.16.0.0/12 to any port 8081 proto tcp

# Enable firewall
sudo ufw enable
```

### 4. Create ReadOnly Users
```bash
# In AbayoNet web interface:
# Admin Menu → User Management → Add User
# Set Role: "ReadOnly" for monitoring-only staff
```

## 🔒 Security Features Active

### Rate Limiting
- **Login**: 5 attempts per IP, then 15-minute lockout
- **API**: 120 requests per minute per IP

### Audit Logging
All security events logged:
- Login/logout attempts
- User changes
- Host modifications
- Permission changes

View logs: Admin Menu → System → Audit Log

### Password Requirements
- Minimum 8 characters
- Must contain letters
- Must contain numbers

### ReadOnly Users Cannot
- Add/edit/delete hosts
- Change settings
- Create users
- Access admin features

## 📊 Quick Security Check

```bash
# Check AbayoNet is running
sudo systemctl status abayonet

# View recent security events
tail -50 /opt/abayonet/data/abayonet.log | grep "AUDIT:"

# Check for failed logins
tail -100 /opt/abayonet/data/abayonet.log | grep "Failed login"

# Monitor in real-time
tail -f /opt/abayonet/data/abayonet.log | grep -E "(AUDIT:|Failed login|Rate limited)"
```

## ⚙️ Configuration Files

### AbayoNet Config
```
/opt/abayonet/abayonet.py         # Main application
/opt/abayonet/abayonet.cfg        # Database config
/opt/abayonet/data/abayonet.log   # Log file
```

### Security Settings (in abayonet.py)
```python
MAX_LOGIN_ATTEMPTS = 5          # Change if needed
LOGIN_LOCKOUT_MINUTES = 15      # Change if needed
MAX_REQUESTS_PER_MINUTE = 120   # Change if needed
```

## 🆘 Emergency Response

### If you suspect unauthorized access:

1. **Immediate Actions**:
```bash
# Stop AbayoNet
sudo systemctl stop abayonet

# Check audit logs
grep "AUDIT:" /opt/abayonet/data/abayonet.log | tail -100

# Review recent database changes
mysql -u abayonet -p abayonetDB
# Then run:
# SELECT * FROM users ORDER BY id DESC LIMIT 10;
# SELECT * FROM hosts ORDER BY id DESC LIMIT 20;
```

2. **After Investigation**:
```bash
# Clear all sessions (forces everyone to re-login)
mysql -u abayonet -p abayonetDB -e "DELETE FROM sessions;"

# Change admin password immediately
# (via web interface: User Menu → Change Password)

# Restart AbayoNet
sudo systemctl start abayonet
```

3. **Long-term**:
- Review and rotate all passwords
- Check firewall rules
- Enable IP whitelisting
- Review user accounts
- Update security procedures

## 📞 Quick Commands Reference

```bash
# Restart AbayoNet
sudo systemctl restart abayonet

# View logs
tail -f /opt/abayonet/data/abayonet.log

# Check service status
sudo systemctl status abayonet

# Test HTTPS
curl -I https://yourdomain.com

# Check open ports
sudo netstat -tlnp | grep -E "(8081|443)"

# View active sessions
mysql -u abayonet -p abayonetDB -e "SELECT username, ip, expires_at FROM sessions;"
```

## ✅ Deployment Checklist

Basic Setup:
- [ ] HTTPS configured and tested
- [ ] Admin password changed
- [ ] Firewall rules active
- [ ] At least one ReadOnly user created

Production Ready:
- [ ] SSL certificate valid and auto-renewing
- [ ] Nginx reverse proxy configured
- [ ] IP whitelisting enabled (if applicable)
- [ ] Backup schedule established
- [ ] Monitoring setup for audit logs
- [ ] Team trained on ReadOnly vs Admin roles
- [ ] Incident response plan documented
- [ ] Regular security audit schedule

## 🔗 Full Documentation

For complete security information, see:
- `/opt/abayonet/SECURITY.md` - Comprehensive security guide
- `/opt/abayonet/README.md` - General documentation

---

**Emergency Contact**: [Your IT Security Contact]
**Last Updated**: October 9, 2026
