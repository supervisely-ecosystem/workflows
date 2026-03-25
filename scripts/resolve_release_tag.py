import argparse
import json
import re
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Resolve release tag for Docker image.")
    parser.add_argument("--config", required=True, help="Path to config.json")
    parser.add_argument("--input-release-tag", default="", help="Explicit release tag input")
    parser.add_argument(
        "--requirements",
        default="dev_requirements.txt",
        help="Requirements file path to use as fallback when config.json is missing or does not define docker_image",
    )
    return parser.parse_args()


def resolve_from_config(config_path: str) -> str:
    with open(config_path, "r", encoding="utf-8") as file_handle:
        data = json.load(file_handle)

    docker_image = data.get("docker_image")
    if not docker_image:
        raise KeyError("config.json missing .docker_image")

    version = docker_image.split(":")[-1]
    if not version:
        raise ValueError("config.json missing .version")

    version_parts = version.split(".")
    version_parts[-1] = str(int(version_parts[-1]))
    return ".".join(version_parts)


def resolve_from_requirements(requirements_path: str) -> str:
    candidate_paths = [Path(requirements_path), Path("requirements.txt")]
    seen_paths = set()

    for path in candidate_paths:
        normalized_path = path.resolve() if path.exists() else path
        normalized_key = str(normalized_path)
        if normalized_key in seen_paths:
            continue
        seen_paths.add(normalized_key)

        if not path.exists() or not path.is_file():
            continue

        with open(path, "r", encoding="utf-8") as file_handle:
            for line in file_handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                match = re.match(r"^supervisely(?:\[[^\]]+\])?==([0-9]+(?:\.[0-9]+)*)$", stripped)
                if match:
                    version = match.group(1)
                    version_parts = version.split(".")
                    version_parts[-1] = str(int(version_parts[-1]))
                    return ".".join(version_parts)

    raise FileNotFoundError(
        f"Could not resolve version from requirements files: {requirements_path}, requirements.txt"
    )


def main() -> int:
    args = parse_args()
    input_tag = (args.input_release_tag or "").strip()
    if input_tag:
        print(input_tag)
        return 0

    try:
        version = resolve_from_config(args.config)
    except FileNotFoundError:
        try:
            version = resolve_from_requirements(args.requirements)
        except Exception:
            print("config.json not found. Provide inputs.release_tag.", file=sys.stderr)
            return 1
    except json.JSONDecodeError as exc:
        print(f"config.json is invalid JSON: {exc}", file=sys.stderr)
        return 1
    except (KeyError, ValueError):
        try:
            version = resolve_from_requirements(args.requirements)
        except Exception:
            print("config.json missing .docker_image; provide inputs.release_tag", file=sys.stderr)
            return 1

    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
