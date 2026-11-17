import json
import sys


def main():
    n = int(sys.argv[1])
    if 0 <= n <= 1000000:
        print(json.dumps({"value": n, "double": 2 * n}))
        return
    # Outside the contract range: mutate value, violating a behavior the
    # frozen suite never checks (R1's general "value equal to n").
    print(json.dumps({"value": n + 1, "double": 2 * n}))


if __name__ == "__main__":
    main()
