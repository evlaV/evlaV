#!/bin/bash
set -e

prepare_repo() {
    if [ -d "$REMOTE/$1" ]; then
        echo "Repository $1 already exists."
    else
        git init --bare "$REMOTE/$1"
    fi
}

# prepare_repo() {
#     gh repo view "evlav/$1" --json name >/dev/null 2>&1 \
#         || gh repo create "evlav/$1" --public
# }

# Repositories produced by the Deckard sync in ./remote.
prepare_repo "atomupd-daemon"
prepare_repo "deckard"
prepare_repo "deckard-android-platform-tools"
prepare_repo "deckard-apitrace"
prepare_repo "deckard-audio-config"
prepare_repo "deckard-buttonledcontrol"
prepare_repo "deckard-fan-control"
prepare_repo "deckard-foxnetstatsd"
prepare_repo "deckard-linux"
prepare_repo "deckard-linux-firmware"
prepare_repo "deckard-mesa"
prepare_repo "deckard-powerbuttond"
prepare_repo "deckard-rtkit"
prepare_repo "deckard-steamdeck-kde-presets"
prepare_repo "deckard-steamos-customizations"
prepare_repo "deckard-steamos-efi"
prepare_repo "deckard-steamos-log-submitter"
prepare_repo "deckard-steamos-manager"
prepare_repo "deckard-u-boot"
prepare_repo "deckard-uboot-splctl"
prepare_repo "holo-cursors"
prepare_repo "perfetto"
prepare_repo "qualcomm-android-graphics-driver"
prepare_repo "qualcomm-linux-graphics-driver"
prepare_repo "qualcomm-linux-graphics-driver-kgsl"
prepare_repo "renderdoc"
prepare_repo "rust-packaging"
prepare_repo "scx"
prepare_repo "steam_notif_daemon"
prepare_repo "steamos-atomupd"
prepare_repo "steamos-devkit-service"
prepare_repo "steamos-reset"
prepare_repo "xdg-desktop-portal-gamescope"
prepare_repo "xdg-desktop-portal-holo"
