# AbayoNet — MySQL setup & migration

## 1. Install MySQL/MariaDB server (on the server you're deploying to)
    sudo apt-get install mysql-server        # or: mariadb-server

## 2. Create the database and user
    sudo mysql -u root -e "
      CREATE DATABASE abayonet CHARACTER SET utf8mb4;
      CREATE USER 'abayonet'@'localhost' IDENTIFIED BY 'YOUR_STRONG_PASSWORD';
      GRANT ALL PRIVILEGES ON abayonet.* TO 'abayonet'@'localhost';
      FLUSH PRIVILEGES;"

## 3. Install the Python driver
    pip install pymysql --break-system-packages
    # (or: pip install -r requirements.txt)

## 4. Configure
Edit `abayonet.cfg` (next to abayonet.py) and set your real password:
    [database]
    host = localhost
    port = 3306
    user = abayonet
    password = YOUR_STRONG_PASSWORD
    name = abayonet

## 5. Migrate your existing data (IMPORTANT — do this before first real use)
Put your old `abayonet.db` file at `data/abayonet.db` (same place the old
app kept it), then run, from the same folder as abayonet.py/abayonet.cfg:

    python3 migrate_sqlite_to_mysql.py data/abayonet.db

This copies hosts, users, settings, alert rules, sessions, host status,
report cache, alerts, and all ping history (raw + hourly/daily rollups)
into MySQL. It's safe to re-run — already-migrated rows are skipped, not
duplicated.

Your source database has some pre-existing corruption in the raw
ping_results table (present before this migration — not something this
script causes). The migration script works around it by walking the
table in id ranges and narrowing down to the exact unrecoverable rows
rather than aborting, and prints exactly which row IDs it couldn't
read. Everything else (hosts, users, config, alert rules, and all
hourly/daily history rollups) copies over completely intact.

## 6. Start the app

Instead of typing `python abayonet.py` by hand every time, use the
included **`AbayoNet.bat`** manager — just double-click it (or
right-click → "Run as administrator" for the install/uninstall
options, which need admin rights to register a Windows Service):

    1. Run now              — runs in the current window, for testing.
                               Closing the window stops it.
    2. Install as Service   — installs pywin32 + registers AbayoNet as
                               a real Windows Service that starts
                               automatically on boot and keeps running
                               after you log off.
    3. Uninstall Service    — removes the Windows Service registration
                               only. Your database/data is untouched.
    4. Start Service        — starts an already-installed service.
    5. Stop Service         — stops it without uninstalling.
    6. Reset admin password — resets the 'admin' login back to
                               admin123 if you get locked out.
    7. Install dependencies — installs/repairs pymysql + pywin32.
    8. Exit

First time on a fresh machine: run option **7** once, then option
**1** to confirm it connects to MySQL correctly (watch for the
"database ready" line), then use option **2** to install it as a
proper background service.

If you'd rather run it by hand instead of using the menu, the
underlying commands are still just:

    python abayonet.py                    (run in foreground)
    python abayonet_service.py install    (install as a service)
    python abayonet_service.py start      (start the service)
    python abayonet_service.py stop       (stop the service)
    python abayonet_service.py remove     (uninstall the service)
    python abayonet.py --reset-admin      (reset admin password)

