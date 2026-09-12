"""Fetch publisher's core export and verify expanded-file hashes."""

import argparse
import gzip
import hashlib
from pathlib import Path
import sys
import urllib.request


ROOT = Path(__file__).resolve().parent
BASE_URL = "https://collusion.wiki/explorer/download/"


def verify(data, expected, name):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"{name}: checksum mismatch; expected {expected}, got {actual}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    destination = ROOT / "data"
    if not args.verify_only:
        destination.mkdir(exist_ok=True)
    for line in (ROOT / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split()
        target = destination / name
        if args.verify_only or target.exists():
            verify(target.read_bytes(), expected, name)
        else:
            with urllib.request.urlopen(BASE_URL + name + ".gz", timeout=30) as response:
                data = gzip.decompress(response.read())
            verify(data, expected, name)
            pending = target.with_suffix(target.suffix + ".part")
            pending.write_bytes(data)
            pending.replace(target)
        print(f"Verified {name}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, EOFError) as error:
        print(f"Download/verification failed: {error}", file=sys.stderr)
        sys.exit(1)
