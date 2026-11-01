# Added by andrejem (2026): one scene entity per saved scene.

import logging
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SERVICE_ACTIVATE_SAVED_SCENE, ATTR_DYNAMIC_SCENE_ID
from .file_utils import PRESET_DATA

_LOGGER = logging.getLogger(__name__)


def _preset_image(preset_id):
    for preset in PRESET_DATA.get("presets", []):
        if preset.get("id") == preset_id and preset.get("img"):
            return f"/assets/{DOMAIN}/{preset['img']}"
    return None


class SavedSceneEntity(Scene):
    _attr_has_entity_name = False
    _attr_icon = "mdi:palette"

    def __init__(self, scene: dict):
        self._scene = scene
        self._attr_unique_id = f"saved_scene_{scene['id']}"

    @property
    def name(self):
        return self._scene["name"]

    @property
    def entity_picture(self):
        return _preset_image(self._scene.get("preset_id"))

    @property
    def extra_state_attributes(self):
        return {
            "saved_scene_id": self._scene["id"],
            "preset_id": self._scene.get("preset_id"),
            "dynamic": self._scene.get("dynamic", False),
        }

    @callback
    def update_scene(self, scene: dict):
        self._scene = scene
        self.async_write_ha_state()

    async def async_activate(self, **kwargs: Any) -> None:
        await self.hass.services.async_call(
            DOMAIN,
            SERVICE_ACTIVATE_SAVED_SCENE,
            {ATTR_DYNAMIC_SCENE_ID: self._scene["id"]},
            blocking=True,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    store = hass.data[DOMAIN]["saved_scenes"]
    entities: dict[str, SavedSceneEntity] = {}

    def _add(scene):
        entity = SavedSceneEntity(scene)
        entities[scene["id"]] = entity
        async_add_entities([entity])

    for scene in store.get_all():
        _add(scene)

    @callback
    def _on_change(scene_id, scene):
        if scene is None:
            entity = entities.pop(scene_id, None)
            if entity is not None:
                registry = er.async_get(hass)
                if entity.entity_id and registry.async_get(entity.entity_id):
                    registry.async_remove(entity.entity_id)
                else:
                    hass.async_create_task(entity.async_remove())
        elif scene_id in entities:
            entities[scene_id].update_scene(scene)
        else:
            _add(scene)

    entry.async_on_unload(store.add_listener(_on_change))
