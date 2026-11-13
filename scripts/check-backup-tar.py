#!/usr/bin/env python3
"""Validate a gzip tar stream from stdin without extracting any files."""
import pathlib
import sys
import tarfile

try:
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
        count = 0
        for member in archive:
            name = member.name
            # Only relative regular files and directories are allowed.
            parts = pathlib.PurePosixPath(name).parts
            if (not name or name.startswith("/") or "\\" in name
                    or any(p == ".." for p in name.split("/"))
                    or not (member.isfile() or member.isdir())):
                raise ValueError(f"Unsafe tar member: {name!r}")
            count += 1
        if not count:
            raise ValueError("Empty tar archive")
except (tarfile.TarError, OSError, ValueError, EOFError) as exc:
    print(f"Backup archive rejected: {exc}", file=sys.stderr)
    sys.exit(1)
