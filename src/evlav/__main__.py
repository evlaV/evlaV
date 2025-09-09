import argparse
import os

from .index import get_repos
from .sources import get_tags, prepare_repo, process_repo, find_and_push_latest


def _main():
    parser = argparse.ArgumentParser(
        description="SteamOS sources repository sync script."
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="https://steamdeck-packages.steamos.cloud/archlinux-mirror/sources",
        help="URL to the sources repository.",
    )
    parser.add_argument(
        "--repo",
        type=str,
        help="Repositories to sync ('holo' or 'jupiter').",
        nargs="+",
        default=["holo", "jupiter"],
    )
    parser.add_argument(
        "-v",
        "--version",
        type=str,
        nargs="+",
        default=["main", "staging", "3.5", "3.6", "3.7"],
        help="Versions to sync (default: all supported). WARNING: The first version MUST ALWAYS be the trunk version (i.e., main).",
    )
    parser.add_argument(
        "--force-push",
        type=str,
        nargs="+",
        default=["staging"],
        help="Versions to force push. This is useful for branches that are rebased often.",
    )
    parser.add_argument(
        "--cache",
        type=str,
        default="./cache",
        help="Path to the cache directory. This will be where all the src packages and index files are stored.",
    )
    parser.add_argument(
        "-r",
        "--remote",
        type=str,
        default="./remote",
        help="Path to the output remote. This will be where all the versioned repositories are stored. Can be a local path or a github org.",
    )
    parser.add_argument(
        "--replace-url",
        type=str,
        required=False,
        default=None,
        help="Path to the replacement URL. Used to fixup the PKGBUILD files. Format: 'git+https://github.com/<org>'",
    )
    parser.add_argument(
        "--readme",
        type=str,
        required=False,
        default=None,
        help="Path to a README file to use for the repository if starting from scratch.",
    )
    parser.add_argument(
        "-w",
        "--work",
        type=str,
        default="./work",
        help="Path to a local scratch directory for processing repositories.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip refreshing indexes for testing.",
    )
    parser.add_argument(
        "--skip-other-repos",
        action="store_true",
        help="Skip extracting internal repos for testing.",
    )
    parser.add_argument(
        "--push-other-repos",
        action="store_true",
        help="Push all internal repositories and skip updating repositories.",
    )
    parser.add_argument(
        "--should-resume",
        action="store_true",
        help="Block starting over from the beginning. Prevent damaging repository history in case the index changed.",
    )
    parser.add_argument(
        "--update-interval",
        type=int,
        default=1,
        help="The number of commits between pushing to remote. 1 is fine for a local remote. 10 is good for a remote like GitHub.",
    )
    parser.add_argument(
        "--user-name",
        type=str,
        default="evlaV Bot",
        help="The username to push as when committing to the git repository.",
    )
    parser.add_argument(
        "--user-email",
        type=str,
        default="evlav@bazzite.gg",
        help="The email to use when committing to the git repository.",
    )
    args = parser.parse_args()

    remote = args.remote
    if remote.startswith("./"):
        remote = os.path.abspath(remote)

    # Find repository pairs
    pairs = []
    push_all = args.push_other_repos
    repo_data = {}
    all_tags = {}
    repo_paths = {}
    for r in args.repo:
        if push_all:
            tags = {}
            repo_paths[r] = ""
        else:
            tags = get_tags(f"{args.work}/{r}", args.version)
            repo_paths[r] = prepare_repo(
                r, args.work, remote, args.user_name, args.user_email
            )
        all_tags[r] = tags
        trunk, *rest = get_repos(
            repo=r,
            versions=args.version,
            sources=args.sources,
            cache=args.cache,
            skip_existing=args.skip_existing,
        )
        repo_data[r] = (trunk, rest)
        pairs.append((trunk, None, tags))
        for r in rest:
            pairs.append((r, trunk, tags))

    # First, update internal repos
    # In case of failure, we avoid updating jupiter/holo and losing track
    find_and_push_latest(args.cache, args.work, remote, pairs, push_all)
    if push_all:
        return

    # Update repositories
    for name in args.repo:
        trunk, repos = repo_data[name]
        repo_path = repo_paths[name]
        tags = all_tags[name]

        process_repo(
            trunk,
            trunk=None,
            cache=args.cache,
            tags=tags,
            repo_path=repo_path,
            work_dir=args.work,
            remote=remote,
            should_resume=args.should_resume,
            pull_remote=args.replacement_url,
            readme=args.readme,
            update_interval=args.update_interval,
            force_push=args.force_push,
        )
        for repo in repos:
            process_repo(
                repo,
                trunk=trunk,
                cache=args.cache,
                tags=tags,
                repo_path=repo_path,
                work_dir=args.work,
                remote=remote,
                should_resume=args.should_resume,
                pull_remote=args.pull_remote,
                readme=args.readme,
                update_interval=args.update_interval,
                force_push=args.force_push,
            )


def main():
    try:
        _main()
    except KeyboardInterrupt:
        print("Interrupted, exiting...")


if __name__ == "__main__":
    main()
