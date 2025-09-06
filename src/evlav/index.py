import os
from datetime import datetime
from html.parser import HTMLParser
from io import BufferedReader
from typing import Literal, NamedTuple


class Package(NamedTuple):
    name: str
    link: str
    date: datetime
    size: int


class Update(NamedTuple):
    date: datetime
    size: int
    packages: tuple[Package, ...]
    prev: "Update | None" = None


class Repository(NamedTuple):
    name: str
    version: str
    url: str
    latest: Update

class IndexParser(HTMLParser):

    def __init__(self, name_filter: str | None = ".tar.gz"):
        super().__init__()

        self.name_filter = name_filter

        self.started = False
        self.packages: list[Package] = []

        self.name = None
        self.link = None
        self.date = None
        self.size = None

        self.data_type: Literal["size", "date"] | None = None

    def handle_starttag(self, tag, attrs):
        # Register index
        if tag == "table":
            for tag, val in attrs:
                if tag == "id" and val in ("index", "index-table", "list"):
                    self.started = True
                    return
            else:
                self.started = False

        if not self.started:
            return

        match tag:
            case "tr":
                self.name = None
                self.link = None
                self.date = None
                self.size = None
            case "a":
                for tag, val in attrs:
                    if tag == "href":
                        self.link = val
                    elif tag == "title":
                        self.name = val
            case "td":
                for tag, val in attrs:
                    if tag == "class" and val in ("size", "date"):
                        self.data_type = val
                        break
                else:
                    self.data_type = None

    def handle_endtag(self, tag):
        match tag:
            case "table":
                self.started = False
            case "tr":
                if (
                    self.name
                    and self.link
                    and self.date
                    and (not self.name_filter or self.name.endswith(self.name_filter))
                ):
                    self.packages.append(
                        Package(
                            name=self.name,
                            link=self.link,
                            date=self.date,
                            size=self.size or 0,
                        )
                    )
                self.name = None
                self.link = None
                self.date = None
                self.size = None
            case "a":
                pass
            case "td":
                self.data_type = None

    def handle_data(self, data):
        match self.data_type:
            case "size":
                try:
                    num, unit = data.split()
                    num = float(num)
                    match unit[0]:
                        case "K":
                            num *= 1024
                        case "M":
                            num *= 1024**2
                        case "G":
                            num *= 1024**3
                    self.size = int(num)
                except ValueError:
                    pass
            case "date":
                try:
                    self.date = datetime.strptime(data, "%Y-%b-%d %H:%M")
                except ValueError:
                    pass


def process_index(data: BufferedReader):
    # Get the packages
    parser = IndexParser()
    parser.feed(data.read().decode("utf-8"))
    packages = parser.packages

    if not packages:
        raise ValueError("No packages found in index")

    # Create a timeline, keep only date and skip hour
    dates = sorted(set(pkg.date for pkg in packages))
    timeline: list[Update] = []
    prev_update = None
    for date in dates:
        pkgs = tuple(pkg for pkg in packages if pkg.date == date)
        size = sum(pkg.size for pkg in pkgs)
        prev_update = Update(date=date, size=size, packages=pkgs, prev=prev_update)
        timeline.append(prev_update)

    return timeline


def get_name_from_update(name: str, update: Update) -> str:
    date_str = update.date.strftime("%y%m%d-%H%MZ")
    return f"{name}-{date_str}" if name else date_str


def viz_timeline(timeline: list[Update], name: str = ""):
    for update in timeline:
        print(
            f"{get_name_from_update(name, update)}: {update.size / 1024**2:.2f} MiB in {len(update.packages)} packages"
        )
        for pkg in update.packages:
            print(f"  - {pkg.name} ({pkg.size / 1024**2:.2f} MiB)")
        print()
    print(f"Total updates ({name}): {len(timeline)}")


def get_repos(
    repo: str, versions: list[str], sources: str, cache: str, skip_existing: bool
) -> list[Repository]:
    repos = []

    for v in versions:
        fn = os.path.join(cache, f"{repo}-{v}.html")

        if not skip_existing or not os.path.exists(fn):
            url = f"{sources}/{repo}-{v}/"
            print(f"Downloading index for {repo}:{v} from {url}")
            os.makedirs(cache, exist_ok=True)
            os.system(f"curl -sSL {url} -o {fn}")
        else:
            print(f"Using cached index for {repo}:{v}")

        with open(fn, "rb") as f:
            timeline = process_index(f)

        repos.append(
            Repository(
                name=f"{repo}:{v}",
                version=v,
                url=f"{sources}/{repo}-{v}/",
                latest=timeline[-1],
            )
        )

    return repos


if __name__ == "__main__":
    import sys

    timelines = {}
    for arg in sys.argv[1:]:
        name, fn = arg.split(":", 1)
        with open(fn, "rb") as f:
            timelines[name] = set(process_index(f))

    primary_name = next(iter(timelines))
    primary = timelines.pop(primary_name)
    viz_timeline(sorted(primary, key=lambda u: u.date), name=primary_name)

    for name, timeline in timelines.items():
        print(f"Timeline for {name}:")
        viz_timeline(sorted(timeline - primary, key=lambda u: u.date), name=name)
