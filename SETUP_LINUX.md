# AbayoNet — Linux server setup

## 1. Install MySQL/MariaDB
    sudo apt-get update
    sudo apt-get install mysql-server        # or: mariadb-server

## 2. Create the database and user
    sudo mysql -u root -e "
      CREATE DATABASE abayonet CHARACTER SET utf8mb4;
      CREATE USER 'abayonet'@'localhost' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
      GRANT ALL PRIVILEGES ON abayonet.* TO 'abayonet'@'localhost';
      FLUSH PRIVILEGES;"

## 3. Install Python 3 and pip (if not already present)
    sudo apt-get install python3 python3-pip

## 4. Copy the app files onto the server
Put this whole folder somewhere permanent, e.g.:
    /opt/abayonet/

Contents should look like:
    /opt/abayonet/
      abayonet.py
      abayonet.cfg
      migrate_sqlite_to_mysql.py
      AbayoNet.sh
      static/
        index.html

## 5. Configure
Edit `/opt/abayonet/abayonet.cfg`:
    [database]
    host = localhost
    port = 3306
    user = abayonet
    password = YOUR_STRONG_PASSWORD
    name = abayonet

## 6. Run the manager
    cd /opt/abayonet
    chmod +x AbayoNet.sh
    ./AbayoNet.sh

Menu options:
    1. Run now                — foreground, in this terminal, for testing.
    2. Install as Service     — registers AbayoNet as a systemd service
                                 (auto-starts on boot, keeps running after
                                 you log out). Needs sudo.
    3. Uninstall Service      — removes the systemd unit only. Your
                                 database/data is untouched.
    4. Start Service
    5. Stop Service
    6. Service status / logs  — shows `systemctl status` and how to
                                 tail live logs with `journalctl`.
    7. Reset admin password   — back to admin123 if you're locked out.
    8. Install/repair deps    — installs pymysql.
    9. Exit

First run on a fresh server:
    ./AbayoNet.sh            → option 1, confirm you see
                                "database ready (MySQL: ...)"
    sudo ./AbayoNet.sh       → option 2, to install it permanently

## 7. Migrate your existing data (if upgrading from the old SQLite version)
    cd /opt/abayonet
    python3 migrate_sqlite_to_mysql.py /path/to/old/abayonet.db

## Useful systemd commands directly (once installed via option 2)
    sudo systemctl status abayonet
    sudo systemctl restart abayonet
    sudo journalctl -u abayonet -f      # live logs
    sudo systemctl enable abayonet      # ensure auto-start on boot
    sudo systemctl disable abayonet     # stop auto-starting on boot

## Firewall
If you can't reach the dashboard from another machine, open the port
AbayoNet is running on (shown in the startup log, default 8780 unless
changed in abayonet.cfg):
    sudo ufw allow 8780/tcp        # Ubuntu/Debian with ufw
    sudo firewall-cmd --add-port=8780/tcp --permanent && sudo firewall-cmd --reload   # RHEL/Fedora
