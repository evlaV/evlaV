import os
import re
import shlex
import shutil
import tarfile
from typing import NamedTuple

from .index import Repository, Update

INTERNAL_CHECK = "steamos.cloud"
PARALLEL_PULLS = 8
MAX_SUBJ_PACKAGES = 9

INTERNAL_REPLACE = [
    r"ssh:\/\/git@gitlab.internal.steamos.cloud:?\/[a-z0-9_-]+",
    r"ssh:\/\/git@gitlab.steamos.cloud\/[a-z0-9_-]+",
    # Holo-team is used for issues
    r"https:\/\/gitlab.steamos.cloud\/(?!holo-team)[a-z0-9_-]+",
]


class Sources(NamedTuple):
    pkg: str
    files: list[str]
    repos: list[tuple[str, str, str]]
    pkgbuild: str


def run(
    cmd: list[str],
    env: dict[str, str] | None = None,
    error: bool = True,
):
    import subprocess

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        if error:
            raise RuntimeError(f"Command {' '.join(cmd)} failed")


def srun(
    cmd: list[str],
    env: dict[str, str] | None = None,
    error: bool = True,
    silent: bool = False,
) -> str:
    import subprocess

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        if not silent:
            print(f"Command failed with code {result.returncode}")
            print(f"stdout: {result.stdout}")
            print(f"stderr: {result.stderr}")
        if error:
            raise RuntimeError(f"Command {' '.join(cmd)} failed")
        else:
            # Return these to grep for important errors
            return result.stdout.strip() + result.stderr.strip()
    return result.stdout.strip()


def infer_name(fn: str) -> str | None:
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
        return fn

    return None


def infer_version(fn: str) -> str:
    suffix = fn.rsplit("-", 2)[-2]
    suffix = suffix.replace(".src.tar.gz", "")
    return suffix


