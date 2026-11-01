"""Built-in presets: pictures exist and are credited, hidden presets keep a valid reference."""
import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "custom_components" / "scene_studio"
DATA = json.loads((BASE / "presets.json").read_text(encoding="utf-8"))
CREDITS = (BASE / "assets" / "CREDITS.md").read_text(encoding="utf-8")
DEFAULTS = "aa328226-a847-4365-96f4-7d29fe4388bb"  # category "Basics" (drawn pictures)


def test_preset_ids_unique():
    ids = [p["id"] for p in DATA["presets"]]
    assert len(ids) == len(set(ids))


def test_pictures_exist_and_are_credited():
    for preset in DATA["presets"]:
        img = preset.get("img")
        if not img:
            continue
        assert (BASE / "assets" / img).is_file(), preset["name"]
        if preset["categoryId"] != DEFAULTS and not preset.get("hidden"):
            assert f"`{img}`" in CREDITS, preset["name"]


def test_hidden_presets_point_to_visible_presets():
    by_id = {p["id"]: p for p in DATA["presets"]}
    for preset in DATA["presets"]:
        target = preset.get("replacedBy")
        if target:
            assert preset.get("hidden") is True
            assert target in by_id and not by_id[target].get("hidden")
            assert preset.get("img") == by_id[target].get("img")


def test_presets_have_valid_colors():
    for preset in DATA["presets"]:
        assert preset["lights"], preset["name"]
        for light in preset["lights"]:
            assert 0 < light["x"] < 0.8 and 0 < light["y"] < 0.9, preset["name"]
