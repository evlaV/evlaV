import argparse
import os

from .index import get_repos
from .sources import get_tags, prepare_repo, process_repo


def _main():
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
        "--pull-remote",
        type=str,
        required=False,
        default=None,
        help="Path to the final pull remote. Used to fixup the PKGBUILD files. Format: 'git+https://github.com/<org>'",
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

    # Allow pulling jupiter and holo in parallel
    work = os.path.join(args.work, args.repo)

    repo_path = prepare_repo(args.repo, work, remote, args.user_name, args.user_email)
    tags = get_tags(f"{work}/{args.repo}", args.version)

    trunk, *repos = get_repos(
        repo=args.repo,
        versions=args.version,
        sources=args.sources,
        cache=args.cache,
        skip_existing=args.skip_existing,
    )

    process_repo(
        trunk,
        trunk=None,
        cache=args.cache,
        tags=tags,
        repo_path=repo_path,
        work_dir=work,
        remote=remote,
        skip_other_repos=args.skip_other_repos,
        should_resume=args.should_resume,
        pull_remote=args.pull_remote,
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
            work_dir=work,
            remote=remote,
            skip_other_repos=args.skip_other_repos,
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
