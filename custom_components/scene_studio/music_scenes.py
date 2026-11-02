# Added by andrejem (2026): music scenes. The colors of a saved scene come from the album cover of
# a media player. Selecting the scene activates it; it can also start by itself when music starts.
# When the music stops (or moves on to another room), the lights return to their state before.

from __future__ import annotations

import asyncio
import colorsys
import contextvars
import functools
import io
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.util import color as color_util

from .const import (
    ATTR_EXCLUDE,
    ATTR_KEEP_GROUPS,
    ATTR_OPTIONAL,
    ATTR_SCENE_PRESET_ID,
    ATTR_TARGETS,
    ATTR_TRANSITION,
    DOMAIN,
    SERVICE_APPLY_PRESET,
    SERVICE_START_DYNAMIC_SCENE,
    SERVICE_STOP_DYNAMIC_SCENES_FOR_TARGETS,
)
from .file_utils import PRESET_DATA, RUNTIME_PRESETS
from .presets import apply_preset
from .saved_scenes import build_service_call
from .util import ensure_list, filter_targets, resolve_entity_ids, resolve_targets

_LOGGER = logging.getLogger(__name__)

ATTR_MUSIC = "music"
AUTO_START_NEVER = "never"
AUTO_START_FOLLOW = "follow"  # only while a music scene is active in another room
AUTO_START_ALWAYS = "always"
AUTO_START_OPTIONS = (AUTO_START_NEVER, AUTO_START_FOLLOW, AUTO_START_ALWAYS)

STOP_DELAY = 30  # seconds without music before the lights return (track changes, hand-overs)
MIN_CHANGE_INTERVAL = 120  # seconds between two cover changes
COVER_TRANSITION = 3
RESTORE_TRANSITION = 2
MAX_COLORS = 5

# Set while the music scene manager calls services itself, so it does not end its own session
_INTERNAL = contextvars.ContextVar("scene_studio_music_internal", default=False)


def runtime_preset_id(scene_id: str) -> str:
    return f"music_{scene_id}"


def extract_cover_colors(data: bytes, max_colors: int = MAX_COLORS) -> list[tuple[float, float]] | None:
    """Dominant, colorful colors of a cover as xy. None if the cover has no usable color."""
    from PIL import Image  # Pillow ships with Home Assistant

    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((96, 96))
    quantized = image.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette() or []
    counts = sorted(quantized.getcolors() or [], reverse=True)
    total = sum(count for count, _ in counts) or 1

    candidates = []
    for count, index in counts:
        r, g, b = palette[index * 3: index * 3 + 3]
        hue, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if val < 0.18 or sat < 0.22:
            continue  # black, white, grey: nothing a lamp can show nicely
        candidates.append((count, hue, sat))

    picked: list[tuple[int, float, float]] = []
    for count, hue, sat in candidates:
        if all(min(abs(hue - h), 1 - abs(hue - h)) >= 0.06 for _, h, _ in picked):
            picked.append((count, hue, sat))
        if len(picked) >= max_colors:
            break

    if not picked or sum(count for count, _, _ in picked) / total < 0.08:
        return None

    colors = []
    for _, hue, sat in picked:
        sat = min(1.0, sat * 1.25 + 0.1)
        r, g, b = colorsys.hsv_to_rgb(hue, sat, 1.0)
        x, y = color_util.color_RGB_to_xy(round(r * 255), round(g * 255), round(b * 255))
        colors.append((round(x, 4), round(y, 4)))
    return colors


@dataclass
class MusicSession:
    scene_id: str
    media_player: str
    lights: list[str]
    snapshot: dict[str, dict]
    album: str | None = None
    last_change: float = 0.0
    stop_timer: object | None = None
    change_timer: object | None = None
    unsub_lights: object | None = field(default=None, repr=False)


