import json
import sys


def main():
    n = int(sys.argv[1])
    if n < 1000000:
        print(json.dumps({"value": n, "double": 2 * n}))
        return
    # Upper boundary of the declared input range: double is off by two.
    print(json.dumps({"value": n, "double": 2 * n + 2}))


if __name__ == "__main__":
    main()
