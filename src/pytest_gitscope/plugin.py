from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from .diff import get_changed_files
from .selector import Resolver, Selector

POST_REPORT_KEY: pytest.StashKey[str] = pytest.StashKey()
REVISION_KEY: pytest.StashKey[str] = pytest.StashKey()
USE_SHORT_CIRCUIT_KEY: pytest.StashKey[bool] = pytest.StashKey()
INCLUDED_MODULES_KEY: pytest.StashKey[set[str]] = pytest.StashKey()
SUPPRESS_NO_TESTS_COLLECTED: pytest.StashKey[bool] = pytest.StashKey()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("collect", "collection")
    group.addoption("--gitscope", help="Select tests based on git revision")
    group.addoption(
        "--gitscope-no-short-circuits",
        action="store_true",
        default=False,
        help="Do not use the short circuits",
    )

    group.addoption(
        "--gitscope-include-module",
        action="append",
        metavar="MODULE",
        help="Include tests that depends on this module and its submodules",
    )

    # Let user register custom short circuit files
    parser.addini(
        "gitscope_short_circuits",
        "list of (relative) glob-style paths to be used for short circuit.",
        type="paths",
        default=default_short_circuit_files(),
    )


def pytest_configure(config: pytest.Config):
    if rev := config.getoption("--gitscope"):
        config.stash[REVISION_KEY] = rev
        config.stash[USE_SHORT_CIRCUIT_KEY] = not config.getoption(
            "--gitscope-no-short-circuits"
        )
        config.stash[INCLUDED_MODULES_KEY] = set(
            config.getoption("--gitscope-include-module") or []
        )


def pytest_report_header(config: pytest.Config, start_path: Any) -> str | None:
    if rev := config.stash.get(REVISION_KEY, None):
        return f"gitscope: Analyzing changes from {rev}"
    else:
        return None


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not items:
        return
    rev = config.stash.get(REVISION_KEY, None)
    if rev is None:
        return

    root = session.startpath
    changed_files = get_changed_files(root, before=rev)

    if not changed_files:
        return

    # Track changes of short circuit files. if a short circuit is changed, then short circuit the whole thing
    # This kind of file usually declares dependencies that are difficult to inspect
    if config.stash.get(USE_SHORT_CIRCUIT_KEY, True) and (
        short_circuit_files := unfold_files(
            root, config.getini("gitscope_short_circuits")
        )
    ):
        if matched_short_circuit_files := changed_files & short_circuit_files:
            # A file that may declare some external dependencies have been changed.
            # it safer to not try to filter
            config.stash[POST_REPORT_KEY] = (
                "The pytest-gitscope plugin won't try to deselect some tests, "
                f"because these files ({', '.join(sorted(map(str, matched_short_circuit_files)))}) have been changed since {rev}"
            )
            return

    # Track changes of conftest.py files. if a conftest.py is changed, then short circuit the whole thing
    changed_conftest_files = {
        changed_file
        for changed_file in changed_files
        if changed_file.name in ["conftest.py"]
    }
    if changed_conftest_files:
        # Some conftest.py have been changed.
        # it safer to not try to filter
        config.stash[POST_REPORT_KEY] = (
            "The pytest-gitscope plugin won't try to deselect some tests, "
            f"because it cannot detect changes introduced into ({', '.join(sorted(map(str, changed_conftest_files)))}) since {rev}"
        )
        return

    selector = Selector(
        changed_files=changed_files,
        resolver=Resolver.from_modules(root=root, modules=sys.modules),
        included_modules=config.stash[INCLUDED_MODULES_KEY],
    )

    # those will be our bases
    test_files = {item.path.relative_to(root) for item in items}
    test_dirs: set[Path] = set()
    for test_file in test_files:
        test_dirs.update(test_file.parents)

    # Track dependencies' changes into conftest.py files. if a conftest.py is affected by a dependency change, then short circuit the whole thing
    conftest_files = {
        conftest_file
        for test_dir in test_dirs
        if (conftest_file := test_dir / "conftest.py") and conftest_file.exists()
    }

    affected_conftest_files = selector.select_files(target_files=conftest_files)
    if affected_conftest_files:
        # Some conftest.py files have been affected by changes.
        # Because they do declare fixtures, it is safer to not try to filter
        config.stash[POST_REPORT_KEY] = (
            "The pytest-gitscope plugin won't try to deselect some tests, "
            f"because file ({', '.join(sorted(map(str, affected_conftest_files)))}) have been affected by dependency changes since {rev}"
        )
        return

    affected_test_files = selector.select_files(target_files=test_files)

    remaining = []
    deselected = []
    for item in items:
        if item.path.relative_to(root) in affected_test_files:
            remaining.append(item)
        else:
            deselected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining
        config.stash[POST_REPORT_KEY] = (
            "Some tests have been deselected by pytest-gitscope plugin, "
            f"because they have not been affected by the changes from {rev}"
        )
        config.stash[SUPPRESS_NO_TESTS_COLLECTED] = not remaining


def pytest_report_collectionfinish(
    config: pytest.Config, start_path: Any, startdir: Any, items: Any
) -> str | list[str]:
    if data := config.stash.get(POST_REPORT_KEY, default=None):
        return data
    return []


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: pytest.ExitCode):
    if (exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED) and session.config.stash.get(
        SUPPRESS_NO_TESTS_COLLECTED, default=False
    ):
        session.exitstatus = pytest.ExitCode.OK


def default_short_circuit_files():
    return {
        Path("pyproject.toml"),
        Path("requirements.txt"),
        Path("poetry.lock"),
        Path("uv.lock"),
        Path("pylock.toml"),
        Path("Pipfile.lock"),
        Path("Pipfile"),
        Path("pdm.lock"),
        Path("setup.cfg"),
        Path("setup.py"),
        Path("requirements.in"),
        Path("pytest.ini"),
    }


def unfold_files(root: Path, custom_paths: list[Path] | None) -> set[Path]:
    unfolded_files: set[Path] = set()
    if custom_paths:
        for custom_path in custom_paths:
            if root in custom_path.parents:
                custom_path = custom_path.relative_to(root)
            if "*" in str(custom_path):
                unfolded_files.update(Path().glob(str(custom_path)))
            else:
                unfolded_files.add(custom_path)
    return unfolded_files
