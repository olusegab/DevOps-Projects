#!/bin/bash
# Script to increase MySQL max_connections to prevent "Too many connections" errors
# Run with: sudo bash /opt/abayonet/fix_mysql_connections.sh

set -e

echo "=== Fixing MySQL max_connections for AbayoNet ==="
echo ""

# Backup current MySQL config
echo "1. Backing up MySQL configuration..."
cp /etc/mysql/mysql.conf.d/mysqld.cnf /etc/mysql/mysql.conf.d/mysqld.cnf.backup.$(date +%Y%m%d_%H%M%S)

# Check if max_connections already set
if grep -q "^max_connections" /etc/mysql/mysql.conf.d/mysqld.cnf; then
    echo "2. Updating existing max_connections setting..."
    sed -i 's/^max_connections.*/max_connections = 300/' /etc/mysql/mysql.conf.d/mysqld.cnf
else
    echo "2. Adding max_connections setting..."
    # Add under [mysqld] section
    sed -i '/^\[mysqld\]/a max_connections = 300' /etc/mysql/mysql.conf.d/mysqld.cnf
fi

echo "3. Restarting MySQL service..."
systemctl restart mysql

echo "4. Verifying new setting..."
sleep 3
mysql -u abayonet -p'Legendary+1' -e "SHOW VARIABLES LIKE 'max_connections';" 2>/dev/null

echo ""
echo "✓ MySQL max_connections increased to 300"
echo "✓ AbayoNet should now handle all 82 hosts without connection errors"
echo ""
echo "Current connections: "
mysql -u abayonet -p'Legendary+1' -e "SHOW STATUS LIKE 'Threads_connected';" 2>/dev/null

echo ""
echo "Done! You can now restart AbayoNet:"
echo "  sudo systemctl restart abayonet.service"
