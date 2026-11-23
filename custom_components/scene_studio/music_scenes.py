# Added by andrejem (2026): music scenes. A saved scene with the preset "Music" takes its colors from
# the album cover of a speaker (the one in the scene's room unless chosen). Selecting the scene
# activates it - until a cover is known nothing changes. It can also start by itself when music
# starts. When the music stops (or moves on to another room), the lights return to their state before.
# Covers are downloaded with a size limit; certificates are only skipped for Home Assistant itself.

from __future__ import annotations

import asyncio
import colorsys
import contextvars
import functools
import io
import math
import logging
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.network import get_url
from homeassistant.util import color as color_util

from .spatial import field_from_bytes
from .const import (
    ATTR_EXCLUDE,
    ATTR_KEEP_GROUPS,
    ATTR_OPTIONAL,
    ATTR_SCENE_PRESET_ID,
    ATTR_TARGETS,
    ATTR_TRANSITION,
    DOMAIN,
    MEDIA_PLAYER_ANY,
    MUSIC_PRESET_ID,
    SERVICE_APPLY_PRESET,
    SERVICE_START_DYNAMIC_SCENE,
    SERVICE_STOP_DYNAMIC_SCENES_FOR_TARGETS,
)
from .file_utils import PRESET_DATA, RUNTIME_PRESETS
from .presets import apply_preset
from .saved_scenes import build_service_call
from .util import ensure_list, lights_of_targets, resolve_entity_ids

_LOGGER = logging.getLogger(__name__)

ATTR_MUSIC = "music"
AUTO_START_NEVER = "never"
AUTO_START_FOLLOW = "follow"  # only while a music scene is active in another room
AUTO_START_ALWAYS = "always"
AUTO_START_OPTIONS = (AUTO_START_NEVER, AUTO_START_FOLLOW, AUTO_START_ALWAYS)

STOP_DELAY = 30  # seconds without music before the lights return (track changes, hand-overs)
MIN_CHANGE_INTERVAL = 5  # seconds: skipping through tracks does not make the lights flicker
# lights of a music scene turned off (e.g. by a motion light): if they come back on within this time
# while the music still plays, the scene continues with the current cover
WAKE_WINDOW = 30 * 60
COVER_TRANSITION = 3
TRACK_TRANSITION = 2  # new track, same cover: the colors move to other lamps
RESTORE_TRANSITION = 2
MAX_COVER_BYTES = 10 * 1024 * 1024  # album covers are a few hundred kB
MAX_COLORS = 5

# Set while the music scene manager calls services itself, so it does not end its own session
_INTERNAL = contextvars.ContextVar("scene_studio_music_internal", default=False)


# lowest saturation of a cover color on the lights
VIVID_MIN = 0.8
# a cover without colors (3.6): white light; for a dark cover dimmed to this part of the scene brightness
WHITE = (0.3227, 0.329)
DARK_DIM = 0.4


def runtime_preset_id(scene_id: str) -> str:
    return f"music_{scene_id}"


def is_music_scene(scene: dict | None) -> bool:
    return bool(scene) and (scene.get(ATTR_SCENE_PRESET_ID) == MUSIC_PRESET_ID or bool(scene.get(ATTR_MUSIC)))


