import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from evlav.__main__ import _main
from evlav.index import DECKARD_SOURCES, Package, get_repos
from evlav.sources import extract_sources

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://gitlab.steamos.cloud/deckard/deckardos/linux-valve.git"


def git(*args):
    result = subprocess.run(
        ["git", *map(str, args)], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def add_text(archive, name, text, mode=0o644):
    data = text.encode()
    member = tarfile.TarInfo(name)
    member.size = len(data)
    member.mode = mode
    archive.addfile(member, io.BytesIO(data))


def archive_bytes(package, pkgbuild, metadata=None, files=None):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        add_text(archive, f"{package}/PKGBUILD", pkgbuild)
        if metadata is not None:
            add_text(archive, f"{package}/.SRCINFO", metadata)
        for name, text in (files or {}).items():
            add_text(archive, f"{package}/{name}", text)
    buffer.seek(0)
    return buffer


def extract(package, pkgbuild, metadata=None, files=None, branch=None):
    with tarfile.open(
        fileobj=archive_bytes(package, pkgbuild, metadata, files), mode="r:gz"
    ) as archive:
        return extract_sources(f"{package}-1-1.src.tar.gz", archive)


def index_html(packages):
    rows = []
    for package in packages:
        rows.append(
            f'<tr><td><a href="{package.link}" title="{package.name}">'
            f'{package.name}</a></td><td class="date">'
            f'{package.date:%Y-%b-%d %H:%M}</td><td class="size">1 K</td></tr>'
        )
    return '<table id="index">' + "".join(rows) + "</table>"


class RoutingTests(unittest.TestCase):
    def test_cached_urls_and_supported_versions(self):
        package = Package("example-1-1.src.tar.gz", "example-1-1.src.tar.gz", datetime(2026, 10, 1), 1)
        with tempfile.TemporaryDirectory() as directory:
            for repo, versions in (
                ("deckard", ["main", "staging"]),
                ("holo", ["main", "3.9"]),
                ("jupiter", ["main", "3.9"]),
            ):
                for version in versions:
                    Path(directory, f"{repo}-{version}.html").write_text(index_html([package]))
            with patch("evlav.index.subprocess.run") as download:
                deckard = get_repos("deckard", ["main", "staging", "3.9"], "https://custom/", directory, True)
                self.assertEqual([repo.url for repo in deckard], list(DECKARD_SOURCES.values()))
                for name in ("holo", "jupiter"):
                    repos = get_repos(name, ["main", "3.9"], "https://custom/", directory, True)
                    self.assertEqual([repo.url for repo in repos], [f"https://custom/{name}-main/", f"https://custom/{name}-3.9/"])
                download.assert_not_called()

    def test_download_and_package_urls_agree(self):
        package = Package("example-1-1.src.tar.gz", "example-1-1.src.tar.gz", datetime(2026, 10, 1), 1)
        with tempfile.TemporaryDirectory() as directory:
            def download(command, **kwargs):
                Path(command[-1]).write_text(index_html([package]))

            with patch("evlav.index.subprocess.run", side_effect=download) as request:
                repos = get_repos("deckard", ["main", "staging"], "unused", directory, False)
            self.assertEqual([call.args[0][2] for call in request.call_args_list], [repo.url for repo in repos])

    def test_unsupported_deckard_versions_fail_without_download(self):
        with patch("evlav.index.subprocess.run") as download:
            with self.assertRaisesRegex(ValueError, "main or staging"):
                get_repos("deckard", ["3.9"], "unused", "unused", False)
            download.assert_not_called()


class MetadataTests(unittest.TestCase):
    def test_srcinfo_is_shared_and_preserves_resolved_values(self):
        metadata = (
            "pkgbase = example\n"
            "source = common.patch\n"
            "source_x86_64 = x86.patch\n"
            "source_aarch64 = arm.patch\n"
            "source = common.patch\n"
            "source = checkout::git+https://gitlab.steamos.cloud/team/project.git#commit=resolved\n"
            "pkgname = example\n"
            "install = ../example/example.install\n"
            "install = generated.install\n"
        )
        for branch in ("holo", "jupiter", "deckard"):
            with self.subTest(branch=branch):
                src = extract("example", 'source=("$unresolved")\n', metadata,
                              {"example.install": "script"}, branch)
                self.assertEqual(src.files, ["common.patch", "x86.patch", "arm.patch", "example.install"])
                self.assertEqual(src.repos[0][1], "checkout")
                self.assertTrue(src.repos[0][2].endswith("#commit=resolved"))

    def test_fallback_is_shared_and_skips_generated_installs(self):
        pkgbuild = (
            'pkgname=example\npkgbase=example\n'
            'source=("common.patch" "checkout::git+https://gitlab.steamos.cloud/team/project.git#tag=${pkgver}")\n'
            'source_aarch64=("arm.patch")\n'
            'install=../example/example.install\n'
            'install="$pkgbase.install"\n'
        )
        for branch in ("holo", "jupiter", "deckard"):
            with self.subTest(branch=branch):
                src = extract("example", pkgbuild, files={"example.install": "script"}, branch=branch)
                self.assertEqual(src.files, ["common.patch", "example.install"])
                self.assertTrue(src.repos[0][2].endswith("#tag=1"))

    def test_existing_name_fixups_work_with_both_metadata_paths(self):
        fixups = {
            "linux-neptune-65": ("linux-integration", "archlinux-linux-neptune"),
            "mesa-jupiter": ("mesa", "checkout"),
            "holo-rust-packaging-tools": ("rust-packaging", "checkout"),
            "steamos-customizations-jupiter": ("steamos-customizations", "checkout"),
        }
        source = "checkout::git+https://gitlab.steamos.cloud/team/original.git"
        for package, expected in fixups.items():
            for branch in ("holo", "jupiter"):
                for use_metadata in (False, True):
                    with self.subTest(package=package, branch=branch, srcinfo=use_metadata):
                        src = extract(package, f'source=("{source}")\n',
                                      f"source = {source}\n" if use_metadata else None,
                                      branch=branch)
                        self.assertEqual(src.repos[0][:2], expected)

    def test_kernel_alias_fallback_extracts_embedded_git_source(self):
        pkgbuild = f'_srcname="archlinux-linux-deckard"\nsource=("$_srcname::git+{UPSTREAM}#commit=$_commit")\n'
        src = extract("linux-618-deckard", pkgbuild, branch="deckard")
        self.assertEqual(src.repos[0][:2], ("deckard-linux", "archlinux-linux-deckard"))

    def test_deckardos_names_come_from_url_and_keep_archive_alias(self):
        for package, alias, name, target in (
            ("linux-tools", "linux", "linux-valve", "deckard-linux"),
            ("deckard-mesa-linux", "mesa", "mesa-valve", "deckard-mesa"),
            ("linux-source", None, "linux-valve", "deckard-linux"),
            ("linux-tools", "linux", "linux-valve-tools", "deckard-linux-valve-tools"),
            ("deckard-uboot", None, "u-boot", "deckard-u-boot"),
            ("deckard-fan-control", None, "deckard-fan-control", "deckard-fan-control"),
            ("qualcomm-android-graphics-driver", None, "qualcomm-android-graphics-driver", "qualcomm-android-graphics-driver"),
            ("qualcomm-driver", "checkout", "deckard-qualcomm-driver-valve", "qualcomm-driver"),
            ("example", "checkout", "qualcomm-driver", "deckard-qualcomm-driver"),
        ):
            for scheme in ("https://", "ssh://git@"):
                source = f"git+{scheme}gitlab.steamos.cloud/deckard/deckardos/{name}.git#branch=release/main"
                if alias:
                    source = f"{alias}::{source}"
                for srcinfo in (None, f"source = {source}\n"):
                    with self.subTest(package=package, scheme=scheme, srcinfo=srcinfo is not None):
                        src = extract(package, f'source=("{source}")\n', srcinfo)
                        self.assertEqual(src.repos[0][:2], (target, alias or name))

    def test_deckard_prefix_only_matches_deckardos_url_path(self):
        for path in ("holo", "jupiter", "deckard/deckardos-extra"):
            source = f"checkout::git+https://gitlab.steamos.cloud/{path}/project.git#branch=deckardos/test"
            src = extract("example", "", f"source = {source}\n")
            self.assertEqual(src.repos[0][:2], ("checkout", "checkout"))

    def test_git_query_is_not_part_of_mirror_or_archive_name(self):
        for alias in (None, "checkout"):
            source = "git+https://gitlab.steamos.cloud/deckard/deckardos/rtkit.git?_commit=abc#branch=main"
            if alias:
                source = f"{alias}::{source}"
            for metadata in (None, f"source = {source}\n"):
                with self.subTest(alias=alias, srcinfo=metadata is not None):
                    src = extract("rtkit", f'source=("{source}")\n', metadata)
                    self.assertEqual(src.repos[0], ("deckard-rtkit", alias or "rtkit", source))

    def test_installer_from_sibling_package_uses_archive_basename(self):
        src = extract("linux-72-deckard", "", "install = ../linux-618-deckard/kernel.install\n",
                      {"kernel.install": "script"}, "deckard")
        self.assertEqual(src.files, ["kernel.install"])

    def test_relative_local_source_path_matches_archive_member(self):
        pkgbuild = 'source=("./backport-layer-ordering.patch")\n'
        for metadata in (None, "source = ./backport-layer-ordering.patch\n"):
            with self.subTest(srcinfo=metadata is not None):
                buffer = archive_bytes("vulkan-icd-loader", pkgbuild, metadata,
                                       {"backport-layer-ordering.patch": "patch contents"})
                with tarfile.open(fileobj=buffer, mode="r:gz") as archive:
                    src = extract_sources("vulkan-icd-loader-1.4.309.0-4.src.tar.gz", archive)
                    self.assertEqual(src.files, ["backport-layer-ordering.patch"])
                    self.assertEqual(archive.extractfile(f"{src.pkg}/{src.files[0]}").read(), b"patch contents")


class LocalChainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / "cache"
        self.remote = self.root / "remote"
        self.work = self.root / "work"
        self.cache.mkdir()
        self.remote.mkdir()
        self.checkout = self.root / "source"
        git("init", "--initial-branch=main", self.checkout)
        git("-C", self.checkout, "config", "user.name", "Test")
        git("-C", self.checkout, "config", "user.email", "test@example.invalid")
        git("-C", self.checkout, "config", "commit.gpgsign", "false")

    def package(self, name, version, day, use_metadata=True, extra_repo=False, upstream=UPSTREAM):
        Path(self.checkout, "version").write_text(version)
        git("-C", self.checkout, "add", ".")
        git("-C", self.checkout, "commit", "-m", version)
        commit = git("-C", self.checkout, "rev-parse", "HEAD")
        embedded = self.root / f"embedded-{name}-{version}"
        git("clone", "--bare", self.checkout, embedded)
        source = f"archlinux-linux-deckard::git+{upstream}#commit={commit}"
        pkgbuild = (
            f"pkgname={name}\npkgbase={name}\n_srcname=archlinux-linux-deckard\n"
            f'source=("$_srcname::git+{upstream}#commit={commit}" "./config")\n'
            f"install=../{name}/kernel.install\n"
            'install="$pkgbase.install"\n'
        )
        metadata = f"source = {source}\nsource = ./config\ninstall = ../{name}/kernel.install\n"
        if extra_repo:
            extra_source = "git+https://gitlab.steamos.cloud/deckard/deckardos/unused.git#tag=old"
            pkgbuild += f'source_aarch64=("{extra_source}")\n'
            metadata += f"source_aarch64 = {extra_source}\n"
        filename = f"{name}-{version}-1.src.tar.gz"
        with tarfile.open(self.cache / filename, "w:gz", dereference=True) as archive:
            add_text(archive, f"{name}/PKGBUILD", pkgbuild)
            if use_metadata:
                add_text(archive, f"{name}/.SRCINFO", metadata)
            add_text(archive, f"{name}/config", f"config {version}")
            add_text(archive, f"{name}/kernel.install", "install script", mode=0o755)
            archive.add(embedded, arcname=f"{name}/archlinux-linux-deckard")
            if extra_repo:
                archive.add(embedded, arcname=f"{name}/unused")
        return Package(filename, filename, datetime(2026, 10, day, 12), 1024)

    def test_complete_chain_and_unchanged_resume(self):
        first = self.package("linux-618-deckard", "1", 1, extra_repo=True)
        staging = self.package("linux-618-deckard", "1.1", 2, use_metadata=False, extra_repo=True)
        latest = self.package("linux-618-deckard", "2", 3, extra_repo=True)
        for version, packages in (("main", [first, latest]), ("staging", [first, staging])):
            Path(self.cache, f"deckard-{version}.html").write_text(index_html(packages))
        git("init", "--bare", self.remote / "deckard")

        args = ["evlav", "--repo", "deckard", "--skip-existing",
                "--cache", str(self.cache), "--remote", str(self.remote), "--work", str(self.work),
                "--readme", str(ROOT / "readme-replace.md"), "--replace-url", "https://github.com/example"]
        with patch("evlav.index.subprocess.run", wraps=subprocess.run) as subprocess_calls, \
             patch("evlav.sources.download_missing") as downloads:
            with patch.object(sys, "argv", args):
                _main()
            remote = self.remote / "deckard"
            heads = git("--git-dir", remote, "show-ref", "--heads")
            self.assertEqual(set(line.split()[1] for line in heads.splitlines()), {"refs/heads/main", "refs/heads/staging"})
            self.assertEqual(git("--git-dir", remote, "rev-list", "--count", "main"), "2")
            self.assertEqual(git("--git-dir", remote, "rev-list", "--count", "staging"), "2")
            self.assertIn(DECKARD_SOURCES["main"], git("--git-dir", remote, "show", "main:readme.md"))
            pkgbuild = git("--git-dir", remote, "show", "main:linux-618-deckard/PKGBUILD")
            self.assertIn("https://github.com/example/deckard-linux.git", pkgbuild)
            self.assertIn("https://github.com/example/deckard-unused.git", pkgbuild)
            self.assertNotIn("/deckardos/", pkgbuild)
            self.assertEqual(git("--git-dir", remote, "show", "staging:linux-618-deckard/config"), "config 1.1")
            self.assertEqual(git("--git-dir", remote, "show", "main:linux-618-deckard/kernel.install"), "install script")
            self.assertTrue(git("--git-dir", remote, "ls-tree", "main", "linux-618-deckard/kernel.install").startswith("100755 "))
            latest_hash = git("-C", self.checkout, "rev-parse", "HEAD")
            for mirror in ("deckard-linux", "deckard-unused"):
                self.assertEqual(git("--git-dir", self.remote / mirror, "rev-parse", "main"), latest_hash)
            with patch.object(sys, "argv", args + ["--should-resume"]):
                _main()
            self.assertEqual(git("--git-dir", remote, "show-ref", "--heads"), heads)
            self.assertTrue(all(call.args[0] == {} for call in downloads.call_args_list))
            self.assertEqual({path.name for path in self.remote.iterdir()}, {"deckard", "deckard-linux", "deckard-unused"})
            self.assertFalse(any(call.args[0][0] == "curl" for call in subprocess_calls.call_args_list))

    def test_push_other_repos_includes_deckard(self):
        package = self.package("linux-618-deckard", "1", 1)
        Path(self.cache, "deckard-main.html").write_text(index_html([package]))
        args = ["evlav", "--repo", "deckard", "--version", "main", "--push-other-repos",
                "--skip-existing", "--cache", str(self.cache), "--remote", str(self.remote),
                "--work", str(self.work)]
        with patch.object(sys, "argv", args):
            _main()
        self.assertEqual(git("--git-dir", self.remote / "deckard-linux", "rev-parse", "main"),
                         git("-C", self.checkout, "rev-parse", "HEAD"))
        self.assertFalse((self.remote / "deckard").exists())

    def test_unchanged_package_update_is_recorded_and_resumes(self):
        payload = archive_bytes("example", 'source=("unchanged.patch")\n',
                                "source = unchanged.patch\n", {"unchanged.patch": "same contents"}).read()
        packages = []
        for release in (1, 2):
            filename = f"example-1-{release}.src.tar.gz"
            Path(self.cache, filename).write_bytes(payload)
            packages.append(Package(filename, filename, datetime(2026, 10, release, 12), len(payload)))
        Path(self.cache, "deckard-main.html").write_text(index_html(packages))
        git("init", "--bare", self.remote / "deckard")
        args = ["evlav", "--repo", "deckard", "--version", "main", "--skip-existing",
                "--cache", str(self.cache), "--remote", str(self.remote), "--work", str(self.work)]
        with patch.object(sys, "argv", args):
            _main()
        remote = self.remote / "deckard"
        head = git("--git-dir", remote, "rev-parse", "main")
        self.assertEqual(git("--git-dir", remote, "rev-list", "--count", "main"), "2")
        self.assertEqual(git("--git-dir", remote, "rev-parse", "main^{tree}"),
                         git("--git-dir", remote, "rev-parse", "main~1^{tree}"))
        with patch.object(sys, "argv", args + ["--should-resume"]):
            _main()
        self.assertEqual(git("--git-dir", remote, "rev-parse", "main"), head)

    def test_deckard_mesa_does_not_replace_jupiter_mesa(self):
        git("-C", self.checkout, "commit", "--allow-empty", "-m", "initial")
        git("-C", self.checkout, "tag", "steamos-test")
        jupiter = self.package("mesa-jupiter", "1", 1,
                               upstream="https://gitlab.steamos.cloud/jupiter/mesa.git")
        jupiter_hash = git("-C", self.checkout, "rev-parse", "HEAD")
        deckard = self.package("deckard-mesa-linux", "2", 2,
                               upstream="https://gitlab.steamos.cloud/deckard/deckardos/mesa-valve.git")
        deckard_hash = git("-C", self.checkout, "rev-parse", "HEAD")
        for name, package in (("jupiter", jupiter), ("deckard", deckard)):
            Path(self.cache, f"{name}-main.html").write_text(index_html([package]))
        args = ["evlav", "--repo", "jupiter", "deckard", "--version", "main",
                "--push-other-repos", "--skip-existing", "--cache", str(self.cache),
                "--remote", str(self.remote), "--work", str(self.work)]
        with patch.object(sys, "argv", args):
            _main()
        self.assertEqual(git("--git-dir", self.remote / "mesa", "rev-parse", "main"), jupiter_hash)
        self.assertEqual(git("--git-dir", self.remote / "deckard-mesa", "rev-parse", "main"), deckard_hash)

    def test_newest_kernel_variant_wins_for_shared_deckard_destination(self):
        older = self.package("linux-618-deckard", "1", 1)
        newer = self.package("linux-72-deckard", "2", 2)
        newest_hash = git("-C", self.checkout, "rev-parse", "HEAD")
        Path(self.cache, "deckard-main.html").write_text(index_html([older, newer]))
        args = ["evlav", "--repo", "deckard", "--version", "main", "--push-other-repos",
                "--skip-existing", "--cache", str(self.cache), "--remote", str(self.remote),
                "--work", str(self.work)]
        with patch.object(sys, "argv", args):
            _main()
        self.assertEqual(git("--git-dir", self.remote / "deckard-linux", "rev-parse", "main"), newest_hash)

    def test_url_replacement_matches_deckard_and_qualcomm_mirror_names(self):
        cases = (
            ("deckard-audio-config", "${pkgname}.git", "deckard-audio-config"),
            ("qualcomm-android-graphics-driver", "qualcomm-android-graphics-driver-valve.git", "qualcomm-android-graphics-driver"),
            ("rtkit", "rtkit.git?_commit=${_commit}", "deckard-rtkit"),
        )
        packages = [
            self.package(name, str(day), day, use_metadata=False,
                         upstream=f"https://gitlab.steamos.cloud/deckard/deckardos/{upstream}")
            for day, (name, upstream, target) in enumerate(cases, 1)
        ]
        Path(self.cache, "deckard-main.html").write_text(index_html(packages))
        git("init", "--bare", self.remote / "deckard")
        args = ["evlav", "--repo", "deckard", "--version", "main", "--skip-existing",
                "--cache", str(self.cache), "--remote", str(self.remote), "--work", str(self.work),
                "--replace-url", "https://github.com/example"]
        with patch.object(sys, "argv", args):
            _main()
        for name, upstream, target in cases:
            pkgbuild = git("--git-dir", self.remote / "deckard", "show", f"main:{name}/PKGBUILD")
            self.assertIn(f"git+https://github.com/example/{target}.git", pkgbuild)
            if name == "rtkit":
                self.assertIn("?_commit=${_commit}", pkgbuild)
            self.assertTrue((self.remote / target).is_dir())

    def test_github_initializer_creates_missing_public_repos_without_pushing(self):
        binaries = self.root / "bin"
        binaries.mkdir()
        capture = self.root / "gh-args"
        gh = binaries / "gh"
        gh.write_text('''#!/bin/bash
printf '%s\\t' "$@" >> "$CAPTURE_ARGS"
printf '\\n' >> "$CAPTURE_ARGS"
if [ "$2" = "view" ]; then
    [ "$3" = "evlav/deckard-linux" ]
fi
''')
        gh.chmod(0o755)
        env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}", CAPTURE_ARGS=str(capture))
        subprocess.run(["bash", str(ROOT / "deckard-init.sh")],
                       cwd=self.root, capture_output=True, text=True, env=env, check=True)
        calls = [line.rstrip('\t').split('\t') for line in capture.read_text().splitlines()]
        creates = [call for call in calls if call[:2] == ["repo", "create"]]
        self.assertIn(["repo", "create", "evlav/deckard", "--public"], creates)
        self.assertIn(["repo", "create", "evlav/qualcomm-android-graphics-driver", "--public"], creates)
        self.assertNotIn(["repo", "create", "evlav/deckard-linux", "--public"], creates)
        self.assertTrue(all(call[:2] in (["repo", "view"], ["repo", "create"]) for call in calls))
        self.assertTrue(all(call[-1] == "--public" and len(call) == 4 for call in creates))
        self.assertFalse(any(self.remote.iterdir()))

    def test_cache_helper_only_targets_deckard_main(self):
        binaries = self.root / "bin"
        binaries.mkdir()
        capture = self.root / "rclone-args"
        rclone = binaries / "rclone"
        rclone.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "$CAPTURE_ARGS"\n')
        rclone.chmod(0o755)
        env = dict(os.environ, PATH=f"{binaries}:{os.environ['PATH']}", CAPTURE_ARGS=str(capture))
        cache = self.root / "cache with spaces"
        subprocess.run(["bash", str(ROOT / "deckard-cache.sh"), str(cache)],
                       capture_output=True, text=True, env=env, check=True)
        arguments = capture.read_text().splitlines()
        self.assertEqual(arguments[arguments.index("--http-url") + 1], DECKARD_SOURCES["main"])
        self.assertEqual(arguments[-2:], [":http:", f"{cache}/"])


if __name__ == "__main__":
    unittest.main()
