# Prepare the remote directory to run locally
CACHE=${1:-cache}


# Remove tmp files from crashed runs
rm -f "$CACHE/*.tar.gz.tmp"

for fn in "$CACHE"/*; do
    # Skip .sig files
    [[ "$fn" == *.tar.gz ]] || continue
    echo "Verifying $fn"
    gunzip -t "$fn" || (echo "Corrupted file $fn" && rm "$fn")
done