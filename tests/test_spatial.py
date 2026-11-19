"""Room canvas: lights with a place on a room plan get the color the picture of the preset has there."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.util import color as color_util

from .test_custom_presets import setup, userdata, runtime  # noqa: F401  (fixture and helpers)

PRESET = "940fd864-51e1-4761-95d3-75d4d68835ea"  # Arctic aurora, several colors

RED = tuple(round(v, 4) for v in color_util.color_RGB_to_xy(255, 0, 0))
BLUE = tuple(round(v, 4) for v in color_util.color_RGB_to_xy(0, 0, 255))
GREEN = tuple(round(v, 4) for v in color_util.color_RGB_to_xy(0, 255, 0))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _field(left, right, width=32, height=20):
    return [[left if x < width / 2 else right for x in range(width)] for _ in range(height)]


def test_lights_get_the_color_at_their_place():
    from custom_components.scene_studio.spatial import assign

    field = _field((250, 10, 10), (10, 10, 250))
    places = {"light.left": {"x": 0.1, "y": 0.5}, "light.right": {"x": 0.9, "y": 0.5}}
    result = assign(field, places, [BLUE, RED])
    assert result["light.left"]["color"] == RED and result["light.right"]["color"] == BLUE


def test_every_color_stays_in_use():
    from custom_components.scene_studio.spatial import assign

    field = _field((250, 10, 10), (250, 10, 10))  # a picture in one color
    places = {f"light.l{i}": {"x": i / 4, "y": 0.5} for i in range(4)}
    used = [v["color"] for v in assign(field, places, [RED, BLUE]).values()]
    assert used.count(RED) == 2 and used.count(BLUE) == 2


def test_the_picture_moves_and_comes_back():
    from custom_components.scene_studio.spatial import assign, shift_of

    field = _field((250, 10, 10), (10, 10, 250))
    places = {"light.a": {"x": 0.25, "y": 0.5}}
    spatial = {"direction": 0, "since": 100.0, "period": 60}
    assert shift_of(None) == (0.0, 0.0) and shift_of({"direction": 90}) == (0.0, 0.0)
    assert assign(field, places, [RED, BLUE], shift_of(spatial, 100.0))["light.a"]["color"] == RED
    # half a room later the right half of the picture... is mirrored in: the light sees what was left of it
    assert assign(field, places, [RED, BLUE], shift_of(spatial, 130.0))["light.a"]["color"] == RED
    assert assign(field, places, [RED, BLUE], shift_of(spatial, 100.0 + 60))["light.a"]["color"] == BLUE
    down = shift_of({"direction": 90, "since": 0.0, "period": 10}, 10.0)
    assert abs(down[0]) < 1e-9 and abs(down[1] - 1) < 1e-9


def test_a_strip_gets_the_colors_along_it_and_own_colors_are_kept():
    from custom_components.scene_studio.spatial import assign

    field = _field((250, 10, 10), (10, 10, 250))
    places = {"light.strip": {"x": 0.05, "y": 0.5, "x2": 0.95, "y2": 0.5}, "light.main": {"x": 0.9, "y": 0.2}}
    result = assign(field, places, [RED, BLUE, GREEN], pools={"light.main": [GREEN]})
    assert result["light.strip"]["strip"][0] == RED and result["light.strip"]["strip"][-1] == BLUE
    assert result["light.main"]["color"] == GREEN  # only its own colors, even if another one is closer
    assert assign(field, {}, [RED]) == {}


def test_without_picture_the_colors_run_from_left_to_right():
    from custom_components.scene_studio.spatial import assign

    places = {f"light.l{i}": {"x": 0.1 + i * 0.4, "y": 0.5} for i in range(3)}
    result = assign(None, places, [GREEN, RED, BLUE])
    assert [result[f"light.l{i}"]["color"] for i in range(3)] == [GREEN, RED, BLUE]


def test_a_picture_with_colors_close_together_still_uses_all_colors():
    from custom_components.scene_studio.spatial import assign

    # blue on the left turning a little greener to the right: far from the preset colors, but ordered
    field = [[(40, 90 + x * 3, 200) for x in range(32)] for _ in range(20)]
    places = {f"light.l{i}": {"x": 0.1 + i * 0.4, "y": 0.5} for i in range(3)}
    result = assign(field, places, [RED, GREEN, BLUE])
    assert len({v["color"] for v in result.values()}) == 3
    assert result["light.l0"]["color"] == BLUE and result["light.l2"]["color"] == GREEN


async def _lights(hass, monkeypatch):
    calls = []

    async def turn_on(call):
        calls.append(dict(call.data))

    hass.services.async_register("light", "turn_on", turn_on)
    attrs = {"supported_color_modes": ["xy"], "color_mode": "xy"}
    for name in ("left", "right", "nowhere"):
        hass.states.async_set(f"light.{name}", "on", attrs)
    await setup(hass, monkeypatch)
    return calls


async def test_room_plans_are_saved_and_used(hass: HomeAssistant, monkeypatch, userdata, hass_ws_client):
    from custom_components.scene_studio import presets
    from custom_components.scene_studio.file_utils import PRESET_DATA

    calls = await _lights(hass, monkeypatch)
    targets = {"entity_id": ["light.left", "light.right", "light.nowhere"]}
    await hass.services.async_call("scene_studio", "apply_preset", {"preset_id": PRESET, "targets": targets}, blocking=True)
    await hass.async_block_till_done()
    before = {c["entity_id"]: tuple(c["xy_color"]) for c in calls}
    calls.clear()
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({
        "type": "scene_studio/save_room_plan", "name": "Living room",
        "lights": {"light.left": {"x": 0.1, "y": 0.5}, "light.right": {"x": 0.9, "y": 0.5, "x2": 0.95, "y2": 0.9}},
    })
    plan = (await client.receive_json())["result"]["plan"]
    assert plan["lights"]["light.right"]["x2"] == 0.95
    await client.send_json_auto_id({"type": "scene_studio/get_room_plans"})
    assert [p["name"] for p in (await client.receive_json())["result"]["plans"]] == ["Living room"]
    await client.send_json_auto_id({"type": "scene_studio/save_room_plan", "name": " ", "lights": {}})
    assert not (await client.receive_json())["success"]

    preset = next(p for p in PRESET_DATA["presets"] if p["id"] == PRESET)
    colors = [(c["x"], c["y"]) for c in preset["lights"]]
    import math

    from custom_components.scene_studio.spatial import _chroma_xy

    # the two colors of the preset that differ most
    a, b = max(((a, b) for a in colors for b in colors), key=lambda p: math.dist(_chroma_xy(p[0]), _chroma_xy(p[1])))
    first, last = color_util.color_xy_to_RGB(*a), color_util.color_xy_to_RGB(*b)

    async def field_for(hass, preset):
        return _field(last, first)

    from custom_components.scene_studio import spatial as spatial_module

    monkeypatch.setattr(spatial_module, "async_field_for", field_for)
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": PRESET, "targets": targets, "spatial": {}}, blocking=True)
    await hass.async_block_till_done()
    got = {c["entity_id"]: tuple(c["xy_color"]) for c in calls}
    assert got["light.left"] == b and got["light.right"] == a
    assert got["light.nowhere"] in colors  # no place: a color of the preset, as before

    calls.clear()
    await hass.services.async_call("scene_studio", "apply_preset", {"preset_id": PRESET, "targets": targets}, blocking=True)
    await hass.async_block_till_done()
    assert {c["entity_id"]: tuple(c["xy_color"]) for c in calls} == before  # not spatial: unchanged

    await client.send_json_auto_id({"type": "scene_studio/delete_room_plan", "plan_id": plan["id"]})
    assert (await client.receive_json())["result"]["deleted"]
    assert runtime(hass).room_plans.get_all() == []


async def test_dynamic_scene_moves_the_picture_and_saved_scenes_keep_the_setting(hass: HomeAssistant, monkeypatch, userdata):
    await _lights(hass, monkeypatch)
    result = await hass.services.async_call("scene_studio", "start_dynamic_scene", {
        "preset_id": PRESET, "targets": {"entity_id": ["light.left"]}, "interval": 30, "spatial": {"direction": 90},
    }, blocking=True, return_response=True)
    spatial = result["parameters"]["spatial"]
    assert spatial["direction"] == 90 and spatial["period"] == 300 and spatial["since"] > 0
    await hass.services.async_call("scene_studio", "stop_all_dynamic_scenes", {}, blocking=True)

    saved = await hass.services.async_call("scene_studio", "save_scene", {
        "name": "Aurora", "preset_id": PRESET, "targets": {"entity_id": ["light.left"]}, "spatial": {"direction": 45},
    }, blocking=True, return_response=True)
    assert saved["scene"]["spatial"] == {"direction": 45}


def test_the_picture_of_a_preset_becomes_a_field_and_is_cut_to_the_plan():
    import os

    from custom_components.scene_studio.spatial import FIELD_SIDE, _field_from_image, field_from_bytes, fit

    assets = os.path.join(os.path.dirname(__file__), "..", "custom_components", "scene_studio", "assets")
    path = os.path.join(assets, f"{PRESET}.jpeg")
    field = _field_from_image(path)
    assert max(len(field), len(field[0])) == FIELD_SIDE and len(field[0][0]) == 3
    with open(path, "rb") as file:
        assert field_from_bytes(file.read()) == field
    assert _field_from_image(b"no picture") is None

    square = [[(x, y, 0) for x in range(30)] for y in range(30)]
    wide, tall = fit(square, 2.0), fit(square, 0.5)
    assert (len(wide), len(wide[0])) == (15, 30) and wide[0][0] == (0, 7, 0)   # the middle rows
    assert (len(tall), len(tall[0])) == (30, 15) and tall[0][0] == (7, 0, 0)   # the middle columns
    assert fit(square, 1.0) == square and fit(None, 1.6) is None


async def test_a_plan_has_a_format_and_an_own_floor_plan(hass: HomeAssistant, monkeypatch, userdata, hass_ws_client):
    await _lights(hass, monkeypatch)
    client = await hass_ws_client(hass)
    image = "data:image/jpeg;base64,AAAA"
    await client.send_json_auto_id({
        "type": "scene_studio/save_room_plan", "name": "Corridor", "aspect": 0.1, "image": image,
        "lights": {"light.left": {"x": 0.5, "y": 0.1}},
    })
    plan = (await client.receive_json())["result"]["plan"]
    assert plan["aspect"] == 0.4 and plan["image"] == image   # the format stays within its limits
    assert runtime(hass).room_plans.place_of("light.left")["aspect"] == 0.4
    assert runtime(hass).room_plans.place_of("light.right") is None

    await client.send_json_auto_id({
        "type": "scene_studio/save_room_plan", "plan_id": plan["id"], "name": "Corridor", "aspect": 1.6,
        "image": None, "lights": {"light.left": {"x": 0.5, "y": 0.1}},
    })
    plan = (await client.receive_json())["result"]["plan"]
    assert "aspect" not in plan and "image" not in plan   # landscape without floor plan is the default
    await client.send_json_auto_id({
        "type": "scene_studio/save_room_plan", "name": "Bad", "image": "data:text/html;base64,AAAA", "lights": {},
    })
    assert not (await client.receive_json())["success"]


async def test_a_music_scene_brings_the_cover_as_its_picture(hass: HomeAssistant):
    from custom_components.scene_studio.spatial import async_field_for

    field = _field((250, 10, 10), (10, 10, 250))
    assert await async_field_for(hass, {"id": "music_x", "field": field}) is field
    assert await async_field_for(hass, {"id": "no picture"}) is None
