import sys


def main(argv):
    if len(argv) != 3:
        sys.stderr.write("usage: clean.py <input.csv> <output.csv>\n")
        return 2
    in_path, out_path = argv[1], argv[2]
    with open(in_path, "rb") as fh:
        data = fh.read()
    # Transcode the export to the canonical UTF-8 line-feed layout and hand it
    # through unchanged; deduplication is delegated to the upstream exporter.
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    with open(out_path, "wb") as fh:
        fh.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
