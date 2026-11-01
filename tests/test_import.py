"""Import from Scene Presets: saved scenes, own presets, scene entities with their IDs and areas."""

import json
import os
import shutil

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er

from .test_custom_presets import setup, userdata, ws  # noqa: F401  (fixture and helpers)

PRESET = "e71b2ef3-1b15-4c4b-b036-4b3d6efe58f8"
OLD_SCENES = [
    {"id": "aaa", "name": "Living room relax", "dynamic": False, "preset_id": PRESET,
     "targets": {"area_id": "living_room"}, "light_brightness": {"light.strip": 20}},
    {"id": "bbb", "name": "Living room aurora", "dynamic": True, "preset_id": PRESET,
     "targets": {"area_id": "living_room"}, "interval_min": 20, "interval_max": 60},
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def old_storage(hass_storage):
    hass_storage["scene_presets.saved_scenes"] = {
        "version": 1, "minor_version": 1, "key": "scene_presets.saved_scenes",
        "data": {"scenes": OLD_SCENES},
    }
    return hass_storage


@pytest.fixture
def old_custom(hass):
    """Own presets of Scene Presets (userdata/custom of the old integration)."""
    path = hass.config.path("custom_components", "scene_presets", "userdata", "custom")
    os.makedirs(os.path.join(path, "assets", "user"), exist_ok=True)
    with open(os.path.join(path, "presets.json"), "w", encoding="utf-8") as file:
        json.dump({"categories": [{"id": "c1", "name": "Mine"}],
                   "presets": [{"id": "p1", "categoryId": "c1", "name": "Beach", "img": "user/beach.jpg",
                                "bri": 200, "lights": [{"x": 0.3, "y": 0.3}]}]}, file)
    with open(os.path.join(path, "assets", "user", "beach.jpg"), "wb") as file:
        file.write(b"\xff\xd8\xff\xe0" + b"0" * 50)
    yield path
    shutil.rmtree(hass.config.path("custom_components", "scene_presets"), ignore_errors=True)


def old_entities(hass):
    """Scene entities of Scene Presets with an area, as Home Assistant has them in its registry."""
    area = ar.async_get(hass).async_create("Living room")
    registry = er.async_get(hass)
    old_entry = MockConfigEntry(domain="scene_presets", data={})
    old_entry.add_to_hass(hass)
    for scene, object_id in (("aaa", "living_room_relax"), ("bbb", "living_room_aurora")):
        entry = registry.async_get_or_create("scene", "scene_presets", f"saved_scene_{scene}",
                                             suggested_object_id=object_id, config_entry=old_entry)
        registry.async_update_entity(entry.entity_id, area_id=area.id, labels={"evening"} if scene == "aaa" else set())
    return area, old_entry


async def test_import_takes_over_entities(hass: HomeAssistant, hass_ws_client, monkeypatch, userdata, old_storage, old_custom):
    area, old_entry = old_entities(hass)
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)

    r = await ws(client, {"type": "scene_studio/import_status"})
    assert r["success"], r
    assert r["result"]["available"] and r["result"]["new_scenes"] == 2 and r["result"]["custom_files"] == 2

    result = await hass.services.async_call("scene_studio", "import_scene_presets", {}, blocking=True, return_response=True)
    await hass.async_block_till_done()
    assert result["scenes"] == 2 and result["entities"] == 2 and result["custom_files"] == 2

    registry = er.async_get(hass)
    for entity_id in ("scene.living_room_relax", "scene.living_room_aurora"):
        entry = registry.async_get(entity_id)
        assert entry is not None and entry.platform == "scene_studio", entity_id
        assert entry.area_id == area.id
        assert hass.states.get(entity_id) is not None
    assert registry.async_get("scene.living_room_relax").labels == {"evening"}
    assert not [e for e in registry.entities.values() if e.platform == "scene_presets"]
    assert hass.config_entries.async_get_entry(old_entry.entry_id).disabled_by is not None

    # scenes keep their IDs and settings
    store = hass.data["scene_studio"]["saved_scenes"]
    assert store.get("aaa")["light_brightness"] == {"light.strip": 20}
    assert store.get("bbb")["interval_min"] == 20
    assert hass.states.get("scene.living_room_relax").attributes["saved_scene_id"] == "aaa"

    # own presets and their pictures
    assert any(p["id"] == "p1" for p in userdata.PRESET_DATA["presets"])
    assert os.path.exists(os.path.join(userdata.CUSTOM_DIR, "assets", "user", "beach.jpg"))

    # a second import brings nothing new
    result = await hass.services.async_call("scene_studio", "import_scene_presets", {}, blocking=True, return_response=True)
    assert result["scenes"] == 0 and result["skipped"] == 2
    r = await ws(client, {"type": "scene_studio/import_status"})
    assert not r["result"]["available"]


async def test_import_without_taking_over(hass: HomeAssistant, hass_ws_client, monkeypatch, userdata, old_storage):
    _area, old_entry = old_entities(hass)
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)

    r = await ws(client, {"type": "scene_studio/import", "take_over_entities": False})
    assert r["success"], r
    await hass.async_block_till_done()
    assert r["result"]["scenes"] == 2 and r["result"]["entities"] == 0

    registry = er.async_get(hass)
    # Scene Presets keeps its entities and stays enabled, Scene Studio gets its own
    assert registry.async_get("scene.living_room_relax").platform == "scene_presets"
    assert hass.config_entries.async_get_entry(old_entry.entry_id).disabled_by is None
    assert registry.async_get_entity_id("scene", "scene_studio", "saved_scene_aaa") is not None


async def test_nothing_to_import(hass: HomeAssistant, hass_ws_client, monkeypatch, userdata):
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)
    r = await ws(client, {"type": "scene_studio/import_status"})
    assert r["success"] and not r["result"]["available"] and r["result"]["scenes"] == 0
