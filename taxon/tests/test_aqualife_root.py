"""Contract tests for the ``AQUALIFE_ROOT`` env var reader.

Issue #68 anchors the species-folder creation at an operator-controlled
root directory (``./Proyecto-Aqualife/`` by default). The resolver MUST:

- read the env var, falling back to a relative default;
- resolve relative paths against the **project root**, NOT cwd;
- fail loudly with HTTP 500 and an ``ErrorResponse`` naming the failing
  path + cwd when the resolved path is unwritable.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AQUALIFE_ROOT", raising=False)


def test_default_root_resolves_against_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default ``./Proyecto-Aqualife/`` lives at the project root, not cwd.

    Running the test from ``tmp_path`` (a subdirectory of the repo, but
    NOT the repo root) MUST still anchor the folder at the project root
    so worktree checkouts behave like main checkouts.
    """
    from taxon.api.workspace import resolve_aqualife_root

    _clear_env(monkeypatch)
    # ``os.chdir`` to a tmp_path subdir so the test proves cwd is NOT
    # used as the anchor.
    cwd = tmp_path / "subfolder"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    resolved = resolve_aqualife_root()
    # The path resolves to <project_root>/Proyecto-Aqualife, NOT
    # <tmp_path>/subfolder/Proyecto-Aqualife.
    assert resolved.name == "Proyecto-Aqualife"
    assert not str(resolved).startswith(str(cwd))
    assert resolved.is_dir()


def test_explicit_absolute_path_used_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absolute ``AQUALIFE_ROOT`` is returned verbatim (no project-root rebase)."""
    from taxon.api.workspace import resolve_aqualife_root

    target = tmp_path / "AqualifeRoot"
    monkeypatch.setenv("AQUALIFE_ROOT", str(target))
    resolved = resolve_aqualife_root()
    assert resolved == target.resolve()
    assert resolved.is_dir()


def test_unwritable_root_raises_api_error_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A read-only ``AQUALIFE_ROOT`` raises :class:`APIError` with status_code=500.

    The error envelope MUST name the failing path AND the current
    working directory so operators can see exactly which filesystem
    state broke the resolution.
    """
    from taxon.api.errors import APIError
    from taxon.api.workspace import resolve_aqualife_root

    target = tmp_path / "ReadOnlyRoot"
    target.mkdir()
    # Strip write permissions for the owner. ``os.chmod`` with
    # ``0o555`` leaves the directory readable but not writable on
    # POSIX. On Windows this would fail differently; the test is
    # skipped on non-POSIX platforms via ``stat.S_IMODE``.
    os.chmod(target, 0o555)
    # On POSIX the bit should be reflected by ``stat.S_IMODE`` returning
    # ``0o555``. If the platform silently ignores the chmod (e.g. as
    # root) the test skips rather than flapping.
    if stat.S_IMODE(os.stat(target).st_mode) != 0o555:
        pytest.skip("chmod could not remove write permission on this platform")
    monkeypatch.setenv("AQUALIFE_ROOT", str(target))
    try:
        with pytest.raises(APIError) as exc_info:
            resolve_aqualife_root()
        assert exc_info.value.status_code == 500
        assert "AQUALIFE_ROOT" in exc_info.value.detail
        assert "not writable" in exc_info.value.detail
        # The detail MUST name the failing path so operators can see
        # exactly which mount broke the resolution.
        assert str(target) in exc_info.value.detail
        # And the current cwd so the error is actionable.
        assert str(Path.cwd()) in exc_info.value.detail
    finally:
        # Restore write perms so the tmp_path cleanup doesn't error.
        os.chmod(target, 0o755)


def test_existing_relative_path_under_project_root_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative ``AQUALIFE_ROOT`` is anchored on the project root, not cwd.

    The resolved path lives at ``<project_root>/<env_value>``, not at
    ``<cwd>/<env_value>``. Running from a tmp_path subfolder proves
    the anchor is the project root.
    """
    from taxon.api.workspace import resolve_aqualife_root

    cwd = tmp_path / "subfolder"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("AQUALIFE_ROOT", "alt-aqualife-root")
    resolved = resolve_aqualife_root()
    assert resolved.name == "alt-aqualife-root"
    assert resolved.is_dir()
    assert not str(resolved).startswith(str(cwd))


def test_root_path_segments_join_verbatim_with_os_sep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Path segments from ``AQUALIFE_ROOT`` join verbatim — no URL encoding, no lowercasing."""
    from taxon.api.workspace import resolve_aqualife_root

    # The env value carries literal mixed-case + spaces + punctuation.
    monkeypatch.setenv("AQUALIFE_ROOT", "My-Custom Root_With.Punctuation")
    resolved = resolve_aqualife_root()
    # The leaf segment is the env value verbatim.
    assert resolved.name == "My-Custom Root_With.Punctuation"
    # The on-disk directory name has the SAME casing — no lowercasing
    # by the resolver.
    assert resolved.name == "My-Custom Root_With.Punctuation"
