#!/bin/bash
# AbayoNet HTTPS Setup Script
# Automates SSL certificate setup for NAT port forwarding

set -e

echo "=================================================="
echo "  AbayoNet HTTPS Setup for NAT Port Forwarding"
echo "=================================================="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Please run with sudo: sudo ./setup-https.sh"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$(whoami)}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "📂 Working directory: $SCRIPT_DIR"
echo "👤 User: $ACTUAL_USER"
echo ""

# Create SSL directory
mkdir -p "$SCRIPT_DIR/ssl"

echo "Select SSL certificate option:"
echo ""
echo "1) Self-signed certificate (Quick - for testing/internal use)"
echo "2) Let's Encrypt certificate (Production - trusted by browsers)"
echo "3) I have my own certificate files"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "🔐 Generating self-signed certificate..."
        echo ""
        
        read -p "Enter your domain/hostname (e.g., abayonet.example.com): " domain
        domain=${domain:-localhost}
        
        # Generate self-signed certificate
        openssl req -newkey rsa:2048 -nodes \
            -keyout "$SCRIPT_DIR/ssl/key.pem" \
            -x509 -days 365 \
            -out "$SCRIPT_DIR/ssl/cert.pem" \
            -subj "/C=NG/ST=Lagos/L=Lagos/O=AbayoNet/CN=$domain"
        
        echo ""
        echo "✅ Self-signed certificate created!"
        echo "⚠️  WARNING: Browsers will show security warnings"
        echo "⚠️  Only use for testing or internal networks"
        ;;
        
    2)
        echo ""
        echo "🌐 Setting up Let's Encrypt certificate..."
        echo ""
        
        # Check if certbot is installed
        if ! command -v certbot &> /dev/null; then
            echo "📦 Installing certbot..."
            apt update
            apt install -y certbot
        fi
        
        read -p "Enter your domain name (must point to your public IP): " domain
        
        if [ -z "$domain" ]; then
            echo "❌ Domain name required"
            exit 1
        fi
        
        echo ""
        echo "⚠️  IMPORTANT: Port 8081 must be accessible from the internet during verification"
        echo "⚠️  Make sure your NAT forwarding is: Public:8081 → Server:8081"
        echo ""
        read -p "Press Enter when ready, or Ctrl+C to abort..."
        
        # Stop AbayoNet
        echo "🛑 Stopping AbayoNet..."
        systemctl stop abayonet || true
        
        # Get certificate
        echo "📜 Requesting certificate from Let's Encrypt..."
        certbot certonly --standalone \
            -d "$domain" \
            --preferred-challenges http \
            --http-01-port 8081 \
            --agree-tos \
            --non-interactive \
            --email "admin@${domain}" || {
                echo "❌ Certificate request failed"
                echo "   Make sure:"
                echo "   1. Domain $domain points to your public IP"
                echo "   2. Port 8081 is open in your NAT forwarding"
                echo "   3. No firewall blocking port 8081"
                exit 1
            }
        
        # Copy certificates
        echo "📋 Copying certificates..."
        cp "/etc/letsencrypt/live/$domain/fullchain.pem" "$SCRIPT_DIR/ssl/cert.pem"
        cp "/etc/letsencrypt/live/$domain/privkey.pem" "$SCRIPT_DIR/ssl/key.pem"
        
        # Create renewal script
        echo "⏰ Setting up auto-renewal..."
        cat > "$SCRIPT_DIR/renew-cert.sh" << 'RENEWSCRIPT'
#!/bin/bash
# Auto-renew Let's Encrypt certificate

DOMAIN="DOMAIN_PLACEHOLDER"
INSTALL_DIR="INSTALL_DIR_PLACEHOLDER"

echo "$(date): Starting certificate renewal for $DOMAIN"

# Stop AbayoNet
systemctl stop abayonet

# Renew certificate
certbot renew --standalone --http-01-port 8081

# Copy new certificates
cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$INSTALL_DIR/ssl/cert.pem"
cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$INSTALL_DIR/ssl/key.pem"

