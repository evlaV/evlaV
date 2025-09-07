# Prepare the remote directory to run locally
REMOTE=${1:-remote}

prepare_repo() {
    if [ -d "$REMOTE/$1" ]; then
        echo "Repository $1 already exists."
    else
        git init --bare "$REMOTE/$1"
    fi
}

# # Mass create automatically
# prepare_repo() {
#     ORGANIZATION=evlav
#     git ls-remote https://github.com/$ORGANIZATION/$1 --json url || gh repo create $ORGANIZATION/$1 --public
# }

# # Mass push automatically
# # Adding a username before @ allows for automatically selecting push user
# prepare_repo() {
#     set -e

#     # Use a temporary empty repo to clear the remote, except default branch
#     # You need to make this
#     # git init --bare tmp
#     # git -C "$REMOTE/tmp" remote add mirror https://evlav-bot@github.com/evlav/holo
#     # git -C "$REMOTE/tmp" config http.postBuffer 157286400

#     git -C "$REMOTE/tmp" remote set-url mirror https://evlav-bot@github.com/evlav/$1
#     git -C "$REMOTE/tmp" push --mirror mirror || true
#     # Push everything again
#     echo "Pushing $1 to remote"
#     git -C "$REMOTE/$1" config http.postBuffer 50000000
#     if [ $(git -C "$REMOTE/$1" remote | grep mirror) ]; then
#         git -C "$REMOTE/$1" remote set-url mirror https://evlav-bot@github.com/evlav/$1
#     else
#         git -C "$REMOTE/$1" remote add mirror https://evlav-bot@github.com/evlav/$1
#     fi
#     git -C "$REMOTE/$1" push --mirror mirror
# }

# Find all with `python -m evlav.sources <cache>`
prepare_repo "jupiter"
prepare_repo "holo"

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
prepare_repo xdg-desktop-portal-gamescope
prepare_repo xdg-desktop-portal-holo
prepare_repo holo-keyring
prepare_repo holo-rust-packaging-tools

prepare_repo foxnetstatsd
prepare_repo galileo-mura-extractor
prepare_repo upower
prepare_repo usbhid-gadget-passthru
prepare_repo vpower
prepare_repo wakehook
prepare_repo wireplumber
prepare_repo xserver
prepare_repo calamares-settings-steamos
prepare_repo debos
prepare_repo kdump-steamos
prepare_repo kupdate-notifier
prepare_repo scx
prepare_repo dirlock