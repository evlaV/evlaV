# Prepare the remote directory to run locally
REMOTE=${1:-remote}

prepare_repo() {
    if [ -d "$REMOTE/$1" ]; then
        echo "Repository $1 already exists."
    else
        git init "$REMOTE/$1"
    fi
}

prepare_repo "jupiter"
prepare_repo "holo"