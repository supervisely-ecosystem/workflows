#!/usr/bin/env python3
"""Render Dockerfile template by substituting ${REQUIREMENTS_FILE}."""

from __future__ import annotations

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Dockerfile template.")
    parser.add_argument("--template", required=True, help="Path to Dockerfile template")
    parser.add_argument("--output", required=True, help="Path to rendered Dockerfile")
    parser.add_argument("--requirements-file", required=True, help="Requirements file path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not os.path.isfile(args.template):
        print(f"Dockerfile template not found at {args.template}", file=sys.stderr)
        return 1

    with open(args.template, "r", encoding="utf-8") as handle:
        content = handle.read()

    rendered = content.replace("${REQUIREMENTS_FILE}", args.requirements_file)

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
