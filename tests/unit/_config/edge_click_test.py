from pathlib import Path

import pytest

from labelme import _config


def test_legacy_config_defaults_to_plain_edge_click(*, tmp_path: Path) -> None:
    path = tmp_path / ".labelmerc"
    path.write_text("auto_save: false\n", encoding="utf-8")
    config = _config.load_config(config_file=path, config_overrides={})
    assert config["canvas"]["add_point_on_edge_without_alt"] is True


@pytest.mark.parametrize("value", [True, False])
def test_edge_click_override_round_trips(*, tmp_path: Path, value: bool) -> None:
    path = tmp_path / ".labelmerc"
    _config.set_overrides(
        config_file=path,
        overrides=[(("canvas", "add_point_on_edge_without_alt"), value)],
    )
    config = _config.load_config(config_file=path, config_overrides={})
    assert config["canvas"]["add_point_on_edge_without_alt"] is value


@pytest.mark.parametrize("value", [None, "false", "true", 0, 1, [], {}])
def test_edge_click_rejects_non_boolean_values(*, value: object) -> None:
    with pytest.raises(ValueError, match="must be true or false"):
        _config.load_config(
            config_file=None,
            config_overrides={"canvas": {"add_point_on_edge_without_alt": value}},
        )
