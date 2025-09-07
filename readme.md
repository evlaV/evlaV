# Arch SrcPkg to Git Repo Converter
This is a little tool that can convert an Arch srcpkg repository to a set of git repositories. It is primarily designed to work on SteamOS repositories and designed to replace [srcpkg2git](https://gitlab.com/evlaV/srcpkg2git). 

The design goals for this tool were:
  - Should be able to run locally
    - Without internet if nothing changed
  - Should be able to run from a github action
    - Only downloading what was changed since last run
    - I.e., take a few minutes to run
    - If no update was done, should only ping a few index files so it can run multiple times a day
  - Should be able to reconstruct the entire history from scratch
    - This would allow re-constructing the repos if something changes
  - Should minimize hard drive access
    - Only the PKGBUILD is extracted from each srcpkg
    - Afterwards, local sources are extracted individually to place in the git repo
    - If `--skip-other-repos` is not used, internal repositories (only) are piece meal extracted and pushed to a remote.

## Usage
Clone this repository. Then, it is recommended to run `./cache.sh`. This will use `rclone` to pull down the `holo-main` and `jupiter-main` source packages. `rclone` supports multiple HTTP connections per file, so it is very fast. The total download is around 500GB/600GB at the time of writing this and will take 2-4 hours. The other ~100GB will be pulled from the tool.

This tool uses a single cache directory instead of one per repo. This was done because `jupiter-3.6` is essentially a copy of `jupiter-main` at the point of split. So most packages are the same, including date and hash. This allows us to use `main` as a trunk and calculate the split point for `3.6`, `3.7`, etc. However, backports do not have the same hash. We make the good-faith assumption that the `PKGBUILD` is the same between backports and the trunk so we only keep one. This means that `rclone` cannot be used to sync all repos.

In case of invalid data in the cache, `./rminv.sh` will find invalid archives and remove them.

Then, you can run the tool:
```python
python3 -m venv venv
source venv/bin/activate

# This tool does not have any external dependencies
pip install -e .

# For local use, ./init.sh will initialize ./remote with empty repositories
# for the tool to use. For a github/gitlab org, these repositories will
# need to be created manually.

# For holo, jupiter repos, the tool will begin from tag initial, so you
# can e.g., add readmes to that tag if you want.
./init.sh

# Run once per repo
# By default, the directoreis ./work (scratch dir), ./cache (tar.gz dir), ./remote (assumes) are used
evlav jupiter
evlav holo
```