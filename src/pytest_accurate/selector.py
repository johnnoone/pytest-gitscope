from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from functools import cache
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType
from typing import Self


@dataclass
class ModulesRegistry:
    root: Path
    by_fullnames: dict[str, Path | None] = field(default_factory=dict)

    @classmethod
    def from_modules(cls, root: Path, modules: dict[str, ModuleType]) -> Self:
        by_fullnames: dict[str, Path | None] = {}
        for name, module in modules.items():
            if (
                (filepath := getattr(module, "__file__", None))
                and (file := Path(filepath))
                and root in file.parents
            ):
                file = file.relative_to(root)
                by_fullnames[name] = file
            else:
                by_fullnames[name] = None
        return cls(root=root, by_fullnames=by_fullnames)

    def __post_init__(self) -> None:
        self.inverse = {
            val: key for key, val in self.by_fullnames.items() if val is not None
        }

    def get_name(self, file: Path) -> str | None:
        return self.inverse.get(file)

    def get(self, name: str) -> Path | None:
        if name not in self.by_fullnames:
            # in case of name not already present into cache, fallback to importlib.util.find_spec
            file: Path | None
            try:
                spec = find_spec(name)
            except ModuleNotFoundError:
                file = self.by_fullnames[name] = None
            else:
                if (
                    spec
                    and spec.origin
                    and (tmp := Path(spec.origin))
                    and (self.root in tmp.parents)
                ):
                    file = self.by_fullnames[name] = tmp.relative_to(self.root)
                else:
                    file = self.by_fullnames[name] = None
            return file
        return self.by_fullnames.get(name)


def select_files(
    target_files: set[Path],
    changed_files: set[Path],
    modules_registry: ModulesRegistry,
) -> set[Path]:
    selection = target_files & changed_files
    target_files = target_files - selection

    if not target_files:
        # we already took everything
        return selection

    queued: dict[Path, set[tuple[str, Path]]] = {}

    for target_file in list(target_files):
        test_package = modules_registry.get_name(target_file)
        acc = set()
        for dep_fullname in list_dependencies(target_file, package=test_package):
            dep_file = modules_registry.get(dep_fullname)
            if dep_file in changed_files:
                target_files.discard(target_file)
                selection.add(target_file)
                break
            elif dep_file:
                acc.add((dep_fullname, dep_file))
        if acc:
            # find recursively
            queued[target_file] = acc

    explored: dict[Path, set[Path]] = defaultdict(set)
    for _ in range(100):
        tmp, queued = queued.items(), {}
        for target_file, dependencies in tmp:
            if target_file in selection:
                # already done
                continue

            acc = set()
            for dep_fullname, dep_file in dependencies:
                if dep_file in explored[target_file]:
                    continue
                for sub_fullname in list_dependencies(dep_file, package=dep_fullname):
                    if sub_file := modules_registry.get(sub_fullname):
                        if sub_file in changed_files:
                            target_files.discard(target_file)
                            selection.add(target_file)
                            break
                        elif sub_file in explored[target_file]:
                            continue
                        else:
                            acc.add((sub_fullname, sub_file))
                explored[target_file].add(dep_file)
            if acc and target_file not in selection:
                # find recursively
                queued[target_file] = acc

        if not queued:
            break
    else:
        raise RecursionError("Too many recursion")

    return selection


@cache
def list_dependencies(file: Path, package: str | None = None) -> set[str]:
    if package:
        parts: list[str] = package.split(".")
    else:
        # guess a package from file. because it is relative to root, it should be safe
        parts = file.with_suffix("").__str__().split("/")

    dependencies: set[str] = set()
    source = file.read_text()
    tree = ast.parse(source, file)
    for node in ast.walk(tree):
        match node:
            case ast.Import(names):
                for name in names:
                    dependencies.add(name.name)
            case ast.ImportFrom(str(module), names, level):
                if level:
                    assert len(parts) >= level
                    prefix = ".".join(parts[-level:]) + "." + module + "."
                else:
                    prefix = module + "."
                for name in names:
                    dependencies.add(prefix + name.name)
            case ast.ImportFrom(None, names, level):
                assert len(parts) >= level
                prefix = ".".join(parts[-level:]) + "."
                for name in names:
                    dependencies.add(prefix + name.name)

    for dependency in list(dependencies):
        while "." in dependency:
            dependency, *_ = dependency.rpartition(".")
            dependencies.add(dependency)
    return dependencies
