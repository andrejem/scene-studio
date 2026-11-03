# Added by andrejem (2026): one scene entity per saved scene (attribute music for music scenes).
# Pictures of the user's own presets get a signed URL that is renewed regularly.

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN, SERVICE_ACTIVATE_SAVED_SCENE, ATTR_DYNAMIC_SCENE_ID
from .file_utils import PRESET_DATA
from .images import image_url, is_private
from .music_scenes import is_music_scene

_LOGGER = logging.getLogger(__name__)


# signed picture URLs are valid for 24 hours (images.SIGNED_URL_VALIDITY) and renewed twice as often
PICTURE_RENEWAL = timedelta(hours=12)


def _preset(preset_id):
    for preset in PRESET_DATA.get("presets", []):
        if preset.get("id") == preset_id and preset.get("img"):
            return preset
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
        preset = _preset(self._scene.get("preset_id"))
        return image_url(self.hass, preset, use_content_user=True) if preset else None

    @property
    def has_private_picture(self) -> bool:
        preset = _preset(self._scene.get("preset_id"))
        return preset is not None and is_private(preset)

    @property
    def extra_state_attributes(self):
        return {
            "saved_scene_id": self._scene["id"],
            "preset_id": self._scene.get("preset_id"),
            "dynamic": self._scene.get("dynamic", False),
            "music": is_music_scene(self._scene),
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
    store = entry.runtime_data.saved_scenes
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

    @callback
    def _renew_pictures(_now=None):
        for entity in entities.values():
            if entity.hass is not None and entity.has_private_picture:
                entity.async_write_ha_state()

    entry.async_on_unload(async_track_time_interval(hass, _renew_pictures, PICTURE_RENEWAL))
