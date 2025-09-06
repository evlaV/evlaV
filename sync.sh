if [ -z "$1" ]; then
    echo "Usage: $0 <repository>"
    exit 1
fi

BASE_URL="https://steamdeck-packages.steamos.cloud/archlinux-mirror/sources"
REPO="$1"

# Repository is an http index. Sync it with wget.
# Remove index file to force sync. Using rclone is better though
rm -rf "repositories/$REPO/index.html"
wget --mirror --no-parent --no-host-directories --cut-dirs=3 -P "repositories/$REPO" "$BASE_URL/$REPO/"