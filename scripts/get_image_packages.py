import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract Python packages from a Syft JSON report into requirements.txt format"
    )
    parser.add_argument(
        "--syft-json",
        required=True,
        help="Path to Syft JSON output file",
    )
    parser.add_argument(
        "--output-requirements",
        required=True,
        help="Path to write requirements-style package list",
    )
    args = parser.parse_args()

    syft_path = Path(args.syft_json)
    output_path = Path(args.output_requirements)

    data = json.loads(syft_path.read_text())
    artifacts = data.get("artifacts", [])

    packages = {}
    for artifact in artifacts:
        purl = artifact.get("purl", "")
        name = artifact.get("name")
        version = artifact.get("version")
        if not name or not version:
            continue
        if purl.startswith("pkg:pypi/"):
            packages[name.lower()] = version

    lines = [f"{name}=={packages[name]}" for name in sorted(packages)]
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""))

    print(f"Discovered {len(lines)} Python packages in image")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())