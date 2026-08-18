from pathlib import Path


def test_static_analysis_config_exists() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "pyproject.toml").is_file()
    assert (root / ".pre-commit-config.yaml").is_file()
    assert (root / ".github/workflows/static-analysis.yml").is_file()


def test_suggested_layout_exists() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "scripts/system/cec_startkodi_on_poweron.py").is_file()
