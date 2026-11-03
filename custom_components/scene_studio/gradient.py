# Added by andrejem (2026): gradient lights. Lamps that can show several colors at once (Philips Hue
# gradient lamps like Signe, Play gradient or the gradient light strip in Zigbee2MQTT) get the colors
# of the preset as a gradient instead of one color. Home Assistant's light entity knows only one
# color, so the gradient is sent to Zigbee2MQTT directly over MQTT.

import json
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import color as color_util

_LOGGER = logging.getLogger(__name__)

MAX_GRADIENT_COLORS = 5
GRADIENT_STYLE = "linear"


def _hex(xy) -> str:
    r, g, b = color_util.color_xy_to_RGB(xy[0], xy[1])
    return f"#{r:02x}{g:02x}{b:02x}"


def gradient_colors(preset_colors, first_color) -> list:
    """Colors for one gradient lamp: the preset colors, starting with the color the lamp would get."""
    colors = list(preset_colors)
    if not colors:
        return []
    start = colors.index(first_color) if first_color in colors else 0
    count = min(len(colors), MAX_GRADIENT_COLORS)
    return [colors[(start + i) % len(colors)] for i in range(count)]


class GradientLights:
    """Finds gradient lamps in Zigbee2MQTT and sends gradients to them."""

    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._devices: dict[str, str] = {}  # ieee address -> MQTT topic of the device
        self._lights: dict[str, str] = {}  # light entity_id -> MQTT topic
        self._unsub = None

    async def async_start(self):
        """Listen to the device lists of Zigbee2MQTT (any base topic). Without MQTT nothing happens."""
        if "mqtt" not in self.hass.config.components:
            return
        try:
            from homeassistant.components import mqtt

            if not await mqtt.async_wait_for_mqtt_client(self.hass):
                return
            self._unsub = await mqtt.async_subscribe(self.hass, "+/bridge/devices", self._on_devices)
        except Exception as err:  # noqa: BLE001 - gradients are optional
            _LOGGER.debug("Gradient lights not available: %s", err)

    @callback
    def async_stop(self):
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _on_devices(self, msg):
        try:
            devices = json.loads(msg.payload)
        except (ValueError, TypeError):
            return
        base = msg.topic.split("/bridge/devices")[0]
        found = {}
        for device in devices or []:
            exposes = json.dumps((device.get("definition") or {}).get("exposes") or [])
            if '"gradient"' in exposes and device.get("ieee_address") and device.get("friendly_name"):
                found[device["ieee_address"].lower()] = f"{base}/{device['friendly_name']}"
        self._devices = found
        self._map_entities()

    @callback
    def _map_entities(self):
        lights = {}
        if self._devices:
            dev_reg = dr.async_get(self.hass)
            ent_reg = er.async_get(self.hass)
            for device in dev_reg.devices.values():
                topic = None
                for domain, ident in device.identifiers:
                    if domain != "mqtt":
                        continue
                    for ieee, device_topic in self._devices.items():
                        if ieee in str(ident).lower():
                            topic = device_topic
                if topic is None:
                    continue
                for entry in er.async_entries_for_device(ent_reg, device.id):
                    if entry.domain == "light":
                        lights[entry.entity_id] = topic
        self._lights = lights
        if lights:
            _LOGGER.debug("Gradient lights: %s", ", ".join(sorted(lights)))

    def is_gradient(self, entity_id: str) -> bool:
        return entity_id in self._lights

    def register(self, entity_id: str, topic: str):
        """Mainly for tests: treat a light as gradient lamp with this MQTT topic."""
        self._lights[entity_id] = topic

    async def async_apply(self, entity_id: str, colors, brightness, transition) -> bool:
        """Send a gradient to the lamp. False if the lamp is no gradient lamp or MQTT failed."""
        topic = self._lights.get(entity_id)
        if topic is None or not colors:
            return False
        payload = {
            "state": "ON",
            "gradient": [_hex(c) for c in colors],
            "gradient_style": GRADIENT_STYLE,
        }
        if brightness is not None:
            payload["brightness"] = int(brightness)
        if transition is not None:
            payload["transition"] = transition
        try:
            from homeassistant.components import mqtt

            await mqtt.async_publish(self.hass, f"{topic}/set", json.dumps(payload))
        except Exception as err:  # noqa: BLE001 - fall back to one color
            _LOGGER.warning("Gradient for %s could not be sent: %s", entity_id, err)
            return False
        return True
