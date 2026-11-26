"""Deep colors: more brightness and/or some white for colors that give little light."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.util import color as color_util

from .test_custom_presets import setup, userdata  # noqa: F401  (fixture and helper)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _xy(r, g, b):
    return color_util.color_RGB_to_xy(r, g, b)


def test_only_deep_colors_change_and_keep_their_hue():
    from custom_components.scene_studio.color_management import DEEP_COLOR_LEVEL, deep_color, light_output

    red, blue, yellow = _xy(255, 0, 0), _xy(0, 0, 255), _xy(255, 255, 0)
    assert deep_color(red, 128) == (red, 128)                         # both off: as before
    assert deep_color(yellow, 128, True, 100) == (yellow, 128)        # bright colors stay
    # brighter: the color stays, the brightness goes up (at most 255)
    xy, bri = deep_color(red, 100, brighten=True)
    assert xy == red and bri == round(100 * DEEP_COLOR_LEVEL / light_output(red))
    assert deep_color(blue, 200, brighten=True) == (blue, 255)
    # lighten: white mixed in, more with a higher value, the brightness stays
    half, bri = deep_color(blue, 128, lighten=50)
    full, _ = deep_color(blue, 128, lighten=100)
    assert bri == 128 and light_output(blue) < light_output(half) < light_output(full)
    assert abs(light_output(full) - DEEP_COLOR_LEVEL) < 0.02
    hue = lambda xy: color_util.color_xy_to_hs(*xy)[0]
    assert abs(hue(full) - hue(blue)) < 4                            # the hue stays
    # both: the brightness first, white only for what is still missing
    xy, bri = deep_color(red, 100, True, 100)
    assert xy == red and bri < 255                                   # the brightness was enough
    xy, bri = deep_color(blue, 255, True, 100)
    assert bri == 255 and abs(light_output(xy) - DEEP_COLOR_LEVEL) < 0.02
    # brightness unknown: only lighten
    assert deep_color(blue, None, True, 0) == (blue, None)


async def test_a_scene_with_deep_colors(hass: HomeAssistant, monkeypatch, userdata):
    calls = []

    async def turn_on(call):
        calls.append(dict(call.data))

    hass.services.async_register("light", "turn_on", turn_on)
    hass.states.async_set("light.a", "on", {"supported_color_modes": ["xy"], "color_mode": "xy"})
    await setup(hass, monkeypatch)

    # an own preset in deep blue
    from custom_components.scene_studio.file_utils import RUNTIME_PRESETS
    blue = _xy(0, 0, 255)
    RUNTIME_PRESETS["test_blue"] = {"id": "test_blue", "name": "Blue", "bri": 128, "lights": [{"x": blue[0], "y": blue[1]}]}
    try:
        await hass.services.async_call("scene_studio", "apply_preset", {
            "preset_id": "test_blue", "targets": {"entity_id": "light.a"}}, blocking=True)
        await hass.services.async_call("scene_studio", "apply_preset", {
            "preset_id": "test_blue", "targets": {"entity_id": "light.a"}, "brighten_deep": True, "lighten_deep": 60}, blocking=True)
    finally:
        RUNTIME_PRESETS.pop("test_blue", None)
    before, after = calls
    assert before["brightness"] == 128                               # without the options: as before
    assert after["brightness"] == 255 and tuple(after["xy_color"]) != tuple(before["xy_color"])

    saved = await hass.services.async_call("scene_studio", "save_scene", {
        "name": "Deep", "preset_id": "940fd864-51e1-4761-95d3-75d4d68835ea", "targets": {"entity_id": "light.a"},
        "brighten_deep": True, "lighten_deep": 40}, blocking=True, return_response=True)
    assert saved["scene"]["brighten_deep"] is True and saved["scene"]["lighten_deep"] == 40