def _cover_hsv(data: bytes, max_colors: int, focus: int) -> tuple[list[tuple[float, float]] | None, dict | None]:
    """The colors of a cover as (hue, saturation for the light), most important first (None if it has
    no usable color), and what else is known about it: ``light`` (average brightness), ``white``
    (part of the picture that is white), ``top`` (part with the first color), ``top_sat``.

    ``focus`` decides what "important" means: 100 = vivid (colorful pixels weighted by saturation x
    value, so small but vivid accents count and pale colors are ignored), 0 = area (every pixel counts
    the same, pale areas such as a light sky included). Values in between mix both.
    """
    from PIL import Image  # Pillow ships with Home Assistant

    f = min(100, max(0, focus)) / 100
    min_sat = 0.06 + 0.19 * f  # 0.25 for vivid: black, white, grey are nothing a lamp can show nicely
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.thumbnail((96, 96))
    pixels = list(image.getdata())
    bins = 24
    weight = [0.0] * bins
    hue_x = [0.0] * bins
    hue_y = [0.0] * bins
    sat_sum = [0.0] * bins
    count = [0] * bins
    colorful = white = 0
    light = 0.0
    for r, g, b in pixels:
        hue, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        light += val
        if sat < 0.06 and val > 0.8:
            white += 1
        if sat < min_sat or val < 0.25:
            continue
        colorful += 1
        count[int(hue * bins) % bins] += 1
        w = sat * val if f == 1 else (sat * val) ** f
        k = int(hue * bins) % bins
        weight[k] += w
        hue_x[k] += w * math.cos(2 * math.pi * hue)
        hue_y[k] += w * math.sin(2 * math.pi * hue)
        sat_sum[k] += w * sat
    if not pixels:
        return None, None
    stats = {"light": light / len(pixels), "white": white / len(pixels), "top": 0.0, "top_sat": 0.0}
    if colorful / len(pixels) < 0.03:
        return None, stats

    order = sorted(range(bins), key=lambda k: -weight[k])
    top = weight[order[0]]
    picked = []
    for k in order:
        if weight[k] < top * 0.03 or len(picked) >= max_colors:
            break
        if any(min(abs(k - p), bins - abs(k - p)) < 2 for p in picked):
            continue  # too close to a color we already have
        picked.append(k)

    # lamps look washed out with the cover's own saturation (often 40-60 %): keep the hue, but use a
    # vivid 80-100 % for the light. Towards "area" the main color stays closer to the cover (from
    # 35 %), so a light blue sky stays light blue; the other colors are accents and stay vivid.
    hsv = []
    for k in picked:
        hue = (math.atan2(hue_y[k], hue_x[k]) / (2 * math.pi)) % 1
        cover_sat = sat_sum[k] / weight[k]
        vivid_min = VIVID_MIN if hsv else 0.35 + (VIVID_MIN - 0.35) * f
        sat = vivid_min + (1.0 - vivid_min) * min(1.0, max(0.0, (cover_sat - 0.25) / 0.6))
        hsv.append((hue, sat))
    stats["top"] = count[picked[0]] / len(pixels)
    stats["top_sat"] = sat_sum[picked[0]] / weight[picked[0]]
    return hsv, stats


def _xy(hsv: list[tuple[float, float]]) -> list[tuple[float, float]]:
    colors = []
    for hue, sat in hsv:
        r, g, b = colorsys.hsv_to_rgb(hue % 1, sat, 1.0)
        x, y = color_util.color_RGB_to_xy(round(r * 255), round(g * 255), round(b * 255))
        colors.append((round(x, 4), round(y, 4)))
    return colors


def extract_cover_palette(data: bytes, focus: int = 100, max_colors: int = MAX_COLORS) -> dict | None:
    """Colors of a cover as xy: ``colors`` (all, most important first), ``main`` (the most important
    color with two close variants, for main lights) and ``accent`` (the other colors, for accent
    lights). None only for an empty picture.

    Covers with only one or two colors get close variants, so a dynamic scene still has something to
    change between; a cover with a single color gets accents a bit further away from it.

    A cover without colors gives white, with ``neutral`` = "white" (bright cover) or "dark" (dark
    cover, the lights are dimmed then). A cover that is mostly white with some color gives white as
    main color and the colors as accents, the more the focus is on areas (never for vivid).
    """
    hsv, stats = _cover_hsv(data, max_colors, focus)
    if stats is None:
        return None
    if not hsv:
        neutral = "white" if stats["light"] >= 0.5 else "dark"
        return {"colors": [WHITE], "main": [WHITE], "accent": [WHITE], "neutral": neutral}
    f = min(100, max(0, focus)) / 100
    if f < 1 and stats["white"] * (1 - f) > stats["top"]:
        # white fills more of the cover than its first color: white is the main color
        sat = VIVID_MIN + (1.0 - VIVID_MIN) * min(1.0, max(0.0, (stats["top_sat"] - 0.25) / 0.6))
        accent = _xy([(hsv[0][0], sat)] + hsv[1:])
        return {"colors": [WHITE] + accent, "main": [WHITE], "accent": accent, "neutral": None}
    floor = 0.35 + (VIVID_MIN - 0.35) * f
    hue, sat = hsv[0]
    main = [(hue, sat), (hue + 0.03, sat), (hue - 0.03, max(floor, sat * 0.9))]
    accent = hsv[1:] or [(hue + 0.09, max(VIVID_MIN, sat)), (hue - 0.09, max(VIVID_MIN, sat))]
    colors = list(hsv)
    if len(colors) < 3:
        for i, (h, s) in enumerate(list(colors)):
            low = floor if i == 0 else VIVID_MIN
            colors.append(((h + 0.035) % 1, s))
            colors.append(((h - 0.035) % 1, max(low, s * 0.9)))
    return {"colors": _xy(colors[: max(max_colors, 3)]), "main": _xy(main), "accent": _xy(accent), "neutral": None}


