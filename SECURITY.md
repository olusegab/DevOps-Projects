# AbayoNet Security Guide

## Overview
AbayoNet v10.0 includes comprehensive security features designed for safe external access via NAT forwarding.

## Security Features Implemented

### 1. Authentication & Authorization
- **Session-based authentication** with secure tokens
- **Role-based access control** (Admin / ReadOnly)
- **Session timeout**: 24 hours of inactivity
- **Secure password hashing**: SHA-256 with salt

### 2. Rate Limiting
- **Login attempts**: Max 5 failed attempts per IP, 15-minute lockout
- **General API requests**: Max 120 requests/minute per IP
- **Automatic IP blocking** for repeated violations

### 3. Password Security
- **Minimum length**: 8 characters
- **Complexity requirements**: Must contain letters AND numbers
- **Password strength validation** on all password operations
- **Forced logout** on password reset

### 4. Input Validation
- **IP address validation**: Proper format checking
- **Email validation**: RFC-compliant format
- **Input sanitization**: Removal of control characters, length limits
- **SQL injection protection**: Parameterized queries throughout

### 5. Audit Logging
- **Comprehensive logging** of security events:
  - Login/logout attempts (success and failure)
  - User creation/modification
  - Host addition/deletion
  - Configuration changes
  - Password changes
- **Last 1000 events** kept in memory
- **Accessible via API**: `/api/admin/audit` (admin only)

### 6. Security Headers
- **X-Content-Type-Options**: nosniff
- **X-Frame-Options**: DENY (prevents clickjacking)
- **X-XSS-Protection**: Enabled
- **Content-Security-Policy**: Restrictive CSP to prevent XSS
- **Referrer-Policy**: strict-origin-when-cross-origin

### 7. ReadOnly User Restrictions
ReadOnly users can:
- ✅ View dashboard and all monitoring data
- ✅ View host details and history
- ✅ View alerts
- ✅ Acknowledge alerts
- ✅ Run "Ping Now" tests
- ✅ Generate and view reports
- ✅ Change their own password

ReadOnly users CANNOT:
- ❌ Add, edit, or delete hosts
- ❌ Toggle host monitoring
- ❌ Import/export hosts
- ❌ Scan subnets
- ❌ Create or modify alert rules
- ❌ Change system settings
- ❌ Create or manage users
- ❌ Access admin dashboard
- ❌ Trigger manual cleanup
- ❌ Discover SNMP interfaces
- ❌ Toggle interface monitoring

## Deployment Best Practices

### For External Access (NAT Forwarding)

#### 1. HTTPS/TLS is MANDATORY
**WARNING**: AbayoNet runs on HTTP by default. For external access, you MUST use HTTPS.

**Recommended Setup**:
```bash
# Option A: Use a reverse proxy (RECOMMENDED)
# Install nginx
sudo apt install nginx

# Configure nginx as reverse proxy with SSL
# See example configuration below
```

