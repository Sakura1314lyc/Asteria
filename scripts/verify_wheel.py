from __future__ import annotations

import argparse
import sys
from pathlib import Path
from zipfile import ZipFile


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that a wheel contains exactly the current Web build."
    )
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    source_root = repository / "src" / "paper_agent" / "web_dist"
    source_files = {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if path.is_file()
    }
    if not source_files:
        parser.error("web_dist is empty; run `pnpm --dir web build` first")

    wheel = args.wheel.resolve()
    if not wheel.is_file() or wheel.suffix != ".whl":
        parser.error(f"wheel does not exist: {wheel}")

    prefix = "paper_agent/web_dist/"
    with ZipFile(wheel) as archive:
        wheel_files = {
            name.removeprefix(prefix)
            for name in archive.namelist()
            if name.startswith(prefix) and not name.endswith("/")
        }

    missing = sorted(source_files - wheel_files)
    stale = sorted(wheel_files - source_files)
    if missing or stale:
        if missing:
            print("Missing Web files:", *missing, sep="\n  ", file=sys.stderr)
        if stale:
            print("Stale Web files:", *stale, sep="\n  ", file=sys.stderr)
        print(
            "Wheel does not match src/paper_agent/web_dist. "
            "Clear or archive build/lib, rebuild, and verify again.",
            file=sys.stderr,
        )
        return 1

    print(f"Wheel Web bundle verified: {len(wheel_files)} files match source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