# Fix permissions
chown USER_PLACEHOLDER:USER_PLACEHOLDER "$INSTALL_DIR/ssl/"*.pem
chmod 600 "$INSTALL_DIR/ssl/key.pem"
chmod 644 "$INSTALL_DIR/ssl/cert.pem"

# Start AbayoNet
systemctl start abayonet

echo "$(date): Certificate renewed and AbayoNet restarted"
RENEWSCRIPT
        
        # Replace placeholders
        sed -i "s|DOMAIN_PLACEHOLDER|$domain|g" "$SCRIPT_DIR/renew-cert.sh"
        sed -i "s|INSTALL_DIR_PLACEHOLDER|$SCRIPT_DIR|g" "$SCRIPT_DIR/renew-cert.sh"
        sed -i "s|USER_PLACEHOLDER|$ACTUAL_USER|g" "$SCRIPT_DIR/renew-cert.sh"
        chmod +x "$SCRIPT_DIR/renew-cert.sh"
        
        # Add to crontab
        (crontab -l 2>/dev/null | grep -v "renew-cert.sh"; echo "0 3 1 * * $SCRIPT_DIR/renew-cert.sh >> $SCRIPT_DIR/data/cert-renewal.log 2>&1") | crontab -
        
        echo "✅ Let's Encrypt certificate installed!"
        echo "✅ Auto-renewal scheduled (monthly)"
        ;;
        
    3)
        echo ""
        echo "📂 Manual certificate installation..."
        echo ""
        echo "Please copy your certificate files to:"
        echo "  Certificate: $SCRIPT_DIR/ssl/cert.pem"
        echo "  Private Key: $SCRIPT_DIR/ssl/key.pem"
        echo ""
        read -p "Press Enter when files are in place..."
        
        if [ ! -f "$SCRIPT_DIR/ssl/cert.pem" ] || [ ! -f "$SCRIPT_DIR/ssl/key.pem" ]; then
            echo "❌ Certificate files not found"
            exit 1
        fi
        ;;
        
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

# Set permissions
echo "🔒 Setting file permissions..."
chown -R "$ACTUAL_USER:$ACTUAL_USER" "$SCRIPT_DIR/ssl"
chmod 600 "$SCRIPT_DIR/ssl/key.pem"
chmod 644 "$SCRIPT_DIR/ssl/cert.pem"

# Verify certificate
echo ""
echo "🔍 Verifying certificate..."
if openssl x509 -in "$SCRIPT_DIR/ssl/cert.pem" -text -noout > /dev/null 2>&1; then
    echo "✅ Certificate is valid"
    
    # Show certificate details
    echo ""
    echo "📋 Certificate Details:"
    openssl x509 -in "$SCRIPT_DIR/ssl/cert.pem" -noout -subject -issuer -dates
else
    echo "❌ Certificate validation failed"
    exit 1
fi

# Start AbayoNet
echo ""
echo "🚀 Starting AbayoNet..."
systemctl start abayonet
sleep 3

# Check if HTTPS is enabled
if grep -q "SSL/TLS enabled" "$SCRIPT_DIR/data/abayonet.log" 2>/dev/null; then
    echo ""
    echo "=================================================="
    echo "  ✅ HTTPS Successfully Enabled!"
    echo "=================================================="
    echo ""
    echo "AbayoNet is now running with HTTPS/SSL encryption"
    echo ""
    echo "📌 Next Steps:"
    echo ""
    echo "1. Update your NAT port forwarding:"
    echo "   Public:443 → Server:8081"
    echo ""
    echo "2. Test HTTPS locally:"
    echo "   curl -k https://localhost:8081/api/version"
    echo ""
    echo "3. Access from internet:"
    if [ "$choice" = "2" ]; then
        echo "   https://$domain"
    else
        echo "   https://your-public-ip:8081"
        echo "   (or https://yourdomain.com if you have a domain)"
    fi
    echo ""
    echo "4. Check logs:"
    echo "   tail -f $SCRIPT_DIR/data/abayonet.log"
    echo ""
    echo "=================================================="
else
    echo ""
    echo "⚠️  HTTPS may not be enabled. Check logs:"
    echo "   tail -20 $SCRIPT_DIR/data/abayonet.log"
fi
