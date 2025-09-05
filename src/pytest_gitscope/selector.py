from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import cache
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType
from typing import NamedTuple, Self, TypeAlias

Name: TypeAlias = str


class Module(NamedTuple):
    name: Name
    file: Path | None


@dataclass
class Resolver:
    root: Path
    by_names: dict[Name, Path | None] = field(default_factory=dict)
    by_files: dict[Path, Name] = field(default_factory=dict)

    @classmethod
    def from_modules(cls, root: Path, modules: dict[str, ModuleType]) -> Self:
        by_names: dict[Name, Path | None] = {}
        by_files: dict[Path, Name] = {}
        for name, module in modules.items():
            if (
                (filepath := getattr(module, "__file__", None))
                and (file := Path(filepath))
                and root in file.parents
            ):
                file = file.relative_to(root)
                by_names[name] = file
                by_files[file] = name
            else:
                by_names[name] = None
        return cls(root=root, by_names=by_names, by_files=by_files)

    def __post_init__(self) -> None:
        self.infer_dependencies = cache(self.infer_dependencies)  # type: ignore[method-assign]
        self.get_module = cache(self.get_module)  # type: ignore[method-assign]
        self.venv_root = self.root / ".venv"

    def get_module_by_file(self, file: Path) -> Module | None:
        if name := self.by_files.get(file):
            return Module(name, file)
        else:
            return None

    def get_module(self, name: str) -> Module | None:
        try:
            file = self.by_names[name]
            return Module(name, file)
        except KeyError:
            pass

        # Fetch from find_spec
        try:
            spec = find_spec(name)
        except ModuleNotFoundError:
            return None

        if spec:
            if (
                spec.origin
                and (file := Path(spec.origin))
                and file.suffix in (".py",)  # For now handle only python files
                and (self.root in file.parents)
                and (self.venv_root not in file.parents)  # Eliminate virtualenv folders
            ):
                file = file.relative_to(self.root)
            else:
                file = None
            return Module(name, file)
        return None

    def infer_dependencies(self, mod: Module) -> set[Name]:
        dependency_names: set[str] = set()
        if not mod.file:
            return dependency_names

        try:
            source = mod.file.read_text()
        except Exception as error:
            error.add_note(f"Current file {mod.file} is expected to be a dependency")
            error.add_note(f"Dependency name is {mod.name}")
            raise error

        parts = tuple(mod.name.split("."))
        tree = ast.parse(source, filename=mod.file)
        for node in ast.walk(tree):
            match node:
                case ast.Import(names):
                    for name in names:
                        dependency_names.add(name.name)
                case ast.ImportFrom(None, names, level):
                    assert len(parts) >= level
                    for name in names:
                        dependency_names.add(".".join(parts[-level:] + (name.name,)))
                case ast.ImportFrom(str(module), names, 0):
                    for name in names:
                        dependency_names.add(".".join((module, name.name)))
                case ast.ImportFrom(str(module), names, level):
                    assert len(parts) >= level
                    for name in names:
                        dependency_names.add(
                            ".".join(parts[-level:] + (module, name.name))
                        )

        for dependency_name in list(dependency_names):
            while "." in dependency_name:
                dependency_name, *_ = dependency_name.rpartition(".")
                dependency_names.add(dependency_name)
        return dependency_names

    def match(self, mod: Module, *, files: set[Path], modules: set[Name]) -> bool:
        if mod.name in modules:
            return True
        if mod.file in files:
            return True
        resolved: set[Name] = {mod.name}
        queue = [mod]
        while queue:
            mods, queue = queue, []
            for mod in mods:
                for dependency_name in self.infer_dependencies(mod) - resolved:
                    resolved.add(mod.name)
                    if dependency_name in modules:
                        return True
                    if dependency := self.get_module(name=dependency_name):
                        if dependency.file in files:
                            return True
                        queue.append(dependency)
        return False


@dataclass
class Selector:
    changed_files: set[Path]
    resolver: Resolver
    included_modules: set[Name]

    def select_files(self, target_files: set[Path]) -> set[Path]:
        selection = target_files & self.changed_files
        target_files = target_files - selection

        if not target_files:
            # we already took everything
            return selection

        for target_file in target_files:
            if mod := self.resolver.get_module_by_file(target_file):
                if self.resolver.match(
                    mod, files=self.changed_files, modules=self.included_modules
                ):
                    selection.add(target_file)
        return selection