def extract_sources(fn, tar) -> Sources | None:
    # File is a .tar.gz archive containing a 'PKGBUILD' file
    # The PKGBUILD is a bash script that contains a sources variable
    # The sources variable consists of files (protocol file://) and
    # repos. For repos, we only care to preserve steamos ones

    # Try to infer package name from fn, otherwise find first dir
    # Structure of name is <name>-<version>-<release>.src.tar.gz
    # Example: jupiter-3.7.0-1.src.tar.gz
    pkgname = infer_name(fn)
    pkgver = infer_version(fn)

    if not pkgname:
        print(f"Could not infer package name from filename {fn}")
        files = tar.getnames()
        if not files:
            print(f"No files found in archive {fn}")
            return None

        pkgname = files[0].split("/")[0]

    pkgbuild = tar.extractfile(f"{pkgname}/PKGBUILD")
    if not pkgbuild:
        print(f"No PKGBUILD found in archive {fn}")
        return None

    pkgbuild = pkgbuild.read().decode("utf-8")
    sources = []
    matches = re.findall(
        r"^ *(?:source|install) *= *(\(.*?(?:\(.*?\).*?)?\)|(?!\().*?$)",
        pkgbuild,
        re.DOTALL | re.MULTILINE,
    )
    for m in matches:
        sources.extend(shlex.split(m.strip("()"), comments=True))

    urlm = re.findall(
        r"^ *url *= *(\(.*?(?:\(.*?\).*?)?\)|(?!\().*?$)",
        pkgbuild,
        re.DOTALL | re.MULTILINE,
    )
    url = None
    if urlm:
        url = shlex.split(urlm[0].strip("()"), comments=True)[0]

    files = []
    repos = []
    for src in sources:
        src = (
            src.replace("${pkgname%-git}", pkgname.replace("-git", ""))
            .replace("$pkgname", pkgname)
            .replace("${pkgname}", pkgname)
            .replace("${pkgbase%-git}", pkgname.replace("-git", ""))
            .replace("${pkgname%-*}", pkgname.rsplit("-", 1)[0])
            .replace("$pkgbase", pkgname)
            .replace("$pkgver", pkgver)
        )

        assert url or (
            "${url}" not in src and "$url" not in src
        ), f"URL variable in {pkgname} but no url set"

        if url:
            src = src.replace("$url", url).replace("${url}", url)

        # Check for git
        if "git+" in src or "git://" in src:
            if "::" in src:
                repo_name = src.split("::", 1)[0]
            else:
                repo_name = src.split("#", 1)[0].split("/")[-1].replace(".git", "")
            unpack_name = repo_name

            # Name fixups for internal repos
            internal_repo = True
            match pkgname:
                case x if "linux-neptune" in x:
                    unpack_name = "archlinux-linux-neptune"
                    if "-kasan" in pkgname:
                        unpack_name = "archlinux-" + pkgname.replace("-kasan", "")
                    repo_name = "linux-integration"
                case "steamos-customizations-jupiter":
                    repo_name = "steamos-customizations"
                case x if "mesa" in x:
                    repo_name = "mesa"
                case x if "steamos-manager" in x:
                    repo_name = "steamos-manager"
                case x if "holo-keyring" in x:
                    repo_name = "archlinux-keyring"
                case x if "holo-rust-packaging-tools" in x:
                    repo_name = "rust-packaging"
                case x if "steamos-atomupd-client" in x:
                    repo_name = "steamos-atomupd"
                case "xorg-xwayland-jupiter":
                    repo_name = "xserver"
                case x if "atomupd-daemon" in x:
                    repo_name = "atomupd-daemon"
                case x if "steamos-networking-tools" in x:
                    # The repo here does not exist/is used
                    continue
                case x if "steamos-repair-tool" in x:
                    # Too large to be uploaded to github
                    continue
                case _:
                    internal_repo = INTERNAL_CHECK in src
                    assert (
                        "$_srcname" not in repo_name
                    ), f"Unknown package with $_srcname: {pkgname}"

            if internal_repo:
                repos.append((repo_name, unpack_name, src))
        elif (
            src
            and "::" not in src
            and "http://" not in src
            and "https://" not in src
            and "$url" not in src
            and "${url}" not in src
            and "$_source_base" not in src
            and "[@]" not in src
        ):
            # Skip remotes, skip :: which is remotes
            files.append(src)

    return Sources(pkgname, files=files, repos=repos, pkgbuild=pkgbuild)


def prepare_repo(repo: str, work: str, remote: str, name: str, email: str):
    import shutil

    if not os.path.exists(work):
        os.makedirs(work, exist_ok=True)

    repo_path = f"{work}/{repo}"
    if os.path.exists(repo_path):
        shutil.rmtree(repo_path)

    srun(["git", "clone", f"{remote}/{repo}", repo_path])
    srun(["git", "-C", repo_path, "config", "user.name", name])
    srun(["git", "-C", repo_path, "config", "user.email", email])
    srun(["git", "-C", repo_path, "config", "commit.gpgsign", "false"])

    return repo_path


def get_name_from_update(repo: Repository, update: Update) -> str:
    date_str = update.date.strftime("%y%m%d-%H%MZ")
    return f"{repo.version}-{date_str}"


def get_tags(repo_path: str, versions: list[str]) -> dict[str, str]:
    print("Extracting versions from git...")
    tags = []
    for v in versions:
        try:
            out = (
                srun(
                    [
                        "git",
                        "-C",
                        repo_path,
                        "log",
                        "origin/" + v,
                        "--format=%H:%ad:%s",
                        "--date=format:%y%m%d-%H%MZ",
                    ]
                )
                .strip()
                .split("\n")
            )
            tags.extend(out)
        except RuntimeError:
            pass

    mapping = {}
    for t in tags:
        ghash, date, version, *_ = t.split(":", 3)
        mapping[version + "-" + date] = ghash.strip('"')

    return mapping


