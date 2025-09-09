# Arch SrcPkg to Git Repo Converter
evlaV is a tool that can convert an Arch srcpkg repository to a set of git repositories. It is primarily designed to work on SteamOS repositories and designed to replace [srcpkg2git](https://gitlab.com/evlaV/srcpkg2git). 

It has two primary functions:
  - Mirror internal repositories from the last version of each package
    - Each repository **reflects the internal repository 1-1** at the time of last publish
  - Reconstruct the repository history by traversing all packages
    - This allows checking out the state of the repository **at any given time**

Initially, this tool travered all versions of each package to create internal repositories. However, it was found that all source packages contain all important tags. Traversing all packages just added noise and stale PRs. So now, only the last version is used.

## Usage
Clone this repository. Then, it is recommended to run `./cache.sh`. This will use `rclone` to pull down the `holo-main` and `jupiter-main` source packages. `rclone` supports multiple HTTP connections per file, so it is very fast. The total download is around 500GB/600GB at the time of writing this and will take 2-4 hours. The other ~100GB will be pulled from the tool.

This tool uses a single cache directory instead of one per repo. This was done because `jupiter-3.6` is essentially a copy of `jupiter-main` at the point of split. So most packages are the same, including date and hash. This allows us to use `main` as a trunk and calculate the split point for `3.6`, `3.7`, etc. However, backports do not have the same hash. We make the good-faith assumption that the `PKGBUILD` is the same between backports and the trunk so we only keep one. This means that `rclone` cannot be used to sync all repos as name collisions will cause it to redownload too many files.

In case of invalid data in the cache, `./rminv.sh` will find invalid archives and remove them.

After a bulk sync, you can run the tool:
```python
python3 -m venv venv
source venv/bin/activate

# This tool does not have any external dependencies
pip install -e .

# For local use, ./init.sh will initialize ./remote with empty repositories
# for the tool to use. For a github/gitlab org, these repositories will
# need to be created manually.
./init.sh

# Optional: use ramdisk scratch dir to avoid scratching your drive
sudo mkdir /dev/shm/work
sudo chown $USER /dev/shm/work
ln -s /dev/shm/work ./work

# Push internal package repos to ./remote
# Latest version only, with `git push --mirror`. Reflects internal repo 1-1
# Old branches from old packages might be missing;
# that's okay, it prevents drift and important tags are in all source packages
evlav --push-other-repos
# Reconstruct jupiter and holo histories
evlav --skip-other-repos

# For incremental updates, calculate missing updates in jupiter/holo, then:
# 1) For each latest version of an updated package, mirror its internal repo
# 2) Only if successful, update holo/jupiter to reflect the last version
# (avoids missing updates in case of a crash)
# Running from scratch, this is equivalent to the commands above.
evlav
```

The tool will automatically resume from the last point it was ran. Use `evlav --help` to find out more options.

To reconstruct the whole history and update all internal repositories, the tool requires ~40 minutes.


## Design Goals

The design goals for this tool were:
  - Should run locally
    - Without internet if nothing changed
  - Should run from a github action
    - Only downloading what was changed since last run
    - I.e., take a few minutes to run
    - If no update was done, should only ping a few index files so it can run multiple times a day
  - Should reconstruct the entire history from scratch
    - This would allow re-constructing the repos if something changes
  - Should minimize hard drive access
    - Only the `PKGBUILD` is extracted from each srcpkg
    - Based on `PKGBUILD` sources, local sources are extracted individually to place in the package repository
    - To mirror internal repos, the only the latest version of each package is checked for them. If they exist, they are extracted and `git push --mirror`ed to the remote.

