# Added by andrejem (2026): room canvas (4.0). The user places the lights of a room on a plan once.
# A scene with "spatial" lays the picture of its preset over the plan: every light gets the preset
# color that is closest to the picture at its place, so the colors are spread through the room like
# in the picture instead of by chance (see assign). Dynamic scenes move the picture slowly through the room.
# Lights without a place and scenes without "spatial" behave as before.

from __future__ import annotations

import bisect
import colorsys
import logging
import math
import os
import time
import uuid

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import color as color_util

from .const import DOMAIN
from .util import resolve_entity_ids

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.room_plans"

# the plan is a 16:10 area, the picture is cut to it; small is enough, the colors are smoothed anyway
FIELD_SIZE = (32, 20)
# a dynamic scene moves the picture once through the room in this many color changes
STEPS_PER_PASS = 10
STRIP_POINTS = 5

_fields: dict[tuple, list] = {}


class PlanError(Exception):
    """Error with a message for the user (shown in the panel)."""


def _clamp(value) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def clean_lights(lights) -> dict:
    out = {}
    for entity_id, place in (lights or {}).items():
        if not isinstance(entity_id, str) or not entity_id.startswith("light.") or not isinstance(place, dict):
            raise PlanError("Invalid light")
        item = {"x": _clamp(place["x"]), "y": _clamp(place["y"])}
        if place.get("x2") is not None and place.get("y2") is not None:
            # light strips and other long lights: from (x, y) to (x2, y2)
            item["x2"], item["y2"] = _clamp(place["x2"]), _clamp(place["y2"])
        out[entity_id] = item
    return out


