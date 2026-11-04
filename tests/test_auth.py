"""Access control: preset data and the user's own pictures need a login, import is for admins only."""

import base64
import json
import os
from datetime import timedelta

import pytest
from homeassistant.components.http.auth import async_sign_path
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.setup import async_setup_component

from .test_custom_presets import setup, userdata, ws  # noqa: F401  (fixture and helpers)

JPEG = base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 200).decode()
COLORS = [{"x": 0.3, "y": 0.3}, {"x": 0.6, "y": 0.35}]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def setup_with_views(hass, monkeypatch):
    from custom_components.scene_studio.view import PrivatePresetImageView, ScenePresetDataView

    assert await async_setup_component(hass, "http", {})
    await setup(hass, monkeypatch)
    hass.http.register_view(ScenePresetDataView)
    hass.http.register_view(PrivatePresetImageView)


async def own_preset(hass, hass_ws_client):
    client = await hass_ws_client(hass)
    r = await ws(client, {"type": "scene_studio/save_custom_preset", "name": "Holiday photo", "bri": 200,
                          "lights": COLORS, "image": "data:image/jpeg;base64," + JPEG,
                          "default_category_name": "My presets"})
    assert r["success"], r
    return r["result"]["preset"]


async def test_preset_data_needs_login(hass: HomeAssistant, hass_client, hass_client_no_auth, hass_ws_client,
                                       monkeypatch, userdata):
    await setup_with_views(hass, monkeypatch)
    preset = await own_preset(hass, hass_ws_client)

    anonymous = await hass_client_no_auth()
    assert (await anonymous.get("/assets/scene_studio/scene_studio.json")).status == 401

    client = await hass_client()
    response = await client.get("/assets/scene_studio/scene_studio.json")
    assert response.status == 200
    data = await response.json()
    own = next(p for p in data["presets"] if p["id"] == preset["id"])
    assert own["img_url"].startswith("/api/scene_studio/image/" + preset["img"] + "?authSig=")
    builtin = next(p for p in data["presets"] if not p.get("custom") and p.get("img"))
    assert "img_url" not in builtin  # built-in pictures stay static files


async def test_own_pictures_need_login(hass: HomeAssistant, hass_client, hass_client_no_auth, hass_ws_client,
                                       monkeypatch, userdata):
    await setup_with_views(hass, monkeypatch)
    preset = await own_preset(hass, hass_ws_client)
    url = "/api/scene_studio/image/" + preset["img"]

    anonymous = await hass_client_no_auth()
    assert (await anonymous.get(url)).status == 401

    client = await hass_client()
    assert (await client.get(url)).status == 200

    # a signed URL works without an auth header (<img> in the panel, entity_picture)
    signed = async_sign_path(hass, url, timedelta(minutes=5), use_content_user=True)
    assert (await anonymous.get(signed)).status == 200

    # nothing else from the disk: unknown pictures and paths outside the folder
    assert (await client.get("/api/scene_studio/image/user/00000000-0000-0000-0000-000000000000.jpg")).status == 404
    assert (await client.get("/api/scene_studio/image/..%2F..%2Fmanifest.json")).status in (400, 404)


async def test_hand_written_custom_preset_picture(hass: HomeAssistant, hass_client, hass_client_no_auth,
                                                  monkeypatch, userdata):
    with open(os.path.join(userdata.CUSTOM_DIR, "assets", "beach.jpg"), "wb") as file:
        file.write(b"\xff\xd8\xff\xe0" + b"0" * 50)
    with open(os.path.join(userdata.CUSTOM_DIR, "presets.json"), "w", encoding="utf-8") as file:
        json.dump({"categories": [{"id": "c1", "name": "Mine"}],
                   "presets": [{"id": "p1", "categoryId": "c1", "name": "Beach", "img": "beach.jpg",
                                "bri": 200, "lights": COLORS}]}, file)
    userdata.reload_preset_data()
    await setup_with_views(hass, monkeypatch)

    assert (await (await hass_client_no_auth()).get("/api/scene_studio/image/beach.jpg")).status == 401
    assert (await (await hass_client()).get("/api/scene_studio/image/beach.jpg")).status == 200


async def test_scene_entity_picture(hass: HomeAssistant, hass_ws_client, monkeypatch, userdata):
    await setup_with_views(hass, monkeypatch)
    preset = await own_preset(hass, hass_ws_client)
    builtin = next(p for p in userdata.PRESET_DATA["presets"] if not p.get("custom") and p.get("img"))

    for name, preset_id in (("Own", preset["id"]), ("Built in", builtin["id"])):
        await hass.services.async_call("scene_studio", "save_scene", {
            "name": name, "preset_id": preset_id, "targets": {"entity_id": ["light.a"]},
        }, blocking=True, return_response=True)
    await hass.async_block_till_done()

    own = hass.states.get("scene.own").attributes["entity_picture"]
    assert own.startswith("/api/scene_studio/image/" + preset["img"] + "?authSig=")
    assert hass.states.get("scene.built_in").attributes["entity_picture"] == "/assets/scene_studio/" + builtin["img"]


