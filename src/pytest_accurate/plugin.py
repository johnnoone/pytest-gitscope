from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

import pytest

from .diff import get_changed_files
from .selector import select_files

POST_REPORT: WeakKeyDictionary[pytest.Config, str] = WeakKeyDictionary()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("collect", "collection")
    group.addoption("--gitscope", help="Select tests based on git revision")


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not items:
        return
    rev = config.getoption("--gitscope")
    if rev is None:
        return

    root = session.startpath
    changed_files = get_changed_files(root, before=rev)

    short_circuit_files = changed_files & {
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
    if short_circuit_files:
        # A file that may declare some external dependencies have been changed.
        # it safer to not try to filter
        POST_REPORT[config] = (
            "The pytest-gitscope plugin won't try to deselect some tests, "
            f"because these files ({', '.join(sorted(map(str, short_circuit_files)))}) have been changed since {rev}"
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
        POST_REPORT[config] = (
            "The pytest-gitscope plugin won't try to deselect some tests, "
            f"because it cannot detect changes introduced into ({', '.join(sorted(map(str, changed_conftest_files)))}) since {rev}"
        )
        return

    # Track dependencies' changes into conftest.py files. if a conftest.py is affected by a dependency change, then short circuit the whole thing
    conftest_files = {file.relative_to(root) for file in root.glob("**/conftest.py")}
    affected_conftest_files = select_files(
        root=root,
        target_files=conftest_files,
        changed_files=changed_files,
        modules=sys.modules.copy(),
    )
    if affected_conftest_files:
        # Some conftest.py files have been affected by changes.
        # Because they do declare fixtures, it is safer to not try to filter
        POST_REPORT[config] = (
            "The pytest-gitscope plugin won't try to deselect some tests, "
            f"because file ({', '.join(sorted(map(str, affected_conftest_files)))}) have been affected by dependency changes since {rev}"
        )
        return

    test_files = {item.path.relative_to(root) for item in items}

    affected_test_files = select_files(
        root=root,
        target_files=test_files,
        changed_files=changed_files,
        modules=sys.modules.copy(),
    )

    remaining = []
    deselected = []
    for item in items:
        if item.path.relative_to(root) not in affected_test_files:
            remaining.append(item)
        else:
            deselected.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining
        POST_REPORT[config] = (
            "Some tests have been deselected by pytest-gitscope plugin, "
            f"because they have not been affected by the changes from {rev}"
        )


def pytest_report_collectionfinish(
    config: pytest.Config, start_path: Any, startdir: Any, items: Any
) -> str | list[str]:
    if data := POST_REPORT.get(config):
        return data
    return []
