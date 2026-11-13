#!/usr/bin/env python3
"""Validate a gzip tar stream from stdin without extracting any files."""
import sys
import tarfile

try:
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
        count = 0
        seen = set()
        for member in archive:
            name = member.name
            # Only relative regular files and directories are allowed.
            if (not name or name.startswith("/") or "\\" in name
                    or any(p == ".." for p in name.split("/"))
                    or not (member.isfile() or member.isdir())):
                raise ValueError(f"Unsafe tar member: {name!r}")
            canonical = name.rstrip('/')
            if canonical in seen:
                raise ValueError(f"Duplicate tar member: {name!r}")
            seen.add(canonical)
            count += 1
        if not count:
            raise ValueError("Empty tar archive")
except (tarfile.TarError, OSError, ValueError, EOFError) as exc:
    print(f"Backup archive rejected: {exc}", file=sys.stderr)
    sys.exit(1)
