"""Presets created in the panel and replaced preset images (websocket commands)."""

import base64
import json
import os
import shutil

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 200).decode()
COLORS = [{"x": 0.3, "y": 0.3}, {"x": 0.6, "y": 0.35}]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def userdata():
    """Empty userdata folder for every test, the real one is restored afterwards."""
    import custom_components.scene_studio.file_utils as fu

    backup = fu.CUSTOM_DIR + ".testbackup"
    if os.path.exists(fu.CUSTOM_DIR):
        shutil.move(fu.CUSTOM_DIR, backup)
    os.makedirs(os.path.join(fu.CUSTOM_DIR, "assets"))
    fu.reload_preset_data()
    yield fu
    shutil.rmtree(fu.CUSTOM_DIR)
    if os.path.exists(backup):
        shutil.move(backup, fu.CUSTOM_DIR)
    fu.reload_preset_data()


async def setup(hass, monkeypatch):
    import custom_components.scene_studio as sp

    async def no_view(hass):
        return None

    monkeypatch.setattr(sp, "async_setup_view", no_view)  # needs the http server
    entry = MockConfigEntry(domain="scene_studio", data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def runtime(hass):
    """Runtime data of the loaded config entry."""
    from custom_components.scene_studio.data import find_data

    return find_data(hass)


async def ws(client, msg):
    await client.send_json_auto_id(msg)
    return await client.receive_json()


def custom(fu):
    return [p for p in fu.PRESET_DATA["presets"] if p.get("custom")]


async def test_create_edit_delete(hass: HomeAssistant, hass_ws_client, monkeypatch, userdata):
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)
    count = len(userdata.PRESET_DATA["presets"])

    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": "Photo", "bri": 200,
                          "lights": COLORS, "image": "data:image/jpeg;base64," + JPEG,
                          "default_category_name": "My presets"})
    assert r["success"], r
    preset = r["result"]["preset"]
    assert preset["img"].startswith("user/")
    assert len(userdata.PRESET_DATA["presets"]) == count + 1  # reloaded without a restart
    assert any(c["name"] == "My presets" for c in userdata.PRESET_DATA["categories"])

    r = await ws(client, {"type": "scene_studio/save_custom_preset", "preset_id": preset["id"],
                          "name": "Photo 2", "bri": 100, "lights": COLORS[:1]})
    assert r["success"], r
    assert [p["name"] for p in custom(userdata)] == ["Photo 2"]
    assert custom(userdata)[0]["img"] == preset["img"]  # no new photo: image stays

    r = await ws(client, {"type": "scene_studio/delete_custom_preset", "preset_id": preset["id"]})
    assert r["success"], r
    assert custom(userdata) == []
    assert not any(c["name"] == "My presets" for c in userdata.PRESET_DATA["categories"])


async def test_new_preset_needs_photo_and_name(hass, hass_ws_client, monkeypatch, userdata):
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)
    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": "x", "bri": 10, "lights": COLORS})
    assert not r["success"] and r["error"]["code"] == "invalid_preset"
    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": " ", "bri": 10, "lights": COLORS, "image": JPEG})
    assert not r["success"]
    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": "x", "bri": 10, "lights": COLORS,
                          "image": base64.b64encode(b"GIF89a...").decode()})
    assert not r["success"]


async def test_builtin_override_and_reset(hass, hass_ws_client, monkeypatch, userdata):
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)
    builtin = next(p for p in userdata.PRESET_DATA["presets"] if not p.get("custom"))
    original = (builtin["img"], builtin["lights"])

    r = await ws(client, {"type": "scene_studio/set_preset_image", "preset_id": builtin["id"], "image": JPEG})
    assert r["success"], r
    changed = next(p for p in userdata.PRESET_DATA["presets"] if p["id"] == builtin["id"])
    assert changed["img"].startswith("user/") and changed["lights"] == original[1] and changed["overridden"]

    # built-in presets cannot be edited or deleted as own presets
    r = await ws(client, {"type": "scene_studio/save_custom_preset", "preset_id": builtin["id"], "name": "x",
                          "bri": 1, "lights": COLORS})
    assert not r["success"]
    r = await ws(client, {"type": "scene_studio/delete_custom_preset", "preset_id": builtin["id"]})
    assert not r["success"]

    r = await ws(client, {"type": "scene_studio/reset_preset", "preset_id": builtin["id"]})
    assert r["success"], r
    restored = next(p for p in userdata.PRESET_DATA["presets"] if p["id"] == builtin["id"])
    assert (restored["img"], restored["lights"]) == original and "overridden" not in restored


