import logging
import os
from typing import NamedTuple

from .index import Repository, Update, get_name_from_update

INTERNAL_CHECK = "git@gitlab.internal.steamos.cloud"

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Sources(NamedTuple):
    pkg: str
    files: list[str]
    repos: list[tuple[str, str]]


def extract_sources(fn: str) -> Sources | None:
    # File is a .tar.gz archive containing a 'PKGBUILD' file
    # The PKGBUILD is a bash script that contains a sources variable
    # The sources variable consists of files (protocol file://) and
    # repos. For repos, we only care to preserve steamos ones
    import re
    import tarfile

    with tarfile.open(fn, "r:gz") as tar:
        # Try to infer package name from fn, otherwise find first dir
        # Structure of name is <name>-<version>-<release>.src.tar.gz
        # Example: jupiter-3.7.0-1.src.tar.gz
        fn = os.path.basename(fn)
        idx = -1
        for _ in range(2):
            idx = fn.rfind("-", 0, idx)
            if idx == -1:
                break
            fn = fn[:idx]
        if idx != -1:
            pkgname = fn
        else:
            pkgname = None

        if not pkgname:
            logger.warning(f"Could not infer package name from filename {fn}")
            files = tar.getnames()
            if not files:
                logger.warning(f"No files found in archive {fn}")
                return None

            pkgname = files[0].split("/")[0]

        pkgbuild = tar.extractfile(f"{pkgname}/PKGBUILD")
        if not pkgbuild:
            logger.warning(f"No PKGBUILD found in archive {fn}")
            return None

        pkgbuild = pkgbuild.read().decode("utf-8")
        matches = re.findall(
            r"^ *?source *?= *?\((.*?)\)", pkgbuild, re.DOTALL | re.MULTILINE
        )
        if not matches:
            logger.warning(f"No sources found in PKGBUILD {fn}")
            return None

        sources = [m.strip().strip('"').strip("'") for m in matches[0].split("\n")]

        files = []
        repos = []
        for src in sources:
            # Check for git
            if src.startswith("#"):
                continue
            elif src.startswith("git+"):
                repo = src.split("#", 1)[0]
                repo_name = repo.split("/")[-1].replace(".git", "")
                if INTERNAL_CHECK in repo:
                    repos.append((repo_name, repo))
            else:
                # Skip remote fetches
                if (
                    "::" not in src
                    and not src.startswith("http://")
                    and not src.startswith("https://")
                ):
                    files.append(src)

        return Sources(pkgname, files=files, repos=repos)


def prepare_repo(repo: str, work: str, remote: str):
    import shutil

    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)

    if not os.path.exists(os.path.join(work, repo)):
        r = os.system(f"git clone {remote}/{repo} {work}/{repo}")
    else:
        r = os.system(f"git -C {work}/{repo} pull")

    if r != 0:
        raise RuntimeError(f"Failed to prepare repository {repo} in {work}")


def get_tags(repo_path: str) -> list[str]:
    import subprocess

    result = subprocess.run(
        ["git", "-C", repo_path, "tag"],
        capture_output=True,
        text=True,
        check=True,
    )
    tags = result.stdout.strip().split("\n")
    return tags


def get_upd_todo(
    tags: list[str], latest: Update, branch_version: str, trunk_version: str | None
) -> list[Update]:
    todo = []
    curr = latest

    while curr:
        name = get_name_from_update(branch_version, curr)
        if name in tags:
            break
        if trunk_version:
            name = get_name_from_update(trunk_version, curr)
            if name in tags:
                break
        todo.append(curr)
        curr = curr.prev

    todo.reverse()
    return todo


def download_missing(missing: dict[str, str]):
    if not missing:
        return

    print(f"Downloading {len(missing)} missing files...")

    import threading
    import queue
    import time

    broke = threading.Event()

    def worker(q: queue.Queue):
        while True:
            fn, url = q.get()
            if fn is None or q.is_shutdown:
                break
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            name = fn.rsplit("/", 1)[-1]
            r = os.system(f"curl -sSL {url} -o {fn}.tmp && mv {fn}.tmp {fn}")
            if r != 0:
                print(f"Failed to download {name}")
                broke.set()
                q.shutdown()
                break
            
            print(f"Downloaded '{name}'")
            q.task_done()

    q = queue.Queue()
    num_threads = min(8, len(missing))
    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker, args=(q,))
        t.start()
        threads.append(t)

    try:
        for fn, url in missing.items():
            q.put((fn, url))
            if q.is_shutdown:
                break

        while not broke.is_set() and not q.empty() and not q.is_shutdown:
            time.sleep(0.2)
    except Exception:
        pass

    if broke.is_set():
        raise RuntimeError("Failed to download some files")


def process_repo(
    repo: Repository, trunk_version: str | None, cache: str, tags: list[str]
):
    todo = get_upd_todo(tags, repo.latest, repo.version, trunk_version)

    print(f"Processing {repo.name} ({len(todo)} updates to apply)")

    missing = {}
    for upd in todo:
        for pkg in upd.packages:
            fn = os.path.join(cache, pkg.name)
            if not os.path.exists(fn) and fn not in missing:
                missing[fn] = repo.url + "/" + pkg.link

    download_missing(missing)
