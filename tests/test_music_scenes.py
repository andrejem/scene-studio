"""Music scenes: colors from the album cover, auto start and return to the state before."""

import io
from datetime import timedelta

import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .test_custom_presets import setup, userdata  # noqa: F401  (fixture and helpers)

PRESET = "e71b2ef3-1b15-4c4b-b036-4b3d6efe58f8"
MUSIC = "b1c7e3d2-2f4a-4c39-9d7e-6a1f0c5e8b42"
PLAYER = "media_player.living_room"
PLAYER_2 = "media_player.bedroom"
LIGHTS = ["light.a", "light.b"]
LIGHTS_2 = ["light.c"]
COVER = [(0.64, 0.33), (0.15, 0.06)]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _image(colors):
    image = Image.new("RGB", (40, 40), colors[0])
    for i, color in enumerate(colors[1:], 1):
        image.paste(color, (0, i * 40 // len(colors), 40, 40))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def test_extract_cover_colors():
    from custom_components.scene_studio.music_scenes import extract_cover_colors

    colors = extract_cover_colors(_image([(220, 20, 30), (20, 40, 200)]))
    assert colors is not None and len(colors) >= 3  # two colors plus close variants
    assert extract_cover_colors(_image([(128, 128, 128), (10, 10, 10), (250, 250, 250)])) is None


def fake_lights(hass, entity_ids):
    attrs = {"supported_color_modes": ["xy", "color_temp"], "color_mode": "xy"}
    for entity_id in entity_ids:
        hass.states.async_set(entity_id, "off", attrs)

    async def turn_on(call):
        ids = call.data["entity_id"]
        for entity_id in [ids] if isinstance(ids, str) else ids:
            new = dict(hass.states.get(entity_id).attributes)
            for key in ("brightness", "xy_color", "color_temp_kelvin"):
                if key in call.data:
                    new[key] = tuple(call.data[key]) if key == "xy_color" else call.data[key]
            new["color_mode"] = "color_temp" if "color_temp_kelvin" in call.data else "xy"
            hass.states.async_set(entity_id, "on", new)

    async def turn_off(call):
        ids = call.data["entity_id"]
        for entity_id in [ids] if isinstance(ids, str) else ids:
            hass.states.async_set(entity_id, "off", dict(hass.states.get(entity_id).attributes))

    hass.services.async_register("light", "turn_on", turn_on)
    hass.services.async_register("light", "turn_off", turn_off)


def player(hass, entity_id, state, album="Album 1"):
    hass.states.async_set(entity_id, state, {
        "media_album_name": album, "media_artist": "Artist",
        "entity_picture": f"/api/media_player_proxy/{entity_id}?token=x&cache={album}",
    })


async def music_setup(hass, monkeypatch):
    import custom_components.scene_studio.music_scenes as ms

    fetched = []

    async def fake_cover(self, scene_id, state):
        fetched.append(self._album_key(state))
        self._colors[scene_id] = (self._album_key(state), COVER)
        return COVER

    monkeypatch.setattr(ms.MusicScenes, "_colors_from_cover", fake_cover)
    fake_lights(hass, LIGHTS + LIGHTS_2)
    player(hass, PLAYER, "paused")
    player(hass, PLAYER_2, "paused")
    await setup(hass, monkeypatch)
    return fetched


async def save(hass, name, lights, media_player, **music):
    r = await hass.services.async_call("scene_studio", "save_scene", {
        "name": name, "preset_id": MUSIC, "targets": {"entity_id": lights},
        "music": {"media_player": media_player, **music},
    }, blocking=True, return_response=True)
    return r["scene"]["id"]


def key(album, entity_id=PLAYER):
    return f"/api/media_player_proxy/{entity_id}|{album}"


def music(hass):
    return hass.data["scene_studio"]["music_scenes"]


def on(hass, entity_id):
    return hass.states.get(entity_id).state == "on"


async def wait(hass, seconds):
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


async def test_select_without_music_waits_for_a_cover(hass: HomeAssistant, monkeypatch, userdata):
    fetched = await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER)
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": scene_id}, blocking=True)
    await hass.async_block_till_done()
    assert not any(on(hass, l) for l in LIGHTS)  # no cover yet: nothing happens
    assert scene_id in music(hass).sessions
    # Music starts: the cover colors come on
    player(hass, PLAYER, "playing")
    await wait(hass, 6)
    assert fetched == [key("Album 1")]
    assert all(on(hass, l) for l in LIGHTS)


async def test_selected_without_music_is_not_restored(hass: HomeAssistant, monkeypatch, userdata):
    await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER)
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.a"}, blocking=True)
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": scene_id}, blocking=True)
    player(hass, PLAYER, "paused")
    await wait(hass, 31)
    assert on(hass, "light.a")


async def test_music_preset_applied_directly(hass: HomeAssistant, monkeypatch, userdata):
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import entity_registry as er

    area = ar.async_get(hass).async_create("Living room")
    registry = er.async_get(hass)
    entry = registry.async_get_or_create("media_player", "sonos", "living", suggested_object_id="living_room")
    registry.async_update_entity(entry.entity_id, area_id=area.id)
    light = registry.async_get_or_create("light", "hue", "a", suggested_object_id="a")
    registry.async_update_entity(light.entity_id, area_id=area.id)
    await music_setup(hass, monkeypatch)

    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": MUSIC, "targets": {"entity_id": ["light.a"]}}, blocking=True)
    assert not on(hass, "light.a")  # no music: nothing happens
    player(hass, PLAYER, "playing")
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": MUSIC, "targets": {"entity_id": ["light.a"]}}, blocking=True)
    assert music(hass).player_in_area(area.id) == PLAYER
    assert on(hass, "light.a")