def extract_cover_colors(data: bytes, max_colors: int = MAX_COLORS) -> list[tuple[float, float]] | None:
    """Dominant, colorful colors of a cover as xy (vivid colors first); white for a cover without colors."""
    palette = extract_cover_palette(data, 100, max_colors)
    return palette["colors"] if palette else None


@dataclass
class MusicSession:
    scene_id: str
    media_player: str | None
    lights: list[str]
    snapshot: dict[str, dict]
    applied: bool = False  # colors are on the lights (only then there is something to restore)
    album: str | None = None
    track: str | None = None
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
        # scene_id -> (snapshot before the music, unsub light listener, unsub expiry timer)
        self._sleeping: dict[str, tuple[dict, object, object]] = {}
        self._colors: dict[str, tuple[str | None, list]] = {}  # scene_id -> (album, colors)
        self._pools: dict[str, dict] = {}  # scene_id -> main and accent colors of that cover, focus used
        self._unsub_players = None
        self._unsub_store = store.add_listener(self._on_store_change)
        # The speaker of a room can change when a scene or a speaker is moved to another room
        self._unsub_registry = hass.bus.async_listen(
            er.EVENT_ENTITY_REGISTRY_UPDATED, self._on_registry_change
        )
        # A scene of Home Assistant (scene.turn_on, scene.apply) on these lights ends a music scene
        self._unsub_services = hass.bus.async_listen(
            EVENT_CALL_SERVICE, self._on_service_call, event_filter=self._is_scene_call
        )
        self._stopped_at: dict[str, float] = {}  # media player -> when it last stopped playing
        self._dismissed: set[str] = set()  # scenes ended by hand: no auto start until the music paused
        # time of day scenes that follow the phase end the same way (set by the integration)
        self.also_release = None
        self._subscribe_players()

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def is_internal() -> bool:
        return _INTERNAL.get()

    def _music_scenes(self) -> list[dict]:
        return [s for s in self.store.get_all() if is_music_scene(s)]

    @staticmethod
    def _is_any(scene: dict) -> bool:
        return (scene.get(ATTR_MUSIC) or {}).get("media_player") == MEDIA_PLAYER_ANY

    def _candidates(self) -> list[str]:
        """Speakers an "any speaker" scene listens to: all Sonos, without Sonos all media players."""
        sonos = [e.entity_id for e in er.async_get(self.hass).entities.values()
                 if e.domain == "media_player" and e.platform == "sonos" and not e.disabled_by]
        return sorted(sonos or self.hass.states.async_entity_ids("media_player"))

    def _music(self, player: str | None) -> bool:
        """Playing with a cover: TV sound or line-in on a Sonos has none and gives no colors."""
        state = self.hass.states.get(player) if player else None
        return state is not None and state.state == "playing" and bool(state.attributes.get("entity_picture"))

    def _playing_candidate(self, exclude: str | None = None) -> str | None:
        """The speaker with a cover that started playing most recently."""
        playing = [self.hass.states.get(p) for p in self._candidates() if p != exclude and self._music(p)]
        playing = [s for s in playing if s is not None]
        return max(playing, key=lambda s: s.last_changed).entity_id if playing else None

    def _player_of(self, scene: dict) -> str | None:
        chosen = (scene.get(ATTR_MUSIC) or {}).get("media_player")
        if chosen == MEDIA_PLAYER_ANY:
            session = self.sessions.get(scene["id"])
            if session is not None and session.media_player and self._music(session.media_player):
                return session.media_player
            return self._playing_candidate() or (session.media_player if session else None)
        if chosen:
            return chosen
        return self.player_in_area(self._scene_area(scene))

    def _scene_area(self, scene: dict) -> str | None:
        """Room of the scene entity, otherwise the (first) room of its lights."""
        registry = er.async_get(self.hass)
        entity_id = registry.async_get_entity_id("scene", DOMAIN, f"saved_scene_{scene['id']}")
        entry = registry.async_get(entity_id) if entity_id else None
        if entry is not None and entry.area_id:
            return entry.area_id
        targets = scene.get(ATTR_TARGETS) or {}
        areas = ensure_list(targets.get("area_id"))
        if areas:
            return areas[0]
        for light in self._scene_lights(scene):
            area = self._entity_area(light)
            if area:
                return area
        return None

    def _entity_area(self, entity_id: str) -> str | None:
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry is None:
            return None
        if entry.area_id:
            return entry.area_id
        device = dr.async_get(self.hass).async_get(entry.device_id) if entry.device_id else None
        return device.area_id if device else None

    def player_in_area(self, area_id: str | None) -> str | None:
        """The speaker of a room: a Sonos if there is one, otherwise any media player."""
        if not area_id:
            return None
        found = []
        for entry in er.async_get(self.hass).entities.values():
            if entry.domain != "media_player" or entry.disabled_by:
                continue
            if self._entity_area(entry.entity_id) == area_id:
                found.append((entry.platform != "sonos", entry.entity_id))
        return sorted(found)[0][1] if found else None

    def _scene_lights(self, scene: dict) -> list[str]:
        lights = lights_of_targets(
            self.hass, scene.get(ATTR_TARGETS) or {}, scene.get(ATTR_EXCLUDE), scene.get(ATTR_KEEP_GROUPS)
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
        """Identifies the cover. The access token in the picture URL changes, the cache key does not."""
        if state is None:
            return None
        attrs = state.attributes
        picture = attrs.get("entity_picture")
        if picture:
            parts = urlsplit(picture)
            return f"{parts.path}|{parse_qs(parts.query).get('cache', [''])[0]}"
        album = attrs.get("media_album_name")
        return f"{attrs.get('media_artist') or ''}|{album}" if album else None

    @staticmethod
    def _track_key(state) -> str | None:
        if state is None:
            return None
        attrs = state.attributes
        return f"{attrs.get('media_artist') or ''}|{attrs.get('media_title') or ''}|{attrs.get('media_content_id') or ''}"

    def _set_runtime_preset(self, scene: dict, colors: list, preset_id: str | None = None) -> str:
        preset_id = preset_id or runtime_preset_id(scene["id"])
        preset = {
            "id": preset_id,
            "name": scene.get("name", "Music"),
            "bri": 255,
            "lights": [{"x": x, "y": y} for x, y in colors],
        }
        # main and accent lights (3.6): they take their colors from their own part of the cover colors
        roles = (scene.get(ATTR_MUSIC) or {}).get("roles") or {}
        pools = self._pools.get(scene.get("id"))
        if roles and pools:
            preset["roles"] = dict(roles)
            preset["pools"] = pools
        if pools and pools.get("dim"):
            preset["dim"] = pools["dim"]  # dark cover without colors: white, but dimmed
        if pools and pools.get("field"):
            preset["field"] = pools["field"]
        RUNTIME_PRESETS[preset_id] = preset
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
        if scene is None or not is_music_scene(scene):
            session = self.sessions.get(scene_id)
            if session is not None:
                self._drop(scene_id)
            RUNTIME_PRESETS.pop(runtime_preset_id(scene_id), None)
        self._subscribe_players()

    @callback
    def _on_registry_change(self, event: Event):
        entity_id = event.data.get("entity_id", "")
        if entity_id.startswith(("scene.", "media_player.")):
            self._subscribe_players()

    def _subscribe_players(self):
        if self._unsub_players is not None:
            self._unsub_players()
            self._unsub_players = None
        scenes = self._music_scenes()
        players = {p for p in (self._player_of(s) for s in scenes) if p}
        if any(self._is_any(s) for s in scenes):
            players.update(self._candidates())
        players = sorted(players)
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
        if session is None or self.is_internal() or not session.applied:
            return
        if not any(self._is_on(entity_id) for entity_id in session.lights):
            # Lights turned off by hand (or by a motion light): the music scene ends. Only with the
            # option "resume" it pauses instead and continues with the current cover when the lights
            # come back on soon while the music plays.
            scene = self.store.get(scene_id)
            if scene is not None and (scene.get(ATTR_MUSIC) or {}).get("resume", False):
                _LOGGER.debug("Music scene %s paused, all lights off", scene_id)
                self._sleep(session)
            self._dismissed.add(scene_id)
            self._drop(scene_id)
            self._stop_loop(scene_id)

    def _sleep(self, session: MusicSession):
        self._wake_cancel(session.scene_id)
        unsub_lights = async_track_state_change_event(
            self.hass, session.lights, functools.partial(self._on_sleeping_light, session.scene_id)
        )
        unsub_timer = async_call_later(
            self.hass, WAKE_WINDOW, functools.partial(self._wake_expired, session.scene_id)
        )
        self._sleeping[session.scene_id] = (session.snapshot, unsub_lights, unsub_timer)

    def _wake_cancel(self, scene_id: str):
        entry = self._sleeping.pop(scene_id, None)
        if entry is not None:
            for unsub in entry[1:]:
                unsub()

    @callback
    def _wake_expired(self, scene_id: str, _now=None):
        entry = self._sleeping.pop(scene_id, None)
        if entry is not None:
            entry[1]()

    @callback
    def _on_sleeping_light(self, scene_id: str, event: Event):
        new = event.data.get("new_state")
        if self.is_internal() or new is None or new.state != "on" or scene_id in self.sessions:
            return
        snapshot = self._sleeping[scene_id][0] if scene_id in self._sleeping else {}
        self._wake_cancel(scene_id)
        scene = self.store.get(scene_id)
        if scene is None or not is_music_scene(scene):
            return
        player = self._player_of(scene)
        if not player or not self._playing(player):
            return  # no music anymore: the lights stay as they were turned on
        _LOGGER.debug("Music scene %s continues, lights back on", scene_id)
        self.hass.async_create_task(self._wake(scene, snapshot))

    async def _wake(self, scene: dict, snapshot: dict):
        await self.async_activate(scene)
        session = self.sessions.get(scene["id"])
        if session is not None and snapshot:
            session.snapshot = snapshot  # at the end of the music: the state before the music

    @callback
    def _on_player(self, event: Event):
        player = event.data["entity_id"]
        old = event.data.get("old_state")
        new = event.data.get("new_state")
        was_playing = old is not None and old.state == "playing"
        playing = new is not None and new.state == "playing"
        # A music scene that was ended by hand stays off while this music goes on: it may start by
        # itself again only after a real break. Many players leave "playing" for a moment between two
        # tracks, which would otherwise count as "music starts".
        stopped_at = self._stopped_at.get(player)
        after_break = stopped_at is None or time.monotonic() - stopped_at >= STOP_DELAY
        if was_playing and not playing:
            self._stopped_at[player] = time.monotonic()

        for scene in self._music_scenes():
            session = self.sessions.get(scene["id"])
            if self._is_any(scene):
                if player not in self._candidates():
                    continue
                if not self._music(player) and (session is None or session.media_player != player):
                    continue  # e.g. TV sound on a Sonos: no cover, no colors
                if session is not None and session.media_player != player:
                    if not self._music(session.media_player):
                        # the speaker of the scene went quiet, another one plays: follow it
                        session.media_player = player
                        session.album = session.track = None
                    else:
                        continue
                elif session is None and not playing:
                    continue
            elif self._player_of(scene) != player:
                continue
            if session is not None:
                if playing:
                    if session.stop_timer is not None:
                        session.stop_timer()
                        session.stop_timer = None
                    if self._album_key(new) != session.album or self._track_key(new) != session.track:
                        self._schedule_cover(scene)
                elif was_playing and session.stop_timer is None:
                    session.stop_timer = async_call_later(
                        self.hass, STOP_DELAY, functools.partial(self._stop_after_music, scene["id"])
                    )
            elif playing and not was_playing:
                if scene["id"] in self._dismissed:
                    if not after_break:
                        continue
                    self._dismissed.discard(scene["id"])
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
        self._wake_cancel(scene_id)
        self._dismissed.discard(scene_id)
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
        focus = (scene.get(ATTR_MUSIC) or {}).get("focus", 100)
        if colors is not None and self._pools.get(scene_id, {}).get("focus", 100) != focus:
            colors = None  # the color choice of the scene was changed: read the cover again
        if colors is None and self._playing(player):
            colors = await self._colors_from_cover(scene_id, state)
        session.album = album
        session.track = self._track_key(state) if self._playing(player) else None
        session.last_change = time.monotonic()
        session.applied = previous is not None and previous.applied
        self.sessions[scene_id] = session
        self._watch_lights(session)
        if colors:
            await self._start_lights(scene, session, colors)
        _LOGGER.debug("Music scene %s selected (%s)", scene["name"], "cover colors" if colors else "waiting for a cover")

    async def _start_lights(self, scene: dict, session: MusicSession, colors: list) -> None:
        """Put the cover colors on the lights of the scene (static or dynamic, like any scene)."""
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
        session.applied = True

    async def async_adhoc_preset(self, targets: dict) -> str | None:
        """Preset "Music" applied directly (presets tab, automations): the current cover of the
        speaker in the room of these lights. None if no music is playing there."""
        lights = lights_of_targets(self.hass, targets)
        areas = ensure_list(targets.get("area_id")) or [a for a in (self._entity_area(l) for l in lights) if a]
        for area in dict.fromkeys(areas):
            player = self.player_in_area(area)
            if player and self._playing(player):
                colors = await self._colors_from_cover(f"adhoc_{player}", self.hass.states.get(player))
                if colors:
                    return self._set_runtime_preset({"name": "Music"}, colors, f"music_adhoc_{player}")
        return None

    async def _colors_from_cover(self, scene_id: str, state) -> list | None:
        picture = state.attributes.get("entity_picture") if state is not None else None
        if not picture:
            return None
        album = self._album_key(state)
        try:
            if picture.startswith("http"):
                # a cover on the internet: certificates are checked
                url = picture
                session = async_get_clientsession(self.hass)
            else:
                # Home Assistant's own media player proxy, reached on the internal URL, which
                # often has a self-signed certificate
                url = get_url(self.hass, prefer_external=False, allow_ip=True) + picture
                session = async_get_clientsession(self.hass, verify_ssl=False)
            async with asyncio.timeout(10):
                response = await session.get(url)
                response.raise_for_status()
                if int(response.headers.get("Content-Length") or 0) > MAX_COVER_BYTES:
                    raise ValueError("cover too large")
                chunks, size = [], 0
                async for chunk in response.content.iter_chunked(65536):
                    size += len(chunk)
                    if size > MAX_COVER_BYTES:
                        raise ValueError("cover too large")
                    chunks.append(chunk)
                data = b"".join(chunks)
            scene = self.store.get(scene_id)
            focus = (scene.get(ATTR_MUSIC) or {}).get("focus", 100) if scene else 100
            palette = await self.hass.async_add_executor_job(extract_cover_palette, data, focus)
        except Exception as err:  # noqa: BLE001 - no cover colors, the preset stays
            _LOGGER.warning("Cover of %s could not be read: %s", state.entity_id, err)
            return None
        if not palette:
            return None
        self._colors[scene_id] = (album, palette["colors"])
        self._pools[scene_id] = {
            "main": palette["main"], "accent": palette["accent"], "focus": focus,
            "dim": DARK_DIM if palette.get("neutral") == "dark" else None,
        }
        if scene and scene.get("spatial") and not palette.get("neutral"):
            # room canvas (4.0): the cover lies over the room, left on the cover is left in the room
            self._pools[scene_id]["field"] = await self.hass.async_add_executor_job(field_from_bytes, data)
        return palette["colors"]

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
        if not self._playing(session.media_player):
            return
        state = self.hass.states.get(session.media_player)
        album, track = self._album_key(state), self._track_key(state)
        if album == session.album and track == session.track:
            return
        new_cover = album != session.album
        session.album, session.track = album, track
        session.last_change = time.monotonic()
        preset_id = runtime_preset_id(scene_id)
        if new_cover:
            colors = await self._colors_from_cover(scene_id, state)
            if colors and not session.applied:
                await self._start_lights(scene, session, colors)
                return
            if colors:
                preset_id = self._set_runtime_preset(scene, colors)
            # cover that cannot be read: keep the colors we have, but still move them on
        if not session.applied:
            return
        on = [entity_id for entity_id in session.lights if self._is_on(entity_id)]
        if not on or preset_id not in RUNTIME_PRESETS:
            return
        settings = scene.get("light_brightness")
        token = _INTERNAL.set(True)
        try:
            await apply_preset(
                self.hass, preset_id, on, COVER_TRANSITION if new_cover else TRACK_TRANSITION, True, True,
                scene.get("brightness"),
                light_brightness={k: v for k, v in (settings or {}).items() if v > 0} or None,
                gradient=scene.get("gradient", True),
                saturation=scene.get("saturation"),
                spatial=scene.get("spatial"),
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
        scene = self.store.get(scene_id)
        if scene is not None and self._is_any(scene):
            other = self._playing_candidate(exclude=session.media_player)
            if other is not None:
                # music still plays elsewhere: take its cover instead of ending
                session.media_player = other
                session.album = session.track = None
                self._schedule_cover(scene)
                return
        self.hass.async_create_task(self.async_end(scene_id, restore=True))

    async def async_end(self, scene_id: str, restore: bool = True):
        session = self.sessions.get(scene_id)
        if session is None:
            return
        self._drop(scene_id)
        if not restore or not session.applied:
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
        if self.is_internal() or not (self.sessions or self._sleeping):
            return
        lights = set(light_entity_ids)
        for entity_id in list(lights):
            lights.update(resolve_entity_ids(self.hass, entity_id))
        for scene_id, session in list(self.sessions.items()):
            if lights & set(session.lights):
                self._dismissed.add(scene_id)
                self._drop(scene_id)
                self._stop_loop(scene_id)
        for scene_id in list(self._sleeping):
            scene = self.store.get(scene_id)
            if scene is None or lights & set(self._scene_lights(scene)):
                self._wake_cancel(scene_id)

    @callback
    def stop_all(self) -> None:
        """Stop everything (service stop_all_dynamic_scenes): the lights stay as they are."""
        if self.is_internal():
            return
        for scene_id in list(self.sessions):
            self._dismissed.add(scene_id)
            self._drop(scene_id)
        for scene_id in list(self._sleeping):
            self._wake_cancel(scene_id)

    @staticmethod
    @callback
    def _is_scene_call(event_data) -> bool:
        return event_data.get("domain") == "scene" and event_data.get("service") in ("turn_on", "apply")

    @callback
    def _on_service_call(self, event: Event):
        """A scene of Home Assistant was started: music scenes on its lights end (like with a scene of
        Scene Studio). Changing lights directly (dimming, a color, on/off) does not end them."""
        if self.is_internal() or not (self.sessions or self._sleeping or self.also_release):
            return
        data = event.data.get("service_data") or {}
        if event.data.get("service") == "apply":
            entities = data.get("entities")
            lights = list(entities) if isinstance(entities, dict) else []
        else:
            lights = []
            registry = er.async_get(self.hass)
            for scene_entity in ensure_list(data.get("entity_id")):
                entry = registry.async_get(scene_entity)
                if entry is not None and entry.platform == DOMAIN:
                    continue  # our own scenes release the lights themselves when they start
                state = self.hass.states.get(scene_entity)
                members = state.attributes.get("entity_id") if state else None
                lights.extend([members] if isinstance(members, str) else list(members or []))
        if lights:
            self.release_lights(lights)
            if self.also_release:
                members = set(lights)
                for entity_id in lights:
                    members.update(resolve_entity_ids(self.hass, entity_id))
                self.also_release(members)

    def _stop_loop(self, scene_id: str) -> None:
        """The color loop of an ended music scene must not go on (or come back with the lights)."""
        preset_id = runtime_preset_id(scene_id)
        for dynamic in list(self.manager.get_all()):
            if dynamic.parameters.get("preset_id") == preset_id:
                self.manager.delete_by_id(dynamic.id)

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
        for scene_id in list(self._sleeping):
            self._wake_cancel(scene_id)
        if self._unsub_players is not None:
            self._unsub_players()
        self._unsub_store()
        self._unsub_registry()
        self._unsub_services()
