# Added by andrejem (2026): soft fade (3.8). Some lights fade on and off but jump to a new color at
# once, whatever transition they get. For lights the user marks, Scene Studio does the fade itself: it
# sends the color in small steps over the transition time. The steps go around the color wheel (hue,
# saturation, brightness), not through RGB, so the middle of a fade keeps its brightness and color.
# A light is marked once for all scenes, with its steps per second (3.10: 1-20, before three levels).
# How fine a single step may be is one setting for all lights (smoothness). The steps start and end
# gently (ease in and out), so the eye notices the steps less. Any other command to the light (another
# scene, a switch, an automation) ends a running fade at once.

from __future__ import annotations

import asyncio
import logging
import math

from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import color as color_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.soft_fade"

# steps per second of a light; up to 3.9 a level, kept as its number of steps
MIN_RATE, MAX_RATE, DEFAULT_RATE = 1, 20, 2
LEVELS = {"fine": 4, "normal": 2, "coarse": 1}
# smoothness: how large one step may be, as a factor of the normal step (STEP_HUE ...)
SMOOTHNESS = {"fine": 0.5, "normal": 1.0, "coarse": 2.5}  # largest step 1°, 2°, 5° of hue
DEFAULT_SMOOTHNESS = "normal"
# below this a fade is not worth it: the light gets the color at once, as before
MIN_DURATION = 0.8
# changes smaller than this need no step of their own (degrees of hue, % saturation, brightness 0..255)
STEP_HUE, STEP_SATURATION, STEP_BRIGHTNESS = 2.0, 2.0, 3.0


def hs_of_params(params: dict, state_attrs: dict | None = None):
    """Target color of a turn_on call as (hue, saturation), None if it sets no color."""
    if params.get("hs_color") is not None:
        hue, sat = params["hs_color"]
        return float(hue), float(sat)
    if params.get("xy_color") is not None:
        return color_util.color_xy_to_hs(*params["xy_color"])
    if params.get("rgb_color") is not None:
        return color_util.color_RGB_to_hs(*params["rgb_color"])
    if params.get("color_temp_kelvin") is not None:
        return color_util.color_temperature_to_hs(params["color_temp_kelvin"])
    return None


def rate_of(value) -> int | None:
    """Steps per second from a stored or sent value (a number, or a level of 3.8/3.9)."""
    if value in LEVELS:
        return LEVELS[value]
    try:
        rate = int(value)
    except (TypeError, ValueError):
        return None
    return max(MIN_RATE, min(MAX_RATE, rate))


def _ease(f: float) -> float:
    """Gentle start and end: small steps at both ends, larger ones in the middle."""
    return (1 - math.cos(math.pi * f)) / 2


def steps_between(start, end, duration: float, rate: int, smoothness: float = 1.0):
    """The steps of a fade: [(hue, saturation, brightness), ...], the last one is the target.

    ``start`` and ``end`` are (hue 0..360, saturation 0..100, brightness 0..255); brightness may be
    None (unchanged). Hue takes the shorter way around the wheel. The number of steps follows the
    duration and the rate (steps per second), but a small change gets fewer steps: no step is larger
    than the normal step times ``smoothness`` (the largest steps are in the middle of the fade).
    """
    (h0, s0, b0), (h1, s1, b1) = start, end
    dh = ((h1 - h0 + 180) % 360) - 180
    # without saturation the hue does not matter (white): no detour around the wheel
    if s0 < 1:
        h0, dh = h1, 0  # from white: start in the hue of the target
    elif s1 < 1:
        dh = 0  # to white: keep the hue while the color fades out
    db = (b1 - b0) if b0 is not None and b1 is not None else 0
    needed = max(abs(dh) / STEP_HUE, abs(s1 - s0) / STEP_SATURATION, abs(db) / STEP_BRIGHTNESS) / smoothness
    # with easing the middle steps are pi/2 times the average step
    count = max(1, min(int(duration * rate), math.ceil(needed * math.pi / 2)))
    steps = []
    for k in range(1, count + 1):
        f = _ease(k / count)
        brightness = None if b1 is None else (b1 if b0 is None else round(b0 + db * f))
        steps.append((round((h0 + dh * f) % 360, 2), round(s0 + (s1 - s0) * f, 2), brightness))
    return steps