def get_upd_todo(
    tags: dict[str, str], latest: Update, branch: Repository, trunk: Repository | None
) -> list[tuple[Update, str | None]]:
    todo = []
    curr = latest

    while curr:
        name = get_name_from_update(branch, curr)
        if name in tags:
            break

        prev_branch = branch
        should_break = False

        # Create fork tag
        if trunk and curr.prev:
            cprev = curr.prev
            chk = trunk.latest
            while chk:
                if chk == cprev:
                    prev_branch = trunk
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
        while not broke.is_set():
            fn = None
            url = None
            while fn is None and url is None and not broke.is_set():
                try:
                    fn, url = q.get(timeout=0.2)
                except queue.Empty:
                    pass
            if fn is None or url is None or broke.is_set():
                break
            os.makedirs(os.path.dirname(fn), exist_ok=True)
            name = fn.rsplit("/", 1)[-1]
            try:
                srun(["curl", "-sSL", url, "-o", f"{fn}.tmp"])
                os.rename(f"{fn}.tmp", fn)
            except Exception as e:
                print(f"Failed to download {name}: {e}")
                broke.set()
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
            if broke.is_set():
                break

        while not broke.is_set() and not q.empty():
            time.sleep(0.2)
    except Exception:
        pass

    if broke.is_set():
        raise RuntimeError("Failed to download some files")

    broke.set()
    for t in threads:
        t.join()


