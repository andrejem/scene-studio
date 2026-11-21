"""Which lights get the color of a preset and which only a white tone."""

import pytest

from homeassistant.core import HomeAssistant

from .test_custom_presets import setup, userdata  # noqa: F401  (fixture and helper)

PRESET = "940fd864-51e1-4761-95d3-75d4d68835ea"  # Arctic aurora


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def test_every_color_mode_gets_the_color(hass: HomeAssistant, monkeypatch, userdata):
    calls = []

    async def turn_on(call):
        calls.append(dict(call.data))

    hass.services.async_register("light", "turn_on", turn_on)
    modes = ("xy", "hs", "rgb", "rgbw", "rgbww")
    for mode in modes:
        hass.states.async_set(f"light.{mode}", "on", {"supported_color_modes": ["color_temp", mode], "color_mode": mode})
    hass.states.async_set("light.white", "on", {"supported_color_modes": ["color_temp"], "color_mode": "color_temp"})
    hass.states.async_set("light.dimmer", "on", {"supported_color_modes": ["brightness"], "color_mode": "brightness"})
    await setup(hass, monkeypatch)

    entities = [f"light.{mode}" for mode in modes] + ["light.white", "light.dimmer"]
    await hass.services.async_call(
        "scene_studio", "apply_preset", {"preset_id": PRESET, "targets": {"entity_id": entities}}, blocking=True)
    await hass.async_block_till_done()

    got = {c["entity_id"]: c for c in calls}
    for mode in modes:   # rgbww was missing: such lights (e.g. WiZ) only got a white tone
        assert "xy_color" in got[f"light.{mode}"] and "color_temp_kelvin" not in got[f"light.{mode}"], mode
    assert "color_temp_kelvin" in got["light.white"] and "xy_color" not in got["light.white"]
    assert "xy_color" not in got["light.dimmer"] and "color_temp_kelvin" not in got["light.dimmer"]