async def test_hand_written_file_is_kept(hass, hass_ws_client, monkeypatch, userdata):
    hand = {"categories": [{"id": "cat-hand", "name": "Hand"}],
            "presets": [{"id": "p-hand", "categoryId": "cat-hand", "name": "Handmade", "bri": 200,
                         "img": "hand.jpeg", "lights": [{"x": 0.5, "y": 0.4}]}],
            "extra": 1}
    with open(userdata.custom_presets_path, "w") as file:
        json.dump(hand, file)
    userdata.reload_preset_data()
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)

    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": "Photo", "bri": 200,
                          "lights": COLORS, "image": JPEG, "category_id": "cat-hand"})
    assert r["success"], r
    with open(userdata.custom_presets_path) as file:
        stored = json.load(file)
    assert stored["extra"] == 1 and stored["presets"][0] == hand["presets"][0]
    assert os.path.exists(userdata.custom_presets_path + ".orig")


async def test_preset_used_by_saved_scene_is_not_deleted(hass, hass_ws_client, monkeypatch, userdata):
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)
    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": "Photo", "bri": 200,
                          "lights": COLORS, "image": JPEG})
    preset_id = r["result"]["preset"]["id"]
    await hass.services.async_call("scene_studio", "save_scene", {
        "name": "Living room", "preset_id": preset_id, "targets": {"entity_id": ["light.x"]}}, blocking=True)
    r = await ws(client, {"type": "scene_studio/delete_custom_preset", "preset_id": preset_id})
    assert not r["success"] and "Living room" in r["error"]["message"]


async def test_admin_only(hass, hass_ws_client, hass_read_only_access_token, monkeypatch, userdata):
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    r = await ws(client, {"type": "scene_studio/reset_preset", "preset_id": "x"})
    assert not r["success"] and r["error"]["code"] == "unauthorized"


async def test_builtin_default_brightness(hass, hass_ws_client, monkeypatch, userdata):
    """The default brightness of a built-in preset can be changed and restored."""
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)
    builtin = next(p for p in userdata.PRESET_DATA["presets"] if not p.get("custom") and p.get("bri") != 77)
    original = builtin["bri"]

    r = await ws(client, {"type": "scene_studio/set_preset_image", "preset_id": builtin["id"], "bri": 77})
    assert r["success"], r
    changed = next(p for p in userdata.PRESET_DATA["presets"] if p["id"] == builtin["id"])
    assert changed["bri"] == 77 and changed["overridden"] and changed["img"] == builtin["img"]

    r = await ws(client, {"type": "scene_studio/reset_preset", "preset_id": builtin["id"]})
    assert r["success"], r
    restored = next(p for p in userdata.PRESET_DATA["presets"] if p["id"] == builtin["id"])
    assert restored["bri"] == original


async def test_preset_from_colors(hass, hass_ws_client, monkeypatch, userdata):
    """A preset made from colors keeps the flag, a photo later removes it."""
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)
    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": "Sunset", "bri": 200, "lights": COLORS,
                          "image": JPEG, "generated": True, "default_category_name": "My presets"})
    assert r["success"], r
    preset = r["result"]["preset"]
    assert custom(userdata)[0]["generated"] is True

    r = await ws(client, {"type": "scene_studio/save_custom_preset", "preset_id": preset["id"], "name": "Sunset",
                          "bri": 200, "lights": COLORS, "image": JPEG, "generated": False})
    assert r["success"], r
    assert "generated" not in custom(userdata)[0]


async def test_hide_builtin_preset(hass, hass_ws_client, monkeypatch, userdata):
    """Built-in presets can be hidden and shown again; restoring the original keeps them hidden."""
    await setup(hass, monkeypatch)
    client = await hass_ws_client(hass)
    builtin = next(p for p in userdata.PRESET_DATA["presets"] if not p.get("custom") and not p.get("hidden"))
    get = lambda: next(p for p in userdata.PRESET_DATA["presets"] if p["id"] == builtin["id"])  # noqa: E731

    r = await ws(client, {"type": "scene_studio/set_preset_hidden", "preset_id": builtin["id"], "hidden": True})
    assert r["success"], r
    assert get()["hidden"] and get()["user_hidden"] and not get().get("overridden")

    await ws(client, {"type": "scene_studio/set_preset_image", "preset_id": builtin["id"], "bri": 50})
    await ws(client, {"type": "scene_studio/reset_preset", "preset_id": builtin["id"]})
    assert get()["hidden"] and get()["bri"] == builtin["bri"]

    r = await ws(client, {"type": "scene_studio/set_preset_hidden", "preset_id": builtin["id"], "hidden": False})
    assert r["success"], r
    assert not get().get("hidden") and not get().get("user_hidden")
    assert "overrides" not in json.load(open(userdata.custom_presets_path))

    # own presets are deleted, not hidden
    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": "Mine", "bri": 100, "lights": COLORS,
                          "image": JPEG, "default_category_name": "My presets"})
    r = await ws(client, {"type": "scene_studio/set_preset_hidden", "preset_id": r["result"]["preset"]["id"], "hidden": True})
    assert not r["success"]