class MusicScenes:
    """Runs music scenes: cover colors, auto start, return to the state before."""

    def __init__(self, hass: HomeAssistant, store, dynamic_scene_manager):
        self.hass = hass
        self.store = store
        self.manager = dynamic_scene_manager
        self.sessions: dict[str, MusicSession] = {}
        self._colors: dict[str, tuple[str | None, list]] = {}  # scene_id -> (album, colors)
        self._unsub_players = None
        self._unsub_store = store.add_listener(self._on_store_change)
        self._subscribe_players()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def is_internal() -> bool:
        return _INTERNAL.get()

    def _music_scenes(self) -> list[dict]:
        return [s for s in self.store.get_all() if s.get(ATTR_MUSIC)]

    def _player_of(self, scene: dict) -> str | None:
        return (scene.get(ATTR_MUSIC) or {}).get("media_player")

    def _scene_lights(self, scene: dict) -> list[str]:
        targets = scene.get(ATTR_TARGETS) or {}
        entity_ids = ensure_list(targets.get("entity_id"))
        lights = filter_targets(
            self.hass,
            resolve_targets(
                self.hass,
                entity_ids,
                ensure_list(targets.get("device_id")),
                ensure_list(targets.get("area_id")),
                ensure_list(targets.get("floor_id")),
                ensure_list(targets.get("label_id")),
            ),
            entity_ids,
            scene.get(ATTR_EXCLUDE),
            scene.get(ATTR_KEEP_GROUPS),
        )
        for entity_id in ensure_list(scene.get(ATTR_OPTIONAL)):
            for resolved in resolve_entity_ids(self.hass, entity_id):
                if resolved not in lights:
                    lights.append(resolved)
        return lights

    def _is_on(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == "on"

    def _playing(self, player: str) -> bool:
        state = self.hass.states.get(player)
        return state is not None and state.state == "playing"

    @staticmethod
    def _album_key(state) -> str | None:
        if state is None:
            return None
        attrs = state.attributes
        album = attrs.get("media_album_name")
        if album:
            return f"{attrs.get('media_artist') or attrs.get('media_album_artist') or ''}|{album}"
        picture = attrs.get("entity_picture")
        if not picture:
            return None
        # The access token in the picture URL changes over time, the cache key does not
        parts = urlsplit(picture)
        return f"{parts.path}|{parse_qs(parts.query).get('cache', [''])[0]}"

    def _fallback_colors(self, scene: dict) -> tuple[list, int]:
        for preset in PRESET_DATA.get("presets", []):
            if preset.get("id") == scene.get(ATTR_SCENE_PRESET_ID):
                return [(l["x"], l["y"]) for l in preset.get("lights", [])], preset.get("bri", 255)
        return [(0.5, 0.4)], 255

    def _set_runtime_preset(self, scene: dict, colors: list | None) -> str:
        fallback, bri = self._fallback_colors(scene)
        preset_id = runtime_preset_id(scene["id"])
        RUNTIME_PRESETS[preset_id] = {
            "id": preset_id,
            "name": scene["name"],
            "bri": bri,
            "lights": [{"x": x, "y": y} for x, y in (colors or fallback)],
        }
        return preset_id

    def session_for_light(self, entity_id: str) -> str | None:
        for scene_id, session in self.sessions.items():
            if entity_id in session.lights:
                return scene_id
        return None

    def get_state(self) -> dict:
        return {
            scene_id: {
                "media_player": s.media_player,
                "album": s.album,
                "colors": RUNTIME_PRESETS.get(runtime_preset_id(scene_id), {}).get("lights", []),
                "stopping": s.stop_timer is not None,
            }
            for scene_id, s in self.sessions.items()
        }

    # ------------------------------------------------------------------ subscriptions
    @callback
    def _on_store_change(self, scene_id, scene):
        if scene is None or not scene.get(ATTR_MUSIC):
            session = self.sessions.get(scene_id)
            if session is not None:
                self._drop(scene_id)
            RUNTIME_PRESETS.pop(runtime_preset_id(scene_id), None)
        self._subscribe_players()

    def _subscribe_players(self):
        if self._unsub_players is not None:
            self._unsub_players()
            self._unsub_players = None
        players = sorted({p for p in (self._player_of(s) for s in self._music_scenes()) if p})
        if players:
            self._unsub_players = async_track_state_change_event(self.hass, players, self._on_player)

    def _watch_lights(self, session: MusicSession):
        if session.unsub_lights is not None:
            session.unsub_lights()
        session.unsub_lights = async_track_state_change_event(
            self.hass, session.lights, functools.partial(self._on_light, session.scene_id)
        )

    @callback
    def _on_light(self, scene_id: str, event: Event):
        session = self.sessions.get(scene_id)
        if session is None or self.is_internal():
            return
        if not any(self._is_on(entity_id) for entity_id in session.lights):
            # Lights turned off by hand (or by a motion light): the music scene is over, nothing to restore
            _LOGGER.debug("Music scene %s ended, all lights off", scene_id)
            self._drop(scene_id)

    @callback
    def _on_player(self, event: Event):
        player = event.data["entity_id"]
        old = event.data.get("old_state")
        new = event.data.get("new_state")
        was_playing = old is not None and old.state == "playing"
        playing = new is not None and new.state == "playing"

        for scene in self._music_scenes():
            if self._player_of(scene) != player:
                continue
            session = self.sessions.get(scene["id"])
            if session is not None:
                if playing:
                    if session.stop_timer is not None:
                        session.stop_timer()
                        session.stop_timer = None
                    if self._album_key(new) != session.album:
                        self._schedule_cover(scene)
                elif was_playing and session.stop_timer is None:
                    session.stop_timer = async_call_later(
                        self.hass, STOP_DELAY, functools.partial(self._stop_after_music, scene["id"])
                    )
            elif playing and not was_playing:
                if self._may_auto_start(scene):
                    self.hass.async_create_task(self.async_activate(scene))

    # ------------------------------------------------------------------ auto start
    def _may_auto_start(self, scene: dict) -> bool:
        music = scene.get(ATTR_MUSIC) or {}
        mode = music.get("auto_start", AUTO_START_NEVER)
        if mode == AUTO_START_NEVER:
            return False
        if mode == AUTO_START_FOLLOW and not any(sid != scene["id"] for sid in self.sessions):
            return False
        if not music.get("when_on", False):
            if any(self._is_on(entity_id) for entity_id in self._scene_lights(scene)):
                return False
        # Only one music scene per media player starts by itself
        for other in self._music_scenes():
            if other["id"] in self.sessions and self._player_of(other) == self._player_of(scene):
                return False
        return True

    # ------------------------------------------------------------------ activate / stop
    async def async_activate(self, scene: dict) -> None:
        """Start (or re-select) a music scene."""
        scene_id = scene["id"]
        player = self._player_of(scene)
        lights = self._scene_lights(scene)
        previous = self.sessions.get(scene_id)
        snapshot = previous.snapshot if previous is not None else self._snapshot(lights)
        if previous is not None:
            self._cancel_timers(previous)
        # Another music scene on these lights hands over: its state from before the music is kept
        for other_id, other in list(self.sessions.items()):
            if other_id != scene_id and set(other.lights) & set(lights):
                if previous is None:
                    snapshot = {
                        **snapshot,
                        **{k: v for k, v in other.snapshot.items() if k in lights},
                    }
                self._drop(other_id)

        session = MusicSession(scene_id, player, lights, snapshot)
        cached_album, cached_colors = self._colors.get(scene_id, (None, None))
        state = self.hass.states.get(player) if player else None
        album = self._album_key(state) if self._playing(player) else cached_album
        colors = cached_colors if album == cached_album else None
        if colors is None and self._playing(player):
            colors = await self._colors_from_cover(scene_id, state)
        session.album = album
        session.last_change = time.monotonic()
        self.sessions[scene_id] = session
        preset_id = self._set_runtime_preset(scene, colors)

        service, data = build_service_call(scene)
        data[ATTR_SCENE_PRESET_ID] = preset_id
        token = _INTERNAL.set(True)
        try:
            if service == SERVICE_APPLY_PRESET:
                await self.hass.services.async_call(
                    DOMAIN, SERVICE_STOP_DYNAMIC_SCENES_FOR_TARGETS, {ATTR_TARGETS: data[ATTR_TARGETS]}, blocking=True
                )
            await self.hass.services.async_call(DOMAIN, service, data, blocking=True)
        finally:
            _INTERNAL.reset(token)
        self._watch_lights(session)
        _LOGGER.debug("Music scene %s active (%s colors)", scene["name"], "cover" if colors else "fallback")

    async def _colors_from_cover(self, scene_id: str, state) -> list | None:
        picture = state.attributes.get("entity_picture") if state is not None else None
        if not picture:
            return None
        album = self._album_key(state)
        try:
            if picture.startswith("http"):
                url = picture
            else:
                url = get_url(self.hass, prefer_external=False, allow_ip=True) + picture
            session = async_get_clientsession(self.hass, verify_ssl=False)
            async with asyncio.timeout(10):
                response = await session.get(url)
                response.raise_for_status()
                data = await response.read()
            colors = await self.hass.async_add_executor_job(extract_cover_colors, data)
        except (asyncio.TimeoutError, NoURLAvailableError, Exception) as err:  # noqa: BLE001
            _LOGGER.warning("Cover of %s could not be read: %s", state.entity_id, err)
            return None
        if colors:
            self._colors[scene_id] = (album, colors)
        return colors

    def _schedule_cover(self, scene: dict):
        session = self.sessions.get(scene["id"])
        if session is None:
            return
        wait = MIN_CHANGE_INTERVAL - (time.monotonic() - session.last_change)
        if session.change_timer is not None:
            return  # a change is already planned and will read the newest cover
        if wait <= 0:
            self.hass.async_create_task(self._change_cover(scene["id"]))
        else:
            session.change_timer = async_call_later(
                self.hass, wait, functools.partial(self._change_cover_later, scene["id"])
            )

    @callback
    def _change_cover_later(self, scene_id: str, _now=None):
        session = self.sessions.get(scene_id)
        if session is not None:
            session.change_timer = None
        self.hass.async_create_task(self._change_cover(scene_id))

    async def _change_cover(self, scene_id: str):
        session = self.sessions.get(scene_id)
        scene = self.store.get(scene_id)
        if session is None or scene is None:
            return
        session.change_timer = None
        state = self.hass.states.get(session.media_player)
        album = self._album_key(state)
        if album == session.album or not self._playing(session.media_player):
            return
        session.album = album
        session.last_change = time.monotonic()
        colors = await self._colors_from_cover(scene_id, state)
        if not colors:
            return  # colorless cover: keep the colors we have
        preset_id = self._set_runtime_preset(scene, colors)
        on = [entity_id for entity_id in session.lights if self._is_on(entity_id)]
        if not on:
            return
        settings = scene.get("light_brightness")
        token = _INTERNAL.set(True)
        try:
            await apply_preset(
                self.hass, preset_id, on, COVER_TRANSITION, True, True, scene.get("brightness"),
                light_brightness={k: v for k, v in (settings or {}).items() if v > 0} or None,
            )
        finally:
            _INTERNAL.reset(token)

    @callback
    def _stop_after_music(self, scene_id: str, _now=None):
        session = self.sessions.get(scene_id)
        if session is None:
            return
        session.stop_timer = None
        if self._playing(session.media_player):
            return
        self.hass.async_create_task(self.async_end(scene_id, restore=True))

    async def async_end(self, scene_id: str, restore: bool = True):
        session = self.sessions.get(scene_id)
        if session is None:
            return
        self._drop(scene_id)
        if not restore:
            return
        token = _INTERNAL.set(True)
        try:
            await self.hass.services.async_call(
                DOMAIN, SERVICE_STOP_DYNAMIC_SCENES_FOR_TARGETS, {ATTR_TARGETS: {"entity_id": session.lights}},
                blocking=True,
            )
            await self._restore(session.snapshot)
        finally:
            _INTERNAL.reset(token)
        _LOGGER.debug("Music scene %s ended, lights restored", scene_id)

    @callback
    def release_lights(self, light_entity_ids) -> None:
        """Another scene was started on these lights: music sessions on them end without restoring."""
        if self.is_internal() or not self.sessions:
            return
        lights = set(light_entity_ids)
        for entity_id in list(lights):
            lights.update(resolve_entity_ids(self.hass, entity_id))
        for scene_id, session in list(self.sessions.items()):
            if lights & set(session.lights):
                self._drop(scene_id)

    def _cancel_timers(self, session: MusicSession):
        for attr in ("stop_timer", "change_timer", "unsub_lights"):
            unsub = getattr(session, attr)
            if unsub is not None:
                unsub()
                setattr(session, attr, None)

    def _drop(self, scene_id: str):
        session = self.sessions.pop(scene_id, None)
        if session is not None:
            self._cancel_timers(session)

    # ------------------------------------------------------------------ snapshot
    def _snapshot(self, lights: list[str]) -> dict[str, dict]:
        snapshot = {}
        for entity_id in lights:
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            attrs = state.attributes
            snapshot[entity_id] = {
                "on": state.state == "on",
                "brightness": attrs.get("brightness"),
                "color_mode": attrs.get("color_mode"),
                "xy_color": attrs.get("xy_color"),
                "color_temp_kelvin": attrs.get("color_temp_kelvin"),
            }
        return snapshot

    async def _restore(self, snapshot: dict[str, dict]):
        tasks = []
        for entity_id, saved in snapshot.items():
            if not saved["on"]:
                if self._is_on(entity_id):
                    tasks.append(self.hass.services.async_call(
                        "light", "turn_off", {"entity_id": entity_id, ATTR_TRANSITION: RESTORE_TRANSITION},
                        blocking=True,
                    ))
                continue
            data = {"entity_id": entity_id, ATTR_TRANSITION: RESTORE_TRANSITION}
            if saved.get("brightness"):
                data["brightness"] = saved["brightness"]
            if saved.get("color_mode") == "color_temp" and saved.get("color_temp_kelvin"):
                data["color_temp_kelvin"] = saved["color_temp_kelvin"]
            elif saved.get("xy_color"):
                data["xy_color"] = saved["xy_color"]
            tasks.append(self.hass.services.async_call("light", "turn_on", data, blocking=True))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @callback
    def async_shutdown(self):
        for scene_id in list(self.sessions):
            self._drop(scene_id)
        if self._unsub_players is not None:
            self._unsub_players()
        self._unsub_store()
