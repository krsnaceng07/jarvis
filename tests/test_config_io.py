import json
import os
from pathlib import Path

from src.config.io import create_config_io, parse_config_json5


def test_parse_json5_fallback(tmp_path):
    raw = '{\n  // comment\n  "a": 1,\n  "b": [1,2,],\n}'
    parsed = parse_config_json5(raw)
    assert parsed["a"] == 1
    assert parsed["b"] == [1, 2]


def test_create_config_io_read_write(tmp_path, monkeypatch):
    cfg_file = tmp_path / "jarvis.json"
    cfg = {"x": 1}
    # create facade pointing to tmp file
    io = create_config_io(config_path=str(cfg_file), env={})
    io.writeConfigFile(cfg)
    assert cfg_file.exists()
    read = io.readConfigFileSnapshot()
    assert read["config"]["x"] == 1
    assert isinstance(read["raw"], str)
