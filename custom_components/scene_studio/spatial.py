# Added by andrejem (2026): room canvas (4.0). The user places the lights of a room on a plan once.
# A scene with "spatial" lays the picture of its preset over the plan: every light gets the preset
# color that is closest to the picture at its place, so the colors are spread through the room like
# in the picture instead of by chance. Dynamic scenes move the picture slowly through the room.
# Lights without a place and scenes without "spatial" behave as before.

from __future__ import annotations

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


def _distance(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def shift_of(spatial: dict | None, now: float | None = None) -> tuple[float, float]:
    """How far the picture has moved (dynamic scenes); (0, 0) for a scene that stands still."""
    if not spatial or spatial.get("since") is None or not spatial.get("period"):
        return (0.0, 0.0)
    passed = ((now if now is not None else time.monotonic()) - spatial["since"]) / spatial["period"]
    angle = math.radians(spatial.get("direction", 0))
    return (math.cos(angle) * passed, math.sin(angle) * passed)


def assign(field, places: dict, colors: list, shift=(0.0, 0.0), pools: dict | None = None) -> dict:
    """Color per light: the preset color closest to the picture at its place.

    ``places`` is {entity_id: place}; ``pools`` optionally limits the colors of single lights
    ({entity_id: colors}, main and accent lights of music scenes). All colors of the preset stay in
    use: none is given to more lights than its share, so a picture with one dominant color does not
    turn the whole room into it. Lights with a strip (x2, y2) also get "strip": colors along it.
    """
    if not field or not places or not colors:
        return {}
    chroma = {tuple(c): _chroma_xy(c) for c in colors}
    for pool in (pools or {}).values():
        for c in pool:
            chroma.setdefault(tuple(c), _chroma_xy(c))

    def options(entity_id):
        return [tuple(c) for c in ((pools or {}).get(entity_id) or colors)]

    pairs = []
    for entity_id, place in places.items():
        x, y = place["x"], place["y"]
        if place.get("x2") is not None:
            x, y = (x + place["x2"]) / 2, (y + place["y2"]) / 2
        here = _chroma_rgb(_sample(field, x - shift[0], y - shift[1]))
        for color in options(entity_id):
            pairs.append((_distance(here, chroma[color]), entity_id, color))
    pairs.sort(key=lambda p: p[0])

    # share of a color: as often as it is in the preset (presets repeat colors that should dominate)
    counts: dict = {}
    for c in colors:
        counts[tuple(c)] = counts.get(tuple(c), 0) + 1
    share = {c: math.ceil(len(places) * n / len(colors)) for c, n in counts.items()}
    used: dict = {}
    result: dict = {}
    for _dist, entity_id, color in pairs:
        if entity_id in result or used.get(color, 0) >= share.get(color, len(places)):
            continue
        result[entity_id] = {"color": color}
        used[color] = used.get(color, 0) + 1
    for _dist, entity_id, color in pairs:  # lights left over (own pools can use up their share)
        result.setdefault(entity_id, {"color": color})

    for entity_id, place in places.items():
        if place.get("x2") is None or entity_id not in result:
            continue
        strip = []
        for i in range(STRIP_POINTS):
            t = i / (STRIP_POINTS - 1)
            here = _chroma_rgb(_sample(
                field,
                place["x"] + (place["x2"] - place["x"]) * t - shift[0],
                place["y"] + (place["y2"] - place["y"]) * t - shift[1],
            ))
            strip.append(min(options(entity_id), key=lambda c: _distance(here, chroma[c])))
        result[entity_id]["strip"] = strip
    return result
