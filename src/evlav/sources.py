from typing import NamedTuple

import logging

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
    import tarfile
    import re

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

import os

chkdir = "repositories/jupiter-3.7"
for fn in os.listdir(chkdir):
    if fn.endswith(".src.tar.gz"):
        try:
            print(extract_sources(chkdir + "/" + fn))
        except Exception as e:
            logger.error(f"Error processing {fn}: {e}")
