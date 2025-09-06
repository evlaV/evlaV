import logging
import os
import re
import subprocess
import tarfile
from typing import NamedTuple

from .index import Repository, Update, get_name_from_update

INTERNAL_CHECK = "git@gitlab.internal.steamos.cloud"
PARALLEL_PULLS = 8

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class Sources(NamedTuple):
    pkg: str
    files: list[str]
    repos: list[tuple[str, str]]
    pkgbuild: str


def extract_sources(fn: str) -> Sources | None:
    # File is a .tar.gz archive containing a 'PKGBUILD' file
    # The PKGBUILD is a bash script that contains a sources variable
    # The sources variable consists of files (protocol file://) and
    # repos. For repos, we only care to preserve steamos ones

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

        sources = []
        for m in matches[0].split("\n"):
            initial = m.strip().rsplit(" #", 1)[0].strip()

            if initial.startswith('"') and initial.endswith('"'):
                initial = initial[1:-1]
            elif initial.startswith("'") and initial.endswith("'"):
                initial = initial[1:-1]
            elif initial.startswith("#"):
                continue
            elif " " in initial:
                sources.extend(initial.split(" "))
                continue

            sources.append(initial)

        files = []
        repos = []
        for src in sources:
            # Check for git
            if src.startswith("git+"):
                repo = src.split("#", 1)[0]
                repo_name = repo.split("/")[-1].replace(".git", "")
                if INTERNAL_CHECK in repo:
                    repos.append((repo_name, repo))
            elif (
                src
                and "::" not in src
                and "http://" not in src
                and "https://" not in src
            ):
                # Skip remotes, skip :: which is remotes
                files.append(src)

        return Sources(pkgname, files=files, repos=repos, pkgbuild=pkgbuild)


def prepare_repo(repo: str, work: str, remote: str):
    import shutil

    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work, exist_ok=True)

    repo_path = f"{work}/{repo}"
    r = os.system(f"git clone {remote}/{repo} {repo_path}")

    if r != 0:
        raise RuntimeError(f"Failed to prepare repository {repo} in {work}")

    return repo_path


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
    tags: list[str], latest: Update, branch_version: str, trunk: Repository | None
) -> list[tuple[Update, str | None]]:
    todo = []
    curr = latest

    while curr:
        name = get_name_from_update(branch_version, curr)
        if name in tags:
            break

        prev_branch = branch_version
        should_break = False

        # Create fork tag
        if trunk and curr.prev:
            cprev = curr.prev
            chk = trunk.latest
            while chk:
                if chk == cprev:
                    prev_branch = trunk.version
                    should_break = True
                    break
                chk = chk.prev

        begin_tag = get_name_from_update(prev_branch, curr.prev) if curr.prev else None
        todo.append((curr, begin_tag))
        if should_break:
            break
        curr = curr.prev

    todo.reverse()
    return todo


def download_missing(missing: dict[str, str]):
    if not missing:
        return

    print(f"Downloading {len(missing)} missing files...")

    import queue
    import threading
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
    num_threads = min(PARALLEL_PULLS, len(missing))
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


def srun(cmd: list[str]):
    import subprocess

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command failed with code {result.returncode}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        raise RuntimeError(f"Command {' '.join(cmd)} failed")
    return result.stdout.strip()


def generate_upd_text(repo: Repository, upd: Update) -> str:
    lines = [
        f"{get_name_from_update(repo.version, upd)}: update {', '.join([p.name.rsplit("-", 2)[0] for p in upd.packages])} ({upd.size / 1024**2:.2f} MiB)"
    ]
    for pkg in upd.packages:
        lines.append(f"- {pkg.name} ({pkg.size / 1024**2:.2f} MiB)")
    return "\n".join(lines)


def process_update(
    repo: Repository,
    upd: Update,
    begin_tag: str | None,
    cache: str,
    repo_path: str,
    work_dir: str,
    remote: str,
    i: int,
    total: int,
):
    import subprocess

    tag_name = get_name_from_update(repo.version, upd)
    if begin_tag is None:
        begin_tag = "initial"
    srun(["git", "-C", repo_path, "checkout", begin_tag])

    for pkg in upd.packages:
        pkg_fn = os.path.join(cache, pkg.name)
        src = extract_sources(pkg_fn)
        if not src:
            print(f"Failed to extract sources from {pkg.name}, skipping")
            continue

        # Remove existing folder
        pkg_path = os.path.join(repo_path, src.pkg)
        srun(["rm", "-rf", pkg_path])
        os.makedirs(pkg_path, exist_ok=True)

        # Write PKGBUILD
        with open(os.path.join(pkg_path, "PKGBUILD"), "w") as f:
            f.write(src.pkgbuild)

        # Write other files if necessary
        if not src.files and not src.repos:
            continue

        with tarfile.open(pkg_fn, "r:gz") as tar:
            for fn in src.files:
                member = tar.getmember(f"{src.pkg}/{fn}")
                member.name = fn  # Prevent path traversal
                tar.extract(member, pkg_path)

            for repo_name, _ in src.repos:
                repo_dir = os.path.join(work_dir, repo_name)
                if os.path.exists(repo_dir):
                    srun(["rm", "-rf", repo_dir])

                # Extract repo from tar
                pkg_name = src.pkg
                def filter_repo(tarinfo):
                    if tarinfo.name.startswith(f"{pkg_name}/{repo_name}/"):
                        tarinfo.name = tarinfo.name.split("/", 1)[1]
                        return tarinfo
                    return None

                tar.extractall(path=work_dir, members=filter(filter_repo, tar))

                # Add remote and push everything
                srun(
                    [
                        "git",
                        "-C",
                        repo_dir,
                        "remote",
                        "add",
                        "mirror",
                        remote + "/" + repo_name,
                    ]
                )
                srun(["git", "-C", repo_dir, "push", "--mirror", "mirror"])

    upd_text = generate_upd_text(repo, upd)
    print(f"Update ({i:04d}/{total}): {upd_text}\n")
    srun(["git", "-C", repo_path, "add", "."])
    srun(["git", "-C", repo_path, "commit", "-m", upd_text])
    srun(["git", "-C", repo_path, "tag", tag_name])

    if (i + 1) % 1 == 0 or i + 1 == total:
        # print(f"Pushing to remote {remote}...")
        srun(["git", "-C", repo_path, "push", "origin", "--tags"])


def process_repo(
    repo: Repository,
    trunk: Repository | None,
    cache: str,
    tags: list[str],
    repo_path: str,
    work_dir: str,
    remote: str,
):
    todo = get_upd_todo(tags, repo.latest, repo.version, trunk)

    print(f"Processing {repo.name} ({len(todo)} updates to apply)")

    missing = {}
    for upd, _ in todo:
        for pkg in upd.packages:
            fn = os.path.join(cache, pkg.name)
            if not os.path.exists(fn) and fn not in missing:
                missing[fn] = repo.url + "/" + pkg.link

    for i, (upd, begin_tag) in enumerate(todo):
        process_update(
            repo, upd, begin_tag, cache, repo_path, work_dir, remote, i, len(todo)
        )

    download_missing(missing)
