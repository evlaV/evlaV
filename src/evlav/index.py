from datetime import datetime
from html.parser import HTMLParser
from io import BufferedReader
from typing import NamedTuple, Literal


class Package(NamedTuple):
    name: str
    link: str
    date: datetime
    size: int


class Update(NamedTuple):
    date: datetime
    size: int
    packages: tuple[Package, ...]
    prev: tuple["Update", ...] = ()


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


def viz_timeline(timeline: list[Update]):
    for update in timeline:
        print(
            f"{update.date.date()}: {update.size / 1024**2:.2f} MiB in {len(update.packages)} packages"
        )
        for pkg in update.packages:
            print(f"  - {pkg.name} ({pkg.size / 1024**2:.2f} MiB)")
        print()
    print(f"Total updates: {len(timeline)}")


def process_index(data: BufferedReader):
    # Get the packages
    parser = IndexParser()
    parser.feed(data.read().decode("utf-8"))
    packages = parser.packages

    if not packages:
        raise ValueError("No packages found in index")

    # Create a timeline, keep only date and skip hour
    dates = sorted(
        set(datetime.combine(pkg.date.date(), datetime.min.time()) for pkg in packages)
    )
    prev_date = None
    timeline: list[Update] = []
    for date in dates:
        pkgs = tuple(
            pkg
            for pkg in packages
            if pkg.date < date and (not prev_date or pkg.date >= prev_date)
        )
        size = sum(pkg.size for pkg in pkgs)
        timeline.append(Update(date=date, size=size, packages=pkgs, prev=tuple(timeline)))
        prev_date = date

    viz_timeline(timeline)


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], "rb") as f:
        process_index(f)