**Example nginx configuration** (`/etc/nginx/sites-available/abayonet`):
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
    limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/auth/login {
        limit_req zone=login burst=3 nodelay;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

#### 2. Firewall Configuration
```bash
# Allow only HTTPS from internet
sudo ufw allow from any to any port 443 proto tcp

# Block direct access to AbayoNet port from internet
sudo ufw deny from any to any port 8081 proto tcp

# Allow local access
sudo ufw allow from 192.168.0.0/16 to any port 8081 proto tcp
```

#### 3. IP Whitelisting (Optional but Recommended)
```bash
# In nginx, allow only specific IPs
location / {
    allow 1.2.3.4;        # Your office IP
    allow 5.6.7.8;        # Your home IP
    deny all;
    proxy_pass http://127.0.0.1:8081;
}
```

#### 4. Strong Password Policy
- **Change default admin password immediately**:
  ```bash
  # First login, go to User Management → Change Password
  # Use password with:
  # - Minimum 12 characters (recommended)
  # - Mix of uppercase, lowercase, numbers, symbols
  # - Not based on dictionary words
  ```

#### 5. Regular Security Audits
```bash
# Check audit logs regularly
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-domain.com/api/admin/audit?limit=100

# Monitor failed login attempts
tail -f /opt/abayonet/data/abayonet.log | grep "Failed login"

# Check for locked IPs
# (visible in Admin System Dashboard)
```

#### 6. User Management
- **Create separate accounts** for each user
- **Use ReadOnly role** for monitoring-only users
- **Never share admin credentials**
- **Regularly review active sessions**
- **Deactivate users** who no longer need access

#### 7. Network Segmentation
- Run AbayoNet on a **management VLAN**
- Restrict access to monitoring subnets
- Use **firewall rules** between zones

#### 8. Monitoring Security Events
```bash
# Watch for suspicious activity
tail -f /opt/abayonet/data/abayonet.log | grep -i "AUDIT:"

# Common security events to monitor:
# - Multiple failed logins from same IP
# - Login from unusual IPs/locations
# - User permission changes
# - Bulk host deletions
# - Unusual API activity patterns
```

## Security Checklist for External Deployment

- [ ] HTTPS/TLS configured with valid certificate
- [ ] Default admin password changed to strong password
- [ ] Firewall rules configured (block direct access to port 8081)
- [ ] Reverse proxy (nginx/Apache) configured
- [ ] IP whitelisting enabled (if applicable)
- [ ] ReadOnly users created for non-admin staff
- [ ] Regular backup schedule established
- [ ] Audit log monitoring configured
- [ ] Session timeout appropriate for your use case
- [ ] Rate limiting tested and working
- [ ] All passwords meet complexity requirements
- [ ] SSL/TLS grade A on SSL Labs test
- [ ] Security headers verified (securityheaders.com)

## API Endpoints Security Matrix

| Endpoint | Admin | ReadOnly | Public | Rate Limited |
|----------|-------|----------|--------|--------------|
| `/api/auth/login` | ✅ | ✅ | ✅ | Yes (5/min) |
| `/api/auth/logout` | ✅ | ✅ | ❌ | Yes |
| `/api/hosts` (GET) | ✅ | ✅ | ❌ | Yes |
| `/api/hosts` (POST) | ✅ | ❌ | ❌ | Yes |
| `/api/hosts/:id` (PUT) | ✅ | ❌ | ❌ | Yes |
| `/api/hosts/bulk_delete` | ✅ | ❌ | ❌ | Yes |
| `/api/ping/:ip` | ✅ | ✅ | ❌ | Yes |
| `/api/alerts` | ✅ | ✅ | ❌ | Yes |
| `/api/alerts/:id/ack` | ✅ | ✅ | ❌ | Yes |
| `/api/users` (POST) | ✅ | ❌ | ❌ | Yes |
| `/api/admin/*` | ✅ | ❌ | ❌ | Yes |
| `/api/scan` | ✅ | ❌ | ❌ | Yes |
| `/api/settings` | ✅ | ❌ | ❌ | Yes |

## Incident Response

### If you detect unauthorized access:

1. **Immediately** change the admin password
2. Review audit logs: `/api/admin/audit`
3. Check active sessions in database
4. Revoke all sessions: `DELETE FROM sessions;` in MySQL
5. Review user accounts for unauthorized additions
6. Check for modified host configurations
7. Review recent alerts and events
8. Update firewall rules if needed
9. Rotate any API keys or tokens
10. Document the incident

### Support & Reporting Security Issues

For security vulnerabilities, please email: security@yourdomain.com
(Do not create public GitHub issues for security problems)

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Let's Encrypt (Free SSL Certificates)](https://letsencrypt.org/)
- [Nginx Security Hardening](https://www.nginx.com/blog/mitigating-ddos-attacks-with-nginx-and-nginx-plus/)
- [MySQL Security Best Practices](https://dev.mysql.com/doc/refman/8.0/en/security-guidelines.html)

---

**Last Updated**: October 9, 2026
**Version**: AbayoNet v10.0
