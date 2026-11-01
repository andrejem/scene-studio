# Added by andrejem (2026): optional lights. An optional light is part of a scene only while it
# is on. If it is turned on later while the scene is still active, it joins the scene.

import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .presets import apply_preset
from .util import ensure_list, resolve_entity_ids

_LOGGER = logging.getLogger(__name__)

JOIN_TRANSITION = 1


def _is_on(hass: HomeAssistant, entity_id: str) -> bool:
    state = hass.states.get(entity_id)
    return state is not None and state.state == "on"


def split_optional(hass: HomeAssistant, light_entity_ids, optional, keep_groups=None):
    """Split the optional lights off the resolved lights of a scene.

    Returns ``(base, optional_on, optional_ids)``: the scene lights without the optional ones,
    the optional lights that are on right now (they take part) and all optional lights.
    An optional group that is also in ``keep_groups`` stays one light, others are resolved.
    """
    keep = set(ensure_list(keep_groups))
    optional_ids = []
    members = set()
    for entity_id in ensure_list(optional):
        members.add(entity_id)
        members.update(resolve_entity_ids(hass, entity_id))
        resolved = [entity_id] if entity_id in keep else resolve_entity_ids(hass, entity_id)
        for resolved_id in resolved:
            if resolved_id not in optional_ids:
                optional_ids.append(resolved_id)

    base = [entity_id for entity_id in light_entity_ids if entity_id not in members]
    optional_on = [entity_id for entity_id in optional_ids if _is_on(hass, entity_id)]
    return base, optional_on, optional_ids


class OptionalLights:
    """Remembers which scene an optional light belongs to and lets it join when turned on."""

    def __init__(self, hass: HomeAssistant, dynamic_scene_manager):
        self.hass = hass
        self.manager = dynamic_scene_manager
        self._registrations: dict[str, dict] = {}
        self._unsub = None

    def forget_overlapping(self, light_entity_ids, optional_ids):
        """A new scene on the lights of a registration replaces it.

        A scene for the optional light alone (e.g. a lamp mode) keeps the registration, so the
        light still joins the room scene after it was off.
        """
        lights = set(light_entity_ids)
        optional = set(optional_ids)
        for entity_id, registration in list(self._registrations.items()):
            if entity_id in optional:
                continue  # re-registered by the new scene
            if lights & set(registration["lights"]):
                del self._registrations[entity_id]
        self._resubscribe()

    def register(
        self, optional_ids, base_lights, preset_id, brightness, dynamic_scene_id=None,
        light_brightness=None,
    ):
        for entity_id in optional_ids:
            self._registrations[entity_id] = {
                "lights": list(base_lights),
                "preset_id": preset_id,
                "brightness": brightness,
                "dynamic_scene_id": dynamic_scene_id,
                "light_brightness": light_brightness,
            }
        self._resubscribe()

    def get_all(self):
        return {entity_id: dict(reg) for entity_id, reg in self._registrations.items()}

    def _resubscribe(self):
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        if self._registrations:
            self._unsub = async_track_state_change_event(
                self.hass, list(self._registrations), self._state_changed
            )

    @callback
    def _state_changed(self, event: Event):
        entity_id = event.data["entity_id"]
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if new_state is None or new_state.state != "on":
            return
        if old_state is not None and old_state.state == "on":
            return
        registration = self._registrations.get(entity_id)
        if registration is not None:
            self.hass.async_create_task(self._join(entity_id, registration))

    async def _join(self, entity_id, registration):
        # Only join while the scene is still visible in the room
        if not any(_is_on(self.hass, other) for other in registration["lights"] if other != entity_id):
            return

        dynamic_scene = None
        if registration["dynamic_scene_id"]:
            dynamic_scene = self.manager.get_by_id(registration["dynamic_scene_id"])
            if dynamic_scene is None:
                # The dynamic scene has ended, so there is nothing to join anymore
                self._registrations.pop(entity_id, None)
                self._resubscribe()
                return

        _LOGGER.debug("Optional light %s joins scene with preset %s", entity_id, registration["preset_id"])
        await apply_preset(
            self.hass,
            registration["preset_id"],
            [entity_id],
            JOIN_TRANSITION,
            True,
            True,
            registration["brightness"],
            light_brightness=registration.get("light_brightness"),
        )
        if dynamic_scene is not None:
            dynamic_scene.add_light(entity_id)
