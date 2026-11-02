# Added by andrejem (2026): persistent saved scenes (preset + targets + settings, music).

import logging
import uuid
from typing import Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.saved_scenes"

# Keys of a saved scene that are passed on to apply_preset / start_dynamic_scene
SCENE_SETTING_KEYS = (
    "preset_id",
    "targets",
    "brightness",
    "transition",
    "shuffle",
    "smart_shuffle",
    "interval",
    "interval_min",
    "interval_max",
    "transition_min",
    "transition_max",
    "exclude",
    "keep_groups",
    "optional",
    "light_brightness",
)


class SavedSceneStore:
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._scenes: dict[str, dict] = {}
        self._listeners: list[Callable[[str, dict | None], None]] = []

    async def async_load(self):
        data = await self._store.async_load()
        self._scenes = {s["id"]: s for s in (data or {}).get("scenes", [])}

    async def _async_save(self):
        await self._store.async_save({"scenes": list(self._scenes.values())})

    @callback
    def add_listener(self, listener: Callable[[str, dict | None], None]) -> Callable[[], None]:
        """Listener is called with (scene_id, scene) on create/update and (scene_id, None) on delete."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _notify(self, scene_id, scene):
        for listener in list(self._listeners):
            listener(scene_id, scene)

    @callback
    def notify_preset_changed(self, preset_id: str) -> None:
        """Scenes using this preset (e.g. its image changed) are announced as updated."""
        for scene in list(self._scenes.values()):
            if scene.get("preset_id") == preset_id:
                self._notify(scene["id"], scene)

    def get_all(self) -> list[dict]:
        return sorted(self._scenes.values(), key=lambda s: s["name"].lower())

    def get(self, scene_id: str) -> dict | None:
        return self._scenes.get(scene_id)

    async def async_save_scene(self, data: dict) -> dict:
        scene_id = data.get("id") or str(uuid.uuid4())
        scene = {
            "id": scene_id,
            "name": data["name"],
            "dynamic": bool(data.get("dynamic", False)),
        }
        for key in SCENE_SETTING_KEYS:
            if data.get(key) is not None:
                scene[key] = data[key]
        if data.get("music"):
            # Music scene: colors from the album cover of a media player (music_scenes.py)
            scene["music"] = dict(data["music"])

        self._scenes[scene_id] = scene
        await self._async_save()
        self._notify(scene_id, scene)
        return scene

    async def async_delete_scene(self, scene_id: str) -> bool:
        if scene_id not in self._scenes:
            return False
        del self._scenes[scene_id]
        await self._async_save()
        self._notify(scene_id, None)
        return True


def build_service_call(scene: dict, dynamic: bool | None = None) -> tuple[str, dict]:
    """Return (service, service_data) that activates the given saved scene.

    ``dynamic`` overrides the saved mode: False applies a dynamic scene once (static),
    True starts a static scene as dynamic scene.
    """
    data = {key: scene[key] for key in SCENE_SETTING_KEYS if key in scene}
    run_dynamic = scene.get("dynamic", False) if dynamic is None else dynamic

    if run_dynamic:
        for key in ("shuffle", "smart_shuffle"):
            data.pop(key, None)
        return "start_dynamic_scene", data

    if scene.get("dynamic"):
        # A dynamic scene applied once: spread the preset colors like the dynamic scene would
        data.setdefault("shuffle", True)
        data.setdefault("smart_shuffle", False)
    for key in ("interval", "interval_min", "interval_max", "transition_min", "transition_max"):
        data.pop(key, None)
    return "apply_preset", data
