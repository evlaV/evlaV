# Prepare the remote directory to run locally
REMOTE=${1:-remote}

prepare_repo_tag() {
    if [ -d "$REMOTE/$1" ]; then
        echo "Repository $1 already exists."
    else
        git init "$REMOTE/$1"
        git -C "$REMOTE/$1" commit --allow-empty -m "Initial commit"
        git -C "$REMOTE/$1" tag initial
    fi
}

prepare_repo() {
    if [ -d "$REMOTE/$1" ]; then
        echo "Repository $1 already exists."
    else
        git init --bare "$REMOTE/$1"
    fi
}

# Find all with `python -m evlav.sources <cache>`
prepare_repo_tag "jupiter"
prepare_repo_tag "holo"

# Jupiter sub-repos
prepare_repo mesa
prepare_repo linux-firmware-neptune
prepare_repo linux-integration

prepare_repo jupiter-dock-updater-bin
prepare_repo jupiter-fan-control
prepare_repo jupiter-hw-support
prepare_repo jupiter-validation-tools

prepare_repo steam_notif_daemon
prepare_repo steamos-customizations
prepare_repo steamos-devkit-service
prepare_repo steamos-efi
prepare_repo steamos-log-submitter
prepare_repo steamos-powerbuttond
prepare_repo steamos-atomupd-client
prepare_repo steamos-manager
prepare_repo steamos-media-creation
prepare_repo steamdeck-kde-presets

prepare_repo ds-inhibit
prepare_repo powerbuttond
prepare_repo valve-hardware-audio-processing
prepare_repo holo-keyring
prepare_repo holo-rust-packaging-tools

prepare_repo foxnetstatsd
prepare_repo galileo-mura-extractor
prepare_repo upower
prepare_repo usbhid-gadget-passthru
prepare_repo vpower
prepare_repo wakehook
prepare_repo wireplumber
prepare_repo xserver-jupiter
prepare_repo calamares-settings-steamos
prepare_repo debos
prepare_repo kdump-steamos
prepare_repo kupdate-notifier
prepare_repo scx