def generate_upd_text(repo: Repository, upd: Update, added: list[str]) -> str:
    pkg_names = [p.name.rsplit("-", 2)[0] for p in upd.packages]

    if added:
        pkg_names = [p for p in pkg_names if p not in added]
        if len(added) <= MAX_SUBJ_PACKAGES:
            pkgs = "add " + ", ".join(added) + (", " if pkg_names else "")
        else:
            pkgs = f"add {len(added)} packages" + (", " if pkg_names else "")
    else:
        pkgs = ""

    if pkg_names:
        if len(pkg_names) <= MAX_SUBJ_PACKAGES:
            pkgs += f"update " + ", ".join(pkg_names)
        else:
            pkgs += f"update {len(pkg_names)} packages"

    lines = [
        f"{repo.version}: {pkgs}",
        "",
        f"Update Changes ({upd.size / 1024**2:.2f} MiB):",
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
    skip_other_repos: bool,
    tags: dict[str, str],
    should_resume: bool = False,
    pull_remote: str | None = None,
    readme: str | None = None,
    update_interval: int = 1,
):
    tag_name = get_name_from_update(repo, upd)
    if begin_tag is None:
        assert (
            not should_resume
        ), "Cannot start from the beginning. Did the repo change?"
        srun(["git", "-C", repo_path, "checkout", "--orphan", repo.version])
        if readme:
            with open(readme, "r") as f:
                readme_text = f.read()
                readme_text = readme_text.replace(
                    "<replace-repo>", repo.branch
                ).replace("<replace-repo-cap>", repo.branch.capitalize())
            with open(os.path.join(repo_path, "readme.md"), "w") as f:
                f.write(readme_text)
            srun(["git", "-C", repo_path, "add", "readme.md"])
    else:
        begin_hash = tags[begin_tag]
        srun(["git", "-C", repo_path, "checkout", begin_hash])
    added = []

    for pkg in upd.packages:
        pkg_fn = os.path.join(cache, pkg.name)

        with tarfile.open(pkg_fn, "r:gz") as tar:
            src = extract_sources(pkg.name, tar)
            if not src:
                print(f"Failed to extract sources from {pkg.name}, skipping")
                continue

            # Remove existing folder
            pkg_path = os.path.join(repo_path, src.pkg)
            if os.path.exists(pkg_path):
                shutil.rmtree(pkg_path)
            else:
                added.append(src.pkg)
            os.makedirs(pkg_path, exist_ok=True)

            # Write PKGBUILD
            with open(os.path.join(pkg_path, "PKGBUILD"), "w") as f:
                pkgbuild = src.pkgbuild
                if pull_remote:
                    for pattern in INTERNAL_REPLACE:
                        pkgbuild = re.sub(pattern, pull_remote, pkgbuild)
                f.write(pkgbuild)

            # Write other files if necessary
            if not src.files and not src.repos:
                continue

            print(f"Extracting sources for {pkg.name}")
            for fn in src.files:
                member = tar.getmember(f"{src.pkg}/{fn}")
                member.name = fn  # Prevent path traversal
                tar.extract(member, pkg_path)

            for repo_name, unpack_name, _ in src.repos if not skip_other_repos else []:
                repo_dir = os.path.join(work_dir, unpack_name)
                if os.path.exists(repo_dir):
                    srun(["rm", "-rf", repo_dir])

                # Extract repo from tar
                pkg_name = src.pkg

                def filter_repo(tarinfo, root):
                    if tarinfo.name.startswith(f"{pkg_name}/{unpack_name}/"):
                        tarinfo.name = tarinfo.name.split("/", 1)[1]
                        return tarinfo
                    return None

                tar.extractall(path=work_dir, filter=filter_repo)

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

                # Use --force here to update outdated refs
                # This can still error out, e.g., somewhere in 2024
                # branch frog becomes frog/6.11 causing a ref error
                # The alternative is --mirror, but that can throw out
                # old branches
                srun(
                    ["git", "-C", repo_dir, "push", "--all", "mirror", "--force"],
                )
                if "mesa" in repo_name:
                    # Only push steamos tags, unfortunately certain mesa tags are corrupted
                    steamos_tags = [
                        t
                        for t in srun(["git", "-C", repo_dir, "tag"]).split("\n")
                        if "steamos" in t
                    ]
                    srun(
                        ["git", "-C", repo_dir, "push", "mirror"] + steamos_tags,
                    )
                else:
                    srun(
                        ["git", "-C", repo_dir, "push", "--tags", "mirror", "--force"],
                    )

                # Save memory
                shutil.rmtree(repo_dir)

    upd_text = generate_upd_text(repo, upd, added)
    print(f"Update ({i:04d}/{total}): {upd_text}\n")
    srun(["git", "-C", repo_path, "add", "."])
    srun(
        [
            "git",
            "-C",
            repo_path,
            "commit",
            "-m",
            upd_text,
            "--date",
            upd.date.isoformat(),
        ],
        env={"GIT_COMMITTER_DATE": upd.date.isoformat()},
    )
    ghash = srun(["git", "-C", repo_path, "rev-parse", "HEAD"])
    tags[tag_name] = ghash

    if (i + 1) % update_interval == 0 or i + 1 == total:
        srun(
            [
                "git",
                "-C",
                repo_path,
                "push",
                "origin",
                f"{ghash}:refs/heads/{repo.version}",
                *(["--force"] if not should_resume else []),
            ]
        )


def process_repo(
    repo: Repository,
    trunk: Repository | None,
    cache: str,
    tags: dict[str, str],
    repo_path: str,
    work_dir: str,
    remote: str,
    skip_other_repos: bool = False,
    should_resume: bool = False,
    pull_remote: str | None = None,
    readme: str | None = None,
    update_interval: int = 1,
    force_push: list[str] | None = None,
):
    todo = get_upd_todo(tags, repo.latest, repo, trunk)

    print(f"Processing {repo.name} ({len(todo)} updates to apply)")

    missing = {}
    for upd, _ in todo:
        for pkg in upd.packages:
            fn = os.path.join(cache, pkg.name)
            if not os.path.exists(fn) and fn not in missing:
                missing[fn] = repo.url + "/" + pkg.link

    download_missing(missing)

    for i, (upd, begin_tag) in enumerate(todo):
        should_resume_branch = should_resume and (
            not force_push or repo.version not in force_push
        )

        process_update(
            repo,
            upd,
            begin_tag,
            cache,
            repo_path,
            work_dir,
            remote,
            i,
            len(todo),
            skip_other_repos,
            tags,
            should_resume_branch,
            pull_remote,
            readme,
            update_interval,
        )


