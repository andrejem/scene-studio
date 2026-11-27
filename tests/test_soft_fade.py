"""Soft fade: Scene Studio fades marked lights itself, in steps around the color wheel."""

import asyncio

import pytest

from homeassistant.core import HomeAssistant

from .test_custom_presets import runtime, setup, userdata  # noqa: F401  (fixture and helpers)

PRESET = "940fd864-51e1-4761-95d3-75d4d68835ea"  # Arctic aurora


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def test_steps_go_around_the_color_wheel():
    from custom_components.scene_studio.soft_fade import steps_between

    # red to blue: the short way over magenta (360 -> 240), brightness stays
    steps = steps_between((0, 100, 200), (240, 100, 200), 30, 4)
    assert steps[-1] == (240, 100, 200)
    hues = [s[0] for s in steps]
    assert all(300 <= h <= 360 or 240 <= h < 300 for h in hues) and hues[0] > 300   # never through green
    assert all(s[1] == 100 and s[2] == 200 for s in steps)
    # a small change needs few steps, the rate is the upper limit
    assert len(steps_between((100, 50, 100), (104, 50, 100), 30, 4)) <= 4
    assert len(steps_between((0, 100, 0), (180, 100, 255), 2, 1)) == 2
    # from white the hue does not wander around the wheel
    white = steps_between((30, 0, 100), (200, 80, 100), 10, 2)
    assert len({s[0] for s in white}) == 1 and white[-1][1] == 80
    # brightness unknown on one side: no change of brightness, the target keeps None
    assert steps_between((0, 100, None), (90, 100, None), 5, 2)[-1] == (90, 100, None)


def test_easing_and_smoothness():
    from custom_components.scene_studio.soft_fade import STEP_HUE, steps_between

    steps = steps_between((0, 100, 200), (240, 100, 200), 60, 20)
    deltas = [abs(((b[0] - a[0] + 180) % 360) - 180) for a, b in zip([(0, 0, 0)] + steps, steps)]
    assert deltas[0] < deltas[len(deltas) // 2] and deltas[-1] < deltas[len(deltas) // 2]   # gentle start and end
    assert max(deltas) <= STEP_HUE + 0.05                                                 # no step larger than allowed
    fine = steps_between((0, 100, 200), (240, 100, 200), 60, 20, 0.5)
    coarse = steps_between((0, 100, 200), (240, 100, 200), 60, 20, 2.5)
    assert len(coarse) < len(steps) < len(fine)                                           # finer = more, smaller steps
    # the time decides when it is short: 5 s at 20 steps per second
    assert len(steps_between((0, 100, 200), (240, 100, 200), 5, 20, 0.5)) == 100


def test_rates_and_old_levels():
    from custom_components.scene_studio.soft_fade import rate_of

    assert (rate_of("coarse"), rate_of("normal"), rate_of("fine")) == (1, 2, 4)
    assert (rate_of(7), rate_of("12"), rate_of(0), rate_of(99), rate_of("silky")) == (7, 12, 1, 20, None)


async def _lights(hass, monkeypatch):
    calls = []

    async def turn_on(call):
        calls.append(dict(call.data))
        data = call.data
        attrs = {"supported_color_modes": ["xy", "color_temp"], "color_mode": "hs",
                 "hs_color": list(data.get("hs_color", [0, 100])), "brightness": data.get("brightness", 200)}
        hass.states.async_set(data["entity_id"] if isinstance(data["entity_id"], str) else data["entity_id"][0], "on", attrs)

    hass.services.async_register("light", "turn_on", turn_on)
    hass.services.async_register("light", "turn_off", lambda call: None)
    for name in ("govee", "hue"):
        hass.states.async_set(f"light.{name}", "on", {"supported_color_modes": ["xy", "color_temp"], "color_mode": "hs",
                                                      "hs_color": [0, 100], "brightness": 200})
    await setup(hass, monkeypatch)
    return calls


async def test_a_marked_light_is_faded_in_steps(hass: HomeAssistant, monkeypatch, userdata, hass_ws_client):
    calls = await _lights(hass, monkeypatch)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "scene_studio/set_soft_fade", "entity_id": "light.govee", "level": "fine"})
    assert (await client.receive_json())["result"]["lights"] == {"light.govee": 4}       # a level of 3.8 still works
    await client.send_json_auto_id({"type": "scene_studio/set_soft_fade", "entity_id": "light.govee", "rate": 20})
    assert (await client.receive_json())["result"]["lights"] == {"light.govee": 20}
    await client.send_json_auto_id({"type": "scene_studio/set_soft_fade", "entity_id": "light.govee", "rate": 21})
    assert not (await client.receive_json())["success"]
    await client.send_json_auto_id({"type": "scene_studio/set_soft_fade_smoothness", "smoothness": "fine"})
    assert (await client.receive_json())["result"]["smoothness"] == "fine"
    await client.send_json_auto_id({"type": "scene_studio/get_soft_fade"})
    assert (await client.receive_json())["result"] == {"lights": {"light.govee": 20}, "smoothness": "fine"}
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": PRESET, "targets": {"entity_id": ["light.govee", "light.hue"]}, "transition": 1}, blocking=True)
    hue = [c for c in calls if c["entity_id"] == "light.hue"]
    assert len(hue) == 1 and hue[0]["transition"] == 1            # not marked: one command as before
    await asyncio.sleep(1.3)
    await hass.async_block_till_done()
    govee = [c for c in calls if c["entity_id"] == "light.govee"]
    assert len(govee) > 5                                          # in steps
    assert all("hs_color" in c and "transition" not in c for c in govee[:-1])
    assert "xy_color" in govee[-1] and "transition" not in govee[-1]   # the last one: the exact preset color


