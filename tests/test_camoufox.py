"""Simple smoke tests for the Camoufox integration helpers."""

# ensure the repo root is on sys.path so `import utils` works in tests
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


def test_import_camoufox_helpers():
    # module should import and expose expected names
    from utils import camoufox

    assert hasattr(camoufox, "camoufox_fetch_anchors"), "helper missing"
    assert hasattr(camoufox, "camoufox_cli_path"), "CLI helper missing"
    assert hasattr(camoufox, "camoufox_launch_server"), "server helper missing"


def test_cli_path_returns_string():
    from utils.camoufox import camoufox_cli_path

    path = camoufox_cli_path()
    assert isinstance(path, str) and path.strip(), "expected nonempty CLI path"


def test_fetch_anchors_raises_when_no_backend(monkeypatch, tmp_path):
    # force environment into "no backend" by clearing endpoint and simulating
    # absence of package and CLI.
    monkeypatch.delenv("CAMOUFOX_ENDPOINT", raising=False)

    # make `shutil.which` return None so CLI fallback fails
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)

    # pretend the package import always fails
    monkeypatch.setattr("utils.camoufox.Camoufox", None, raising=False)

    from utils.camoufox import camoufox_fetch_anchors

    with pytest.raises(RuntimeError):
        camoufox_fetch_anchors("https://example.com")
