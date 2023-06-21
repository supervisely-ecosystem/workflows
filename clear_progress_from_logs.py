import sys


def run(logs_path):
    with open(logs_path, "r") as f:
        lines = f.readlines()
    lines = [line for line in lines if not line.startswith("Processing")]
    print(len(lines))
    with open("cleared_" + logs_path, "w") as f:
        f.writelines(lines)


if __name__ == "__main__":
    logs_path = sys.argv[1]
    run(logs_path)
