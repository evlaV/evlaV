# Prepare the remote directory to run locally
CACHE=${1:-cache}


# Remove tmp files from crashed runs
echo "Removing .tmp files from downloader"
rm -f "$CACHE/*.tmp"

for fn in "$CACHE"/*; do
    # Skip .sig files
    [[ "$fn" == *.tar.gz ]] || continue
    echo "Verifying $fn"
    gunzip -t "$fn" || (echo "Corrupted file $fn" && rm "$fn")
done