from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_package_metadata_uses_devflow_readme() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["name"] == "devflow"
    assert pyproject["project"]["readme"] == "README.md"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("# DevFlow\n")
    assert "docs/DEVFLOW_SOURCE_OF_TRUTH.md" in readme


def test_release_artifacts_describe_versioning_and_state_compatibility() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")

    assert "semantic versioning" in changelog
    assert "State compatibility" in changelog
    assert "No public release artifact has been published yet." in changelog
    assert "python -m build" in checklist
    assert "python -m twine check dist/*" in checklist
    assert "state-shape change" in checklist


def test_declared_license_and_attribution_files_exist() -> None:
    assert "MIT License" in (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Superpowers" in (ROOT / "ATTRIBUTION.md").read_text(encoding="utf-8")
