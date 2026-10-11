"""Command-line entry module for the crawl fixture."""

from fixture_cli.core import Engine


def main() -> int:
    """Run the fixture CLI."""
    engine = Engine(greeting="hello")
    print(engine.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