class RoomPlans:
    """Places of the lights on the plans of the rooms."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._plans: dict[str, dict] = {}

    async def async_load(self):
        data = await self._store.async_load()
        self._plans = {p["id"]: p for p in (data or {}).get("plans", [])}

    async def _async_save(self):
        await self._store.async_save({"plans": list(self._plans.values())})

    def get_all(self) -> list[dict]:
        return sorted(self._plans.values(), key=lambda p: p["name"].lower())

    async def async_save_plan(self, data: dict) -> dict:
        name = (data.get("name") or "").strip()
        if not name:
            raise PlanError("Please enter a name")
        plan_id = data.get("id") or str(uuid.uuid4())
        if data.get("id") and plan_id not in self._plans:
            raise PlanError("Unknown plan")
        plan = {"id": plan_id, "name": name, "lights": clean_lights(data.get("lights"))}
        if data.get("area_id"):
            plan["area_id"] = data["area_id"]
        self._plans[plan_id] = plan
        await self._async_save()
        return plan

    async def async_delete_plan(self, plan_id: str) -> bool:
        if plan_id not in self._plans:
            return False
        del self._plans[plan_id]
        await self._async_save()
        return True

    def place_of(self, entity_id: str) -> dict | None:
        """Place of a light: its own, or the one of a group it belongs to (or that it consists of)."""
        for plan in self._plans.values():
            place = plan["lights"].get(entity_id)
            if place is not None:
                return place
        for plan in self._plans.values():
            for key, place in plan["lights"].items():
                if entity_id in resolve_entity_ids(self.hass, key):
                    return place
        members = [m for m in resolve_entity_ids(self.hass, entity_id) if m != entity_id]
        places = [p for p in (self._own(m) for m in members) if p is not None]
        if places:
            # a group used as one light sits in the middle of its lights
            return {"x": sum(p["x"] for p in places) / len(places), "y": sum(p["y"] for p in places) / len(places)}
        return None

    def _own(self, entity_id):
        for plan in self._plans.values():
            if entity_id in plan["lights"]:
                return plan["lights"][entity_id]
        return None


# --- the picture of a preset as a small field of colors ------------------------------------------------

def _field_from_image(source) -> list | None:
    """Rows of (r, g, b), blocking (PIL). ``source`` is a path or the bytes of a picture."""
    try:
        import io

        from PIL import Image, ImageFilter, ImageOps

        image = Image.open(io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source).convert("RGB")
        image = ImageOps.fit(image, (FIELD_SIZE[0] * 4, FIELD_SIZE[1] * 4)).filter(ImageFilter.GaussianBlur(4))
        image = image.resize(FIELD_SIZE)
        pixels = list(image.getdata())
    except Exception as err:  # noqa: BLE001 - without picture the scene works as before
        _LOGGER.debug("Picture for the room canvas cannot be read: %s", err)
        return None
    width = FIELD_SIZE[0]
    return [pixels[row * width:(row + 1) * width] for row in range(FIELD_SIZE[1])]


def field_from_bytes(data: bytes) -> list | None:
    """Field of a picture that is not a file (album cover of a music scene); blocking."""
    return _field_from_image(data)


def _image_path(preset: dict) -> str | None:
    from .custom_presets import USER_IMG_PREFIX
    from .file_utils import BASE_PATH
    from .images import is_private, private_image_path

    img = preset.get("img")
    if not img:
        return None
    if is_private(preset) or img.startswith(USER_IMG_PREFIX):
        return private_image_path(img)
    path = os.path.join(BASE_PATH, "assets", img)
    return path if os.path.isfile(path) else None


async def async_field_for(hass: HomeAssistant, preset: dict) -> list | None:
    """The picture of the preset as field; None if it has none (then nothing is spatial)."""
    if preset.get("field"):
        return preset["field"]  # runtime presets (music) bring their own
    key = (preset.get("id"), preset.get("img"))
    if key not in _fields:
        path = await hass.async_add_executor_job(_image_path, preset)
        field = await hass.async_add_executor_job(_field_from_image, path) if path else None
        if len(_fields) > 64:
            _fields.clear()
        _fields[key] = field
    return _fields[key]


# --- colors by place --------------------------------------------------------------------------------

def _mirror(value: float) -> float:
    value = value % 2.0
    return 2.0 - value if value > 1.0 else value


def _sample(field, x: float, y: float):
    height, width = len(field), len(field[0])
    return field[min(height - 1, int(_mirror(y) * height))][min(width - 1, int(_mirror(x) * width))]


def _chroma_rgb(rgb) -> tuple[float, float]:
    """Color without its brightness (the lights have their own): a point on the color wheel."""
    hue, sat, _val = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    return (sat * math.cos(hue * 2 * math.pi), sat * math.sin(hue * 2 * math.pi))


def _chroma_xy(xy) -> tuple[float, float]:
    return _chroma_rgb(color_util.color_xy_to_RGB(xy[0], xy[1]))


def _ranks(field):
    """Where each cell of the picture stands between its two most different colors, 0..1.

    The colors of a picture are often close together (a blue-green aurora, a warm sunset). Comparing
    them one by one with the preset colors would give most lights the same color. So only the order
    counts: the cells are sorted along the direction in which the colors of the picture differ most,
    and a cell is described by its rank in that order. Returns (ranks as rows, axis, center) or None
    for a picture in one color.
    """
    cells = [_chroma_rgb(pixel) for row in field for pixel in row]
    n = len(cells)
    mx, my = sum(c[0] for c in cells) / n, sum(c[1] for c in cells) / n
    cxx = sum((c[0] - mx) ** 2 for c in cells) / n
    cyy = sum((c[1] - my) ** 2 for c in cells) / n
    cxy = sum((c[0] - mx) * (c[1] - my) for c in cells) / n
    if cxx + cyy < 1e-4:
        return None
    angle = 0.5 * math.atan2(2 * cxy, cxx - cyy)
    axis = (math.cos(angle), math.sin(angle))
    scalars = [(c[0] - mx) * axis[0] + (c[1] - my) * axis[1] for c in cells]
    order = sorted(scalars)
    ranks = [(bisect.bisect_left(order, v) + bisect.bisect_right(order, v)) / (2 * n) for v in scalars]
    width = len(field[0])
    return [ranks[i:i + width] for i in range(0, n, width)], axis, (mx, my)


def shift_of(spatial: dict | None, now: float | None = None) -> tuple[float, float]:
    """How far the picture has moved (dynamic scenes); (0, 0) for a scene that stands still."""
    if not spatial or spatial.get("since") is None or not spatial.get("period"):
        return (0.0, 0.0)
    passed = ((now if now is not None else time.monotonic()) - spatial["since"]) / spatial["period"]
    angle = math.radians(spatial.get("direction", 0))
    return (math.cos(angle) * passed, math.sin(angle) * passed)


def assign(field, places: dict, colors: list, shift=(0.0, 0.0), pools: dict | None = None) -> dict:
    """Color per light by its place: {entity_id: {"color": xy, "strip": [xy, ...]}}.

    The preset colors are put in the order in which the picture changes its colors, each with the
    share it has in the preset (presets repeat colors that should dominate). A light gets the color
    that belongs to the picture at its place. All colors stay in use as far as there are lights, and
    none gets more lights than its share. Without picture, or with a picture in one color, the
    colors run from left to right in the order of the preset.

    ``places`` is {entity_id: place}; ``pools`` limits the colors of single lights ({entity_id:
    colors}, main and accent lights of music scenes). Lights with a strip (x2, y2) also get the
    colors along it.
    """
    if not places or not colors:
        return {}
    colors = [tuple(c) for c in colors]
    distinct = list(dict.fromkeys(colors))
    ranked = _ranks(field) if field else None

    if ranked is not None:
        ranks, axis, center = ranked

        def along(color):
            chroma = _chroma_xy(color)
            return (chroma[0] - center[0]) * axis[0] + (chroma[1] - center[1]) * axis[1]

        def rank_at(x, y):
            return _sample(ranks, x - shift[0], y - shift[1])

        distinct.sort(key=along)
    else:
        along = None

        def rank_at(x, y):
            return _mirror(x - shift[0])

    # every color has its part of 0..1, as wide as its share of the preset
    position, start = {}, 0.0
    for color in distinct:
        width = colors.count(color) / len(colors)
        position[color] = start + width / 2
        start += width

    def position_of(color):
        if color in position:
            return position[color]
        if along is None:
            return 0.5
        # a color that is not in the preset (own colors of a light): between its neighbours
        value = along(color)
        before = [c for c in distinct if along(c) <= value]
        after = [c for c in distinct if along(c) > value]
        if not before:
            return 0.0
        if not after:
            return 1.0
        low, high = before[-1], after[0]
        span = along(high) - along(low)
        part = (value - along(low)) / span if span else 0.5
        return position[low] + (position[high] - position[low]) * part

    def options(entity_id):
        return [tuple(c) for c in ((pools or {}).get(entity_id) or distinct)]

    pairs = []
    for entity_id, place in places.items():
        x, y = place["x"], place["y"]
        if place.get("x2") is not None:
            x, y = (x + place["x2"]) / 2, (y + place["y2"]) / 2
        here = rank_at(x, y)
        for color in options(entity_id):
            pairs.append((abs(here - position_of(color)), entity_id, color))
    pairs.sort(key=lambda p: p[0])

    result: dict = {}
    used: dict = {}
    share = {c: math.ceil(len(places) * colors.count(c) / len(colors)) for c in distinct}
    # first every color once, then up to its share, then whatever is left (own colors of a light)
    for limit in (lambda c: 1, lambda c: share.get(c, len(places)), lambda c: len(places)):
        for _cost, entity_id, color in pairs:
            if entity_id not in result and used.get(color, 0) < limit(color):
                result[entity_id] = {"color": color}
                used[color] = used.get(color, 0) + 1

    for entity_id, place in places.items():
        if place.get("x2") is None or entity_id not in result:
            continue
        strip = []
        for i in range(STRIP_POINTS):
            t = i / (STRIP_POINTS - 1)
            here = rank_at(place["x"] + (place["x2"] - place["x"]) * t, place["y"] + (place["y2"] - place["y"]) * t)
            strip.append(min(options(entity_id), key=lambda c: abs(here - position_of(c))))
        result[entity_id]["strip"] = strip
    return result
