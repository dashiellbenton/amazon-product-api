"""Command-line interface for amazon-buddy."""
from __future__ import annotations

import argparse
import json

import amazon_buddy as api


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--async", dest="async_tasks", default=5, type=int)
    parser.add_argument("--keyword", "-k", default="")
    parser.add_argument("--number", "-n", default=20, type=int)
    parser.add_argument("--filetype", default="csv", choices=["csv", "json", "all", ""])
    parser.add_argument("--sort", action="store_true")
    parser.add_argument("--discount", "-d", action="store_true")
    parser.add_argument("--sponsored", action="store_true")
    parser.add_argument("--min-rating", default=1, type=float)
    parser.add_argument("--max-rating", default=5, type=float)
    parser.add_argument("--country", default="US")
    parser.add_argument("--category", default="aps")
    parser.add_argument("--random-ua", action="store_true")
    parser.add_argument("--user-agent", default="")
    parser.add_argument("--timeout", "-t", default=0, type=int)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amazon-buddy", description="Amazon scraper")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["products", "reviews", "asin", "categories", "countries"]:
        p = sub.add_parser(name)
        _add_common_arguments(p)
        if name in {"reviews", "asin"}:
            p.add_argument("id")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    options = vars(args)
    command = options.pop("command")
    if options.get("user_agent"):
        options["ua"] = options.pop("user_agent")
        options["random_ua"] = False
    options["rating"] = [options.pop("min_rating"), options.pop("max_rating")]
    if command in {"reviews", "asin"}:
        options["asin"] = options.pop("id")
    data = getattr(api, command)(options) if command != "countries" else api.countries()
    if command in {"countries", "categories"} or not options.get("filetype"):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif command in {"products", "reviews", "asin"}:
        stem = api.safe_output_stem(command, options.get("keyword") or options.get("asin"))
        print(f"Result was saved to a {options['filetype']} file using the clear name format: {stem}.<ext>")


if __name__ == "__main__":
    main()
