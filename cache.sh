# Prepare the remote directory to run locally
CACHE=${1:-cache}

cache_repo() {
    echo "Caching repo $1 to $CACHE"
    rclone copy --transfers 4 -P --size-only --http-url https://steamdeck-packages.steamos.cloud/archlinux-mirror/sources/$1/ :http: $CACHE/
}

set -e

# This is a great start before running the sync script
# Unfortunately, there are name collisions between the folders,
# so caching the other packages will override the previous ones.
# Using a single folder for all versions is not ideal, but it saves having
# to redownload every repository. We take it on faith that when there is a 
# name collision, the sources are identical.
cache_repo "holo-main"
cache_repo "jupiter-main"

# cache_repo "holo-3.5"
# cache_repo "holo-3.6"
# cache_repo "holo-3.7"

# cache_repo "jupiter-3.5"
# cache_repo "jupiter-3.6"
# cache_repo "jupiter-3.7"