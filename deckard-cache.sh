#!/bin/bash
set -e

CACHE=${1:-cache}
echo "Caching Deckard main to $CACHE"
# Cache main only: shared package filenames can collide across versions.
# The sync command downloads any missing staging packages itself.
rclone copy --transfers 4 -P --size-only \
    --http-url https://holo-packages.steamos.cloud/archlinux-deckard-hotfixes/source/ \
    :http: "$CACHE/"
