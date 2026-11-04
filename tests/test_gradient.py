"""Gradient lamps get all colors of the preset over MQTT (Zigbee2MQTT), other lamps one color."""

import json

import pytest

from homeassistant.core import HomeAssistant

from .test_custom_presets import setup, userdata, runtime  # noqa: F401  (fixture and helpers)

PRESET = "940fd864-51e1-4761-95d3-75d4d68835ea"  # Arctic aurora, several colors


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def test_gradient_colors_start_with_the_lamps_color():
    from custom_components.scene_studio.gradient import gradient_colors

    colors = [(0.1, 0.1), (0.2, 0.2), (0.3, 0.3), (0.4, 0.4), (0.5, 0.4), (0.6, 0.3)]
    assert gradient_colors(colors, (0.3, 0.3)) == [(0.3, 0.3), (0.4, 0.4), (0.5, 0.4), (0.6, 0.3), (0.1, 0.1)]
    assert gradient_colors([(0.3, 0.3)], (0.9, 0.9)) == [(0.3, 0.3)]


async def _setup(hass, monkeypatch):
    import homeassistant.components.mqtt as mqtt

    published = []

    async def fake_publish(hass, topic, payload, *args, **kwargs):
        published.append((topic, json.loads(payload)))

    monkeypatch.setattr(mqtt, "async_publish", fake_publish)
    turned_on = []

    async def turn_on(call):
        turned_on.append(call.data["entity_id"])

    hass.services.async_register("light", "turn_on", turn_on)
    attrs = {"supported_color_modes": ["xy", "color_temp"], "color_mode": "xy"}
    hass.states.async_set("light.signe", "off", attrs)
    hass.states.async_set("light.bulb", "off", attrs)
    await setup(hass, monkeypatch)
    runtime(hass).gradient.register("light.signe", "zigbee2mqtt/Signe")
    return published, turned_on


async def test_gradient_lamp_gets_all_colors(hass: HomeAssistant, monkeypatch, userdata):
    published, turned_on = await _setup(hass, monkeypatch)
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": PRESET, "targets": {"entity_id": ["light.signe", "light.bulb"]}}, blocking=True)
    await hass.async_block_till_done()
    assert [t for t, _ in published] == ["zigbee2mqtt/Signe/set"]
    payload = published[0][1]
    assert len(payload["gradient"]) >= 2 and payload["gradient_style"] == "linear" and payload["state"] == "ON"
    assert turned_on == ["light.bulb"]


async def test_gradient_can_be_switched_off(hass: HomeAssistant, monkeypatch, userdata):
    published, turned_on = await _setup(hass, monkeypatch)
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": PRESET, "targets": {"entity_id": ["light.signe"]}, "gradient": False}, blocking=True)
    await hass.async_block_till_done()
    assert published == [] and turned_on == ["light.signe"]


async def test_saved_scene_keeps_gradient_setting(hass: HomeAssistant, monkeypatch, userdata):
    published, turned_on = await _setup(hass, monkeypatch)
    r = await hass.services.async_call("scene_studio", "save_scene", {
        "name": "Signe one color", "preset_id": PRESET, "targets": {"entity_id": ["light.signe"]},
        "gradient": False}, blocking=True, return_response=True)
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": r["scene"]["id"]}, blocking=True)
    await hass.async_block_till_done()
    assert published == [] and turned_on == ["light.signe"]


def _z2m_xy(hex_color):
    """What Zigbee2MQTT makes of a gradient hex color (ColorRGB.fromHex(hex).toXY(), no gamma)."""
    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    big_x = r * 0.664511 + g * 0.154324 + b * 0.162028
    big_y = r * 0.283881 + g * 0.668433 + b * 0.047685
    big_z = r * 0.000088 + g * 0.07231 + b * 0.986039
    total = big_x + big_y + big_z
    return big_x / total, big_y / total


@pytest.mark.parametrize("xy", [(0.17, 0.7), (0.15, 0.06), (0.64, 0.33), (0.3, 0.32), (0.2, 0.45), (0.45, 0.41)])
def test_hex_round_trip(xy):
    """The lamp gets the xy of the preset back, so gradients are as saturated as single colors."""
    from custom_components.scene_studio.gradient import _hex

    x, y = _z2m_xy(_hex(xy))
    assert abs(x - xy[0]) < 0.01 and abs(y - xy[1]) < 0.01
