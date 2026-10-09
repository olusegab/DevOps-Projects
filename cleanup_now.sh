#!/bin/bash
# Emergency data cleanup - runs once to immediately fix stuck query issue
# Deletes ping data older than 7 days in batches

set -e

DB_USER="abayonet"
DB_PASS="Legendary+1"
DB_NAME="abayonetDB"

echo "=== AbayoNet Emergency Data Cleanup ==="
echo ""
echo "This will delete ping_results older than 7 days to fix performance issues."
echo "Starting at: $(date)"
echo ""

# Calculate cutoff date (7 days ago)
CUTOFF=$(date -d '7 days ago' '+%Y-%m-%d %H:%M:%S')
echo "Deleting ping_results older than: $CUTOFF"
echo ""

# Get initial count
INITIAL=$(mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -sN -e "SELECT COUNT(*) FROM ping_results WHERE timestamp < '$CUTOFF';" 2>/dev/null)
echo "Found $INITIAL rows to delete"
echo ""

if [ "$INITIAL" -eq 0 ]; then
    echo "No old data to delete. Cleanup complete!"
    exit 0
fi

# Delete in batches to avoid locking
BATCH_SIZE=50000
TOTAL_DELETED=0

echo "Deleting in batches of $BATCH_SIZE rows..."
echo ""

while true; do
    # Delete one batch
    DELETED=$(mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -sN -e "
        DELETE FROM ping_results 
        WHERE timestamp < '$CUTOFF' 
        LIMIT $BATCH_SIZE;
        SELECT ROW_COUNT();" 2>/dev/null | tail -1)
    
    if [ "$DELETED" -eq 0 ]; then
        break
    fi
    
    TOTAL_DELETED=$((TOTAL_DELETED + DELETED))
    PERCENT=$((TOTAL_DELETED * 100 / INITIAL))
    
    echo "Progress: $TOTAL_DELETED / $INITIAL rows deleted ($PERCENT%)"
    
    # Brief pause to let other queries through
    sleep 0.5
done

echo ""
echo "=== Cleanup Complete ==="
echo "Total deleted: $TOTAL_DELETED rows"
echo "Finished at: $(date)"
echo ""

# Show final table size
FINAL=$(mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -sN -e "SELECT COUNT(*) FROM ping_results;" 2>/dev/null)
echo "Final ping_results count: $FINAL rows"
echo ""

# Optimize table to reclaim space
echo "Optimizing table to reclaim disk space..."
mysql -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "OPTIMIZE TABLE ping_results;" 2>/dev/null
echo ""

echo "✅ Done! The app should now be fast and responsive."
echo "Please restart AbayoNet: sudo systemctl restart abayonet.service"
