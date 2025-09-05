import subprocess
from os import PathLike
from pathlib import Path


def get_changed_files(
    base: PathLike[str] = Path("."), *, before: str | None = "main"
) -> set[Path]:
    command: list = [
        "git",
        "-C",
        base,
        "diff",
        "--name-only",
        "--diff-filter=dt",
        before,
    ]
    result = subprocess.run(command, capture_output=True, check=True)
    return {Path(p) for p in result.stdout.decode().strip().split()}


def get_py_files(base: PathLike[str] = Path(".")) -> set[Path]:
    """List python files that are tracked or trackable by the repository"""
    command: list = [
        "git",
        "-C",
        base,
        "ls-files",
        "-mco",
        "--exclude-standard",
    ]
    result = subprocess.run(command, capture_output=True, check=True)
    acc = set()
    for p in result.stdout.decode().strip().split():
        path = Path(p)
        if path.suffix == [".py"]:
            acc.add(path)
    return acc