async def test_import_is_for_admins(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token,
                                    hass_read_only_user, monkeypatch, userdata):
    await setup(hass, monkeypatch)

    client = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    r = await ws(client, {"type": "scene_studio/import_status"})
    assert not r["success"] and r["error"]["code"] == "unauthorized"

    with pytest.raises(Unauthorized):
        await hass.services.async_call("scene_studio", "import_scene_presets", {}, blocking=True,
                                       return_response=True, context=Context(user_id=hass_read_only_user.id))

    admin = await hass_ws_client(hass)
    assert (await ws(admin, {"type": "scene_studio/import_status"}))["success"]


async def test_reload(hass: HomeAssistant, monkeypatch, userdata):
    """The entry can be reloaded: everything is set up again, services keep working."""
    from custom_components.scene_studio.data import find_data

    await setup(hass, monkeypatch)
    entry = hass.config_entries.async_entries("scene_studio")[0]
    first = find_data(hass)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert find_data(hass) is not None and find_data(hass) is not first
    response = await hass.services.async_call("scene_studio", "get_dynamic_scenes", {}, blocking=True,
                                              return_response=True)
    assert response is not None

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert find_data(hass) is None


async def test_service_activation_is_recorded(hass: HomeAssistant, monkeypatch, userdata):
    """activate_saved_scene marks the scene entity like scene.turn_on (active tile), not for lamp modes."""
    from homeassistant.util import dt as dt_util

    await setup(hass, monkeypatch)
    hass.states.async_set("light.a", "off", {"supported_color_modes": ["xy"]})
    hass.services.async_register("light", "turn_on", lambda call: None)
    builtin = next(p for p in userdata.PRESET_DATA["presets"] if not p.get("custom"))
    ids = {}
    for name in ("Bright", "Aurora"):
        r = await hass.services.async_call("scene_studio", "save_scene", {
            "name": name, "preset_id": builtin["id"], "targets": {"entity_id": ["light.a"]},
        }, blocking=True, return_response=True)
        ids[name] = r["scene"]["id"]
    await hass.async_block_till_done()
    assert hass.states.get("scene.bright").state == "unknown"

    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": ids["Bright"]}, blocking=True)
    first = dt_util.parse_datetime(hass.states.get("scene.bright").state)
    assert first is not None

    # a lamp mode (other targets) does not make the scene the active one
    await hass.services.async_call("scene_studio", "activate_saved_scene",
                                   {"id": ids["Aurora"], "targets": {"entity_id": ["light.a"]}}, blocking=True)
    assert hass.states.get("scene.aurora").state == "unknown"


async def test_scene_order(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token, monkeypatch, userdata):
    """The order set in the panel is kept, shown as attribute and survives editing a scene."""
    from custom_components.scene_studio.data import find_data

    await setup(hass, monkeypatch)
    builtin = next(p for p in userdata.PRESET_DATA["presets"] if not p.get("custom"))
    ids = []
    for name in ("Alpha", "Beta", "Gamma"):
        r = await hass.services.async_call("scene_studio", "save_scene", {
            "name": name, "preset_id": builtin["id"], "targets": {"entity_id": ["light.a"]},
        }, blocking=True, return_response=True)
        ids.append(r["scene"]["id"])
    client = await hass_ws_client(hass)
    r = await ws(client, {"type": "scene_studio/set_scene_order", "scene_ids": [ids[2], ids[0], ids[1]]})
    assert r["success"], r
    await hass.async_block_till_done()
    store = find_data(hass).saved_scenes
    assert [s["name"] for s in store.get_all()] == ["Gamma", "Alpha", "Beta"]
    assert hass.states.get("scene.gamma").attributes["order"] == 0

    # editing keeps the place
    await hass.services.async_call("scene_studio", "save_scene", {
        "id": ids[2], "name": "Gamma", "preset_id": builtin["id"], "targets": {"entity_id": ["light.b"]},
    }, blocking=True, return_response=True)
    assert store.get(ids[2])["order"] == 0

    reader = await hass_ws_client(hass, access_token=hass_read_only_access_token)
    assert not (await ws(reader, {"type": "scene_studio/set_scene_order", "scene_ids": ids}))["success"]
