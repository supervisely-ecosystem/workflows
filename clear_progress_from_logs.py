import sys


def run(logs_path):
    lines = []
    with open(logs_path, "r") as f:
        line = f.readline()
        if not line.startswith("Processing"):
            lines.append(line)
    with open(logs_path, "w") as f:
        f.writelines(lines)


if __name__ == "__main__":
    logs_path = sys.argv[1]
    run(logs_path)