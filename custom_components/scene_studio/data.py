# Added by andrejem (2026): runtime data of the config entry (entry.runtime_data). Everything that
# runs - saved scenes, dynamic scenes, optional lights, music scenes, gradient lamps - is created when
# the entry is set up and stopped when it is unloaded, so the integration can be reloaded.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN

if TYPE_CHECKING:
    from .dynamic_scenes import DynamicSceneManager
    from .gradient import GradientLights
    from .music_scenes import MusicScenes
    from .optional_lights import OptionalLights
    from .saved_scenes import SavedSceneStore


@dataclass
class SceneStudioData:
    saved_scenes: SavedSceneStore
    dynamic_scenes: DynamicSceneManager
    optional_lights: OptionalLights
    music_scenes: MusicScenes
    gradient: GradientLights
    # scene entities by saved scene id (scene.py), to mark a scene as activated
    scene_entities: dict = field(default_factory=dict)


type SceneStudioConfigEntry = ConfigEntry[SceneStudioData]


def find_data(hass: HomeAssistant) -> SceneStudioData | None:
    """Runtime data of the (single) config entry, None while it is not set up."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state not in (ConfigEntryState.LOADED, ConfigEntryState.SETUP_IN_PROGRESS):
            continue
        data = getattr(entry, "runtime_data", None)
        if isinstance(data, SceneStudioData):
            return data
    return None


def get_data(hass: HomeAssistant) -> SceneStudioData:
    """Runtime data for services; a clear error while Scene Studio is not set up."""
    data = find_data(hass)
    if data is None:
        raise ServiceValidationError("Scene Studio is not set up")
    return data