async def test_music_end_restores_state_before(hass: HomeAssistant, monkeypatch, userdata):
    fetched = await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER)
    player(hass, PLAYER, "playing")
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": scene_id}, blocking=True)
    await hass.async_block_till_done()
    assert fetched == [key("Album 1")]
    from custom_components.scene_studio.file_utils import RUNTIME_PRESETS
    assert RUNTIME_PRESETS[f"music_{scene_id}"]["lights"] == [{"x": x, "y": y} for x, y in COVER]

    # A short pause (next track) does nothing
    player(hass, PLAYER, "paused")
    await wait(hass, 10)
    player(hass, PLAYER, "playing")
    await wait(hass, 40)
    assert scene_id in music(hass).sessions and on(hass, "light.a")

    # Music stops: after the delay the lights are off again, like before
    player(hass, PLAYER, "paused")
    await wait(hass, 31)
    assert scene_id not in music(hass).sessions
    assert not on(hass, "light.a") and not on(hass, "light.b")


async def test_auto_start_only_when_lights_off(hass: HomeAssistant, monkeypatch, userdata):
    await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER, auto_start="always")
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.a"}, blocking=True)
    player(hass, PLAYER, "playing")
    await hass.async_block_till_done()
    assert scene_id not in music(hass).sessions  # light was on: left alone

    player(hass, PLAYER, "paused")
    await hass.services.async_call("light", "turn_off", {"entity_id": "light.a"}, blocking=True)
    player(hass, PLAYER, "playing")
    await hass.async_block_till_done()
    assert scene_id in music(hass).sessions and on(hass, "light.b")


async def test_auto_start_when_on_overrides(hass: HomeAssistant, monkeypatch, userdata):
    await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER, auto_start="always", when_on=True)
    await hass.services.async_call("light", "turn_on", {"entity_id": "light.a"}, blocking=True)
    player(hass, PLAYER, "playing")
    await hass.async_block_till_done()
    assert scene_id in music(hass).sessions


async def test_follow_needs_active_music_scene(hass: HomeAssistant, monkeypatch, userdata):
    await music_setup(hass, monkeypatch)
    living = await save(hass, "Living music", LIGHTS, PLAYER)
    bedroom = await save(hass, "Bedroom music", LIGHTS_2, PLAYER_2, auto_start="follow")

    player(hass, PLAYER_2, "playing")
    await hass.async_block_till_done()
    assert bedroom not in music(hass).sessions  # nothing to follow
    player(hass, PLAYER_2, "paused")

    player(hass, PLAYER, "playing")
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": living}, blocking=True)
    await hass.async_block_till_done()
    # The music moves to the bedroom (Follow Me Music): bedroom starts, living room returns to off
    player(hass, PLAYER_2, "playing")
    player(hass, PLAYER, "paused")
    await hass.async_block_till_done()
    assert bedroom in music(hass).sessions and on(hass, "light.c")
    await wait(hass, 31)
    assert living not in music(hass).sessions and not on(hass, "light.a")


async def test_other_scene_takes_over_without_restore(hass: HomeAssistant, monkeypatch, userdata):
    await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER)
    player(hass, PLAYER, "playing")
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": scene_id}, blocking=True)
    await hass.services.async_call("scene_studio", "apply_preset", {
        "preset_id": PRESET, "targets": {"entity_id": LIGHTS}}, blocking=True)
    await hass.async_block_till_done()
    assert scene_id not in music(hass).sessions
    player(hass, PLAYER, "paused")
    await wait(hass, 31)
    assert on(hass, "light.a")  # the other scene stays


async def test_lights_off_ends_music_scene(hass: HomeAssistant, monkeypatch, userdata):
    await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER)
    player(hass, PLAYER, "playing")
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": scene_id}, blocking=True)
    await hass.services.async_call("light", "turn_off", {"entity_id": LIGHTS}, blocking=True)
    await hass.async_block_till_done()
    assert scene_id not in music(hass).sessions


async def test_new_cover_changes_colors_quickly(hass: HomeAssistant, monkeypatch, userdata):
    fetched = await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER)
    player(hass, PLAYER, "playing")
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": scene_id}, blocking=True)
    await hass.async_block_till_done()
    # Skipping through tracks: only the cover that stays is read
    player(hass, PLAYER, "playing", album="Album 2")
    player(hass, PLAYER, "playing", album="Album 3")
    await hass.async_block_till_done()
    assert fetched == [key("Album 1")]
    await wait(hass, 6)
    assert fetched == [key("Album 1"), key("Album 3")]


async def test_new_track_same_cover_moves_colors(hass: HomeAssistant, monkeypatch, userdata):
    fetched = await music_setup(hass, monkeypatch)
    scene_id = await save(hass, "Living music", LIGHTS, PLAYER)
    player(hass, PLAYER, "playing")
    await hass.services.async_call("scene_studio", "activate_saved_scene", {"id": scene_id}, blocking=True)
    await hass.async_block_till_done()
    calls = []
    import custom_components.scene_studio.music_scenes as ms
    original = ms.apply_preset

    async def spy(*args, **kwargs):
        calls.append(args[3])  # transition
        return await original(*args, **kwargs)

    monkeypatch.setattr(ms, "apply_preset", spy)
    hass.states.async_set(PLAYER, "playing", {**hass.states.get(PLAYER).attributes, "media_title": "Track 2"})
    await wait(hass, 6)
    assert fetched == [key("Album 1")]  # same cover, nothing to read
    assert calls == [ms.TRACK_TRANSITION]
