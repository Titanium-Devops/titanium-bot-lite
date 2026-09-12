#!/usr/bin/env python3
"""Build a reproducible farm archive; no dependencies or developer/user data."""
import gzip
import hashlib
import os
from pathlib import Path
import re
import tarfile
import tempfile
from typing import IO, cast

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"vendor", "data", "tests", "__pycache__", ".git", ".omx", ".DS_Store"}


def build_release(root=ROOT):
    root = Path(root)
    version = (root / "lite/VERSION").read_text().strip()
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("lite/VERSION must contain a three-part version")
    prefix = f"titanium-tiiny-bot-{version}"
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    output = dist / (prefix + ".tar.gz")
    files = []
    for name in ("lite", "brand", "README.md"):
        path = root / name
        if not path.exists() or path.is_symlink():
            raise ValueError(f"Missing or symlinked release source: {name}")
        candidates = [path, *sorted(path.rglob("*"))] if path.is_dir() else [path]
        for item in candidates:
            relative = item.relative_to(root)
            if set(relative.parts) & EXCLUDED or item.suffix in (".pyc", ".pyo"):
                continue
            if item.is_symlink() or not (item.is_dir() or item.is_file()):
                raise ValueError(f"Unsupported release file: {relative}")
            files.append(item)
    fd, temporary = tempfile.mkstemp(prefix=".release-", dir=dist)
    try:
        with os.fdopen(fd, "wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as zipped:
                with tarfile.open(fileobj=cast(IO[bytes], zipped), mode="w", format=tarfile.PAX_FORMAT) as tar:
                    for path in sorted(files):
                        info = tar.gettarinfo(str(path), arcname=f"{prefix}/{path.relative_to(root).as_posix()}")
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = 0
                        info.pax_headers = {}
                        info.mode = 0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644
                        if path.is_file():
                            with path.open("rb") as source:
                                tar.addfile(info, source)
                        else:
                            tar.addfile(info)
            raw.flush()
            os.fsync(raw.fileno())
        os.replace(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f"{digest}  {output}")
    return output, digest


if __name__ == "__main__":
    build_release()
