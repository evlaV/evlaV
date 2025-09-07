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
prepare_repo jupiter-fan-control
prepare_repo jupiter-hw-support
prepare_repo jupiter-validation-tools

prepare_repo linux-firmware-neptune
prepare_repo linux-integration
prepare_repo mesa

prepare_repo foxnetstatsd
prepare_repo steamos-customizations
prepare_repo vpower
prepare_repo xserver-jupiter
prepare_repo steamos-devkit-service