def check_repos(cache: str):
    repos = {}
    seen = set()
    fns = os.listdir(cache)
    for i, fn in enumerate(fns):
        if fn.endswith(".src.tar.gz") and infer_name(fn) not in seen:
            with tarfile.open(os.path.join(cache, fn), "r:gz") as tar:
                src = extract_sources(fn, tar)
                if not src:
                    continue
            print(f"Package ({i:04d}/{len(fns)}): {fn}")

            for name, unpack, url in src.repos:
                print(f"  Repo: {name} -> {unpack}:: {url}")
                repos[name] = (unpack, url)
            seen.add(src.pkg)

    for name, (unpack, url) in repos.items():
        print(f"{name:40s} -> {unpack}:: {url}")


def find_and_push_latest(
    cache: str,
    work_dir: str,
    remote: str,
    trunk: Repository | None,
    repos: list[Repository],
):
    packages = {}
    for repo in (trunk, *repos):
        if not repo:
            continue
        upd = repo.latest
        while upd:
            for pkg in upd.packages:
                name = infer_name(pkg.name)
                if not name:
                    print(f"Could not infer name from {pkg.name}, skipping")
                    continue
                if name not in packages or packages[name][-1] < upd.date:
                    packages[name] = (pkg, repo, upd.date)
            upd = upd.prev

    print(f"Found {len(packages)} unique packages to push")

    missing = {}
    for name, (pkg, repo, _) in packages.items():
        fn = os.path.join(cache, pkg.name)
        if not os.path.exists(fn) and fn not in missing:
            missing[fn] = repo.url + "/" + pkg.link

    download_missing(missing)

    for name, (pkg, repo, _) in packages.items():
        pkg_fn = os.path.join(cache, pkg.name)

        with tarfile.open(pkg_fn, "r:gz") as tar:
            src = extract_sources(pkg.name, tar)
            if not src:
                print(f"Failed to extract sources from {pkg.name}, skipping")
                continue

            for repo_name, unpack_name, _ in src.repos:
                repo_dir = os.path.join(work_dir, unpack_name)
                if os.path.exists(repo_dir):
                    srun(["rm", "-rf", repo_dir])

                print(f"Pushing repo {repo_name} from package {pkg.name}")

                # Extract repo from tar
                pkg_name = src.pkg

                def filter_repo(tarinfo, root):
                    if tarinfo.name.startswith(f"{pkg_name}/{unpack_name}/"):
                        tarinfo.name = tarinfo.name.split("/", 1)[1]
                        return tarinfo
                    return None

                tar.extractall(path=work_dir, filter=filter_repo)

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

                # Use --force here to update outdated refs
                # This can still error out, e.g., somewhere in 2024
                # branch frog becomes frog/6.11 causing a ref error
                # The alternative is --mirror, but that can throw out
                # old branches
                run(
                    ["git", "-C", repo_dir, "push", "--all", "mirror", "--force"],
                )
                if "mesa" in repo_name:
                    # Only push steamos tags, unfortunately certain mesa tags are corrupted
                    steamos_tags = [
                        t
                        for t in srun(["git", "-C", repo_dir, "tag"]).split("\n")
                        if "steamos" in t
                    ]
                    run(
                        ["git", "-C", repo_dir, "push", "mirror"] + steamos_tags,
                    )
                else:
                    run(
                        ["git", "-C", repo_dir, "push", "--tags", "mirror", "--force"],
                    )

                # Save memory
                shutil.rmtree(repo_dir)


if __name__ == "__main__":
    # Find out which repos we need to push
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "--check-repos":
        assert len(sys.argv) == 3
        check_repos(sys.argv[2])
