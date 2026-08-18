from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from flash2scratch.ffdec import FFDecError, _safe_extract, _select_portable_asset


def test_selects_standard_portable_ffdec_zip():
    release = {
        "assets": [
            {
                "name": "ffdec_lib_99.0.0.zip",
                "browser_download_url": "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version99.0.0/ffdec_lib_99.0.0.zip",
            },
            {
                "name": "ffdec_99.0.0_macosx.zip",
                "browser_download_url": "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version99.0.0/ffdec_99.0.0_macosx.zip",
            },
            {
                "name": "ffdec_99.0.0.zip",
                "browser_download_url": "https://github.com/jindrapetrik/jpexs-decompiler/releases/download/version99.0.0/ffdec_99.0.0.zip",
            },
        ]
    }

    name, url = _select_portable_asset(release)
    assert name == "ffdec_99.0.0.zip"
    assert url.endswith("/ffdec_99.0.0.zip")


def test_rejects_non_official_release_download_url():
    release = {
        "assets": [
            {
                "name": "ffdec_99.0.0.zip",
                "browser_download_url": "https://example.com/ffdec_99.0.0.zip",
            }
        ]
    }

    with pytest.raises(FFDecError):
        _select_portable_asset(release)


def test_safe_extract_rejects_parent_traversal(tmp_path: Path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", "nope")

    with pytest.raises(FFDecError):
        _safe_extract(archive, tmp_path / "out")