async def test_another_command_ends_the_fade(hass: HomeAssistant, monkeypatch, userdata):
    calls = await _lights(hass, monkeypatch)
    await runtime(hass).soft_fade.async_set("light.govee", "coarse")
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": PRESET, "targets": {"entity_id": ["light.govee"]}, "transition": 30}, blocking=True)
    await asyncio.sleep(0.05)
    assert runtime(hass).soft_fade._running                       # running in the background
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.govee", "brightness": 10}, blocking=True)
    await asyncio.sleep(0.05)
    assert not runtime(hass).soft_fade._running                   # someone else: the fade ends at once
    count = len(calls)
    await asyncio.sleep(1.2)
    assert len(calls) == count

    # a light that is off fades on by itself: one command as before
    hass.states.async_set("light.govee", "off", {"supported_color_modes": ["xy"]})
    calls.clear()
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": PRESET, "targets": {"entity_id": ["light.govee"]}, "transition": 30}, blocking=True)
    assert len(calls) == 1 and calls[0]["transition"] == 30 and not runtime(hass).soft_fade._running

    # not marked any more: as before
    await runtime(hass).soft_fade.async_set("light.govee", None)
    assert runtime(hass).soft_fade.lights() == {}


async def test_a_light_turned_off_during_the_fade_stays_off(hass: HomeAssistant, monkeypatch, userdata):
    calls = await _lights(hass, monkeypatch)
    await runtime(hass).soft_fade.async_set("light.govee", 20)
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": PRESET, "targets": {"entity_id": ["light.govee"]}, "transition": 2}, blocking=True)
    await asyncio.sleep(0.12)
    hass.states.async_set("light.govee", "off", {})               # at the switch: no service call
    count = len(calls)
    await asyncio.sleep(0.5)
    assert len(calls) <= count + 1 and not runtime(hass).soft_fade._running


async def test_settings_of_3_8_are_kept(hass: HomeAssistant, monkeypatch, userdata, hass_storage):
    hass_storage["scene_studio.soft_fade"] = {"version": 1, "key": "scene_studio.soft_fade",
                                              "data": {"lights": {"light.a": "coarse", "light.b": "fine", "light.c": "odd"}}}
    await _lights(hass, monkeypatch)
    assert runtime(hass).soft_fade.lights() == {"light.a": 1, "light.b": 4}
    assert runtime(hass).soft_fade.smoothness() == "normal"
