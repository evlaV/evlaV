from datetime import datetime
from html.parser import HTMLParser
from io import BufferedReader
from typing import NamedTuple, Literal


class Package(NamedTuple):
    name: str
    link: str
    date: datetime
    size: int


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
    
    print(f"Found {len(packages)} packages in index")


if __name__ == "__main__":
    import sys

    with open(sys.argv[1], "rb") as f:
        process_index(f)
