# Added by andrejem (2026): import from the Scene Presets integration (scene_presets, the original
# or a fork of it): saved scenes, own presets and replaced pictures (userdata/custom). Optionally the
# scene entities of the saved scenes are taken over with their entity ID, name, icon, area and labels,
# so dashboards and automations keep working. Scene Presets is then disabled (not removed).

import logging
import os
import shutil

from homeassistant.config_entries import ConfigEntryDisabler
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .file_utils import CUSTOM_DIR, reload_preset_data

_LOGGER = logging.getLogger(__name__)

OLD_DOMAIN = "scene_presets"
OLD_STORAGE_KEY = "scene_presets.saved_scenes"


def _old_custom_dir(hass: HomeAssistant) -> str:
    return hass.config.path("custom_components", OLD_DOMAIN, "userdata", "custom")


async def _old_scenes(hass: HomeAssistant) -> list[dict]:
    data = await Store(hass, 1, OLD_STORAGE_KEY).async_load()
    return [s for s in (data or {}).get("scenes", []) if s.get("id") and s.get("name")]


def _custom_files(src: str) -> list[str]:
    """Files below userdata/custom of Scene Presets (presets.json, pictures), relative paths."""
    if not os.path.isdir(src):
        return []
    files = []
    for root, _dirs, names in os.walk(src):
        for name in names:
            files.append(os.path.relpath(os.path.join(root, name), src))
    return files


def _copy_custom(src: str, dst: str, overwrite: bool) -> int:
    copied = 0
    for rel in _custom_files(src):
        target = os.path.join(dst, rel)
        if os.path.exists(target) and not overwrite:
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(src, rel), target)
        copied += 1
    return copied


async def async_import_status(hass: HomeAssistant, store) -> dict:
    """What an import would bring over (for the panel)."""
    scenes = await _old_scenes(hass)
    new = [s for s in scenes if store.get(s["id"]) is None]
    files = await hass.async_add_executor_job(_custom_files, _old_custom_dir(hass))
    has_custom = await hass.async_add_executor_job(os.path.exists, os.path.join(CUSTOM_DIR, "presets.json"))
    return {
        "available": bool(new) or bool(files) and not has_custom,
        "scenes": len(scenes),
        "new_scenes": len(new),
        "custom_files": len(files),
        "scene_presets_loaded": any(e.disabled_by is None for e in hass.config_entries.async_entries(OLD_DOMAIN)),
    }


async def async_import_scene_presets(
    hass: HomeAssistant, store, take_over_entities: bool = True, overwrite: bool = False
) -> dict:
    """Bring saved scenes and own presets of Scene Presets over. Scenes keep their IDs."""
    result = {"scenes": 0, "skipped": 0, "custom_files": 0, "entities": 0, "disabled_scene_presets": False}

    copied = await hass.async_add_executor_job(_copy_custom, _old_custom_dir(hass), CUSTOM_DIR, overwrite)
    result["custom_files"] = copied
    if copied:
        await hass.async_add_executor_job(reload_preset_data)

    scenes = await _old_scenes(hass)
    to_import = [s for s in scenes if overwrite or store.get(s["id"]) is None]
    result["skipped"] = len(scenes) - len(to_import)

    if take_over_entities and to_import:
        # Unload Scene Presets first, otherwise it would create its scene entities again
        for entry in hass.config_entries.async_entries(OLD_DOMAIN):
            if entry.disabled_by is None:
                await hass.config_entries.async_set_disabled_by(entry.entry_id, ConfigEntryDisabler.USER)
                result["disabled_scene_presets"] = True

        registry = er.async_get(hass)
        own_entry = next(iter(hass.config_entries.async_entries(DOMAIN)), None)
        old_entries = {
            e.unique_id: e for e in list(registry.entities.values())
            if e.platform == OLD_DOMAIN and e.domain == "scene"
        }
        for scene in to_import:
            unique_id = f"saved_scene_{scene['id']}"
            old = old_entries.get(unique_id)
            if old is None or registry.async_get_entity_id("scene", DOMAIN, unique_id):
                continue
            entity_id = old.entity_id
            registry.async_remove(entity_id)
            new = registry.async_get_or_create(
                "scene", DOMAIN, unique_id,
                suggested_object_id=entity_id.split(".", 1)[1],
                config_entry=own_entry,
            )
            changes = {
                "area_id": old.area_id,
                "name": old.name,
                "icon": old.icon,
                "labels": old.labels,
            }
            if new.entity_id != entity_id:
                changes["new_entity_id"] = entity_id
            registry.async_update_entity(new.entity_id, **changes)
            result["entities"] += 1

    for scene in to_import:
        await store.async_save_scene(dict(scene))
        result["scenes"] += 1

    _LOGGER.info("Imported from Scene Presets: %s", result)
    return result
