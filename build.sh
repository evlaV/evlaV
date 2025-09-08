#!/bin/bash

# Test builds work by building the source packages
# --allsources takes too much time :(

REMOTEDIR=${1:-./repositories/holo}

# git -C $REMOTEDIR fetch mirror
# git -C $REMOTEDIR reset --hard mirror/main

for dr in $(ls $REMOTEDIR); do
    if [ "$dr" == "grub" ] || [[ "$dr" == *linux-neptune* ]]; then
        continue
    fi
    
    makepkg -S --skippgpcheck -D $REMOTEDIR/$dr -f \
        || read -n 1 -p "Press enter to continue"
done