class SoftFade:
    """Lights faded by Scene Studio, and the fades that are running."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._lights: dict[str, int] = {}  # entity_id -> steps per second
        self._smoothness = DEFAULT_SMOOTHNESS
        self._running: dict[str, asyncio.Task] = {}
        self._own: set[str] = set()  # context ids of the steps, so they do not end their own fade
        self._unsub = None

    async def async_load(self):
        data = await self._store.async_load() or {}
        lights = {e: rate_of(v) for e, v in (data.get("lights") or {}).items()}
        self._lights = {e: r for e, r in lights.items() if r is not None}
        if data.get("smoothness") in SMOOTHNESS:
            self._smoothness = data["smoothness"]
        self._unsub = self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._on_call)

    def lights(self) -> dict:
        return dict(self._lights)

    def smoothness(self) -> str:
        return self._smoothness

    def level_of(self, entity_id: str) -> int | None:
        """Steps per second of a light, None if Scene Studio does not fade it."""
        return self._lights.get(entity_id)

    async def async_set(self, entity_id: str, rate):
        """Steps per second of a light (1-20, or a level of 3.8/3.9); None: not faded any more."""
        if rate is None:
            self._lights.pop(entity_id, None)
            self.cancel(entity_id)
        else:
            value = rate_of(rate)
            if value is None:
                raise ValueError(f"Unknown rate {rate}")
            self._lights[entity_id] = value
        await self._async_save()

    async def async_set_smoothness(self, smoothness: str):
        if smoothness not in SMOOTHNESS:
            raise ValueError(f"Unknown smoothness {smoothness}")
        self._smoothness = smoothness
        await self._async_save()

    async def _async_save(self):
        await self._store.async_save({"lights": self._lights, "smoothness": self._smoothness})

    @callback
    def cancel(self, entity_id: str):
        task = self._running.pop(entity_id, None)
        if task is not None and not task.done():
            task.cancel()

    @callback
    def async_shutdown(self):
        if self._unsub:
            self._unsub()
            self._unsub = None
        for entity_id in list(self._running):
            self.cancel(entity_id)

    @callback
    def _on_call(self, event: Event):
        """Another command to a fading light ends its fade."""
        if event.data.get("domain") != "light" or not self._running:
            return
        if event.context.id in self._own or (event.context.parent_id and event.context.parent_id in self._own):
            return
        data = event.data.get("service_data") or {}
        targets = data.get("entity_id")
        if targets is None:
            targets = (event.data.get("target") or {}).get("entity_id")
        if targets is None:
            return
        for entity_id in [targets] if isinstance(targets, str) else list(targets):
            self.cancel(entity_id)

    def fade(self, params: dict) -> bool:
        """Turn a marked light on with ``params`` (one light, as apply_preset sends it) and fade there.

        Returns False when the light is not faded by Scene Studio (not marked, off, too short, no color
        change); the caller then sends the command as before. A fade already running on the light ends.
        """
        entity_id = params.get("entity_id")
        rate = self._lights.get(entity_id) if isinstance(entity_id, str) else None
        if rate is None:
            return False
        self.cancel(entity_id)
        duration = float(params.get("transition") or 0)
        state = self.hass.states.get(entity_id)
        target = hs_of_params(params)
        if duration < MIN_DURATION or state is None or state.state != "on" or target is None:
            return False  # off: the light fades on by itself; no color: nothing to fade
        current = state.attributes.get("hs_color")
        if current is None:
            return False
        start = (float(current[0]), float(current[1]), state.attributes.get("brightness"))
        end = (target[0], target[1], params.get("brightness"))
        steps = steps_between(start, end, duration, rate, SMOOTHNESS[self._smoothness])
        if len(steps) <= 1:
            return False
        self._running[entity_id] = self.hass.async_create_background_task(
            self._run(entity_id, params, steps, duration / len(steps)), f"scene_studio_soft_fade_{entity_id}"
        )
        return True

    async def _run(self, entity_id: str, params: dict, steps: list, interval: float):
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            for k, (hue, sat, brightness) in enumerate(steps[:-1], start=1):
                data = {"entity_id": entity_id, "hs_color": [hue, sat]}
                if brightness is not None:
                    data["brightness"] = brightness
                await self._send(data)
                await asyncio.sleep(max(0.0, started + k * interval - loop.time()))
                state = self.hass.states.get(entity_id)
                if state is None or state.state != "on":
                    return  # turned off in between (e.g. at the switch): do not turn it on again
            # the last step is the command itself, with the exact color of the preset
            final = {key: value for key, value in params.items() if key != "transition"}
            await self._send(final)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - a failed step must not leave a task behind
            _LOGGER.warning("Soft fade of %s stopped: %s", entity_id, err)
        finally:
            if self._running.get(entity_id) is asyncio.current_task():
                self._running.pop(entity_id, None)

    async def _send(self, data: dict):
        context = Context()
        self._own.add(context.id)
        try:
            await self.hass.services.async_call("light", "turn_on", data, blocking=False, context=context)
            await asyncio.sleep(0)  # the call_service event is fired before the id is forgotten
        finally:
            self._own.discard(context.id)
