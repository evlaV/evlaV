import argparse

from .index import get_repos

def main():
    parser = argparse.ArgumentParser(
        description="SteamOS sources repository sync script."
    )
    parser.add_argument(
        "repo",
        type=str,
        default="holo",
        help="Repository to sync ('holo' or 'jupiter').",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="https://steamdeck-packages.steamos.cloud/archlinux-mirror/sources",
        help="URL to the sources repository.",
    )
    parser.add_argument(
        "-v",
        "--version",
        type=str,
        nargs="+",
        default=["main", "3.3.3", "3.5", "3.6", "3.7"],
        help="Versions to sync (default: all supported). WARNING: The first version MUST ALWAYS be the trunk version (i.e., main).",
    )
    parser.add_argument(
        "--cache",
        type=str,
        default="./cache",
        help="Path to the cache directory. This will be where all the src packages and index files are stored.",
    )
    parser.add_argument(
        "-r", "--remote",
        type=str,
        default="./repositories",
        help="Path to the output remote. This will be where all the versioned repositories are stored. Can be a local path or a github org.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip refreshing indexes for testing.",
    )
    args = parser.parse_args()

    trunk, *repos = get_repos(
        repo=args.repo,
        versions=args.version,
        sources=args.sources,
        cache=args.cache,
        skip_existing=args.skip_existing,
    )
    print(trunk, repos)

if __name__ == "__main__":
    main()
