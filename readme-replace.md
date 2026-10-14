# SteamOS <replace-repo-cap> Repository

This is an automatically updated mirror of the SteamOS <replace-repo-cap> repository built from the SteamOS source packages found [here](<replace-sources>). For more information, see the tool that generates this mirror, [evlav](https://github.com/evlav/evlav).

<replace-source-note>

> [!WARNING]
> This mirror is automatically generated from scratch and updated automatically. **It may have its history regenerated at any time.**

## Building Packages
To build packages in this repository, clone it and run `makepkg` in the directory of the package you want to build.

```bash
git clone https://github.com/evlaV/<replace-repo>.git

cd <replace-repo>/<package>
makepkg -si
```
