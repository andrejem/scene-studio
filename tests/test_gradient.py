"""Gradient lamps get all colors of the preset over MQTT (Zigbee2MQTT), other lamps one color."""

import json

import pytest

from homeassistant.core import HomeAssistant

from .test_custom_presets import setup, userdata  # noqa: F401  (fixture and helpers)

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
    hass.data["scene_studio"]["gradient"].register("light.signe", "zigbee2mqtt/Signe")
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
