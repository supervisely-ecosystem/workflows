import argparse
import json
import sys


def parse_args():
    parser = argparse.ArgumentParser(description="Resolve release tag for Docker image.")
    parser.add_argument("--config", required=True, help="Path to config.json")
    parser.add_argument("--input-release-tag", default="", help="Explicit release tag input")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_tag = (args.input_release_tag or "").strip()
    if input_tag:
        print(input_tag)
        return 0

    try:
        with open(args.config, "r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
    except FileNotFoundError:
        # todo: find instead
        print("config.json not found. Provide inputs.release_tag.", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"config.json is invalid JSON: {exc}", file=sys.stderr)
        return 1
    # todo: maybe add check for "type": "app"
    docker_image = data.get("docker_image")
    if not docker_image:
        print("config.json missing .docker_image; provide inputs.release_tag", file=sys.stderr)
        return 1
    version = docker_image.split(":")[-1]
    if not version:
        print("config.json missing .version; provide inputs.release_tag", file=sys.stderr)
        return 1
    version_parts = version.split(".")
    new_version = version_parts[:-1] + [str(int(version_parts[-1]))]
    new_version = ".".join(new_version)

    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
