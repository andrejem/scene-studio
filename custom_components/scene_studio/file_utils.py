# Modified by andrejem (2026): presets are built by load_preset_data(), so presets created in the
# panel and replaced preset images (overrides) can be reloaded without a restart
# (async_reload_preset_data reads the files in the executor).
# Runtime presets for music scenes (RUNTIME_PRESETS). No file access at import: the presets are loaded
# and the userdata folder is created when the config entry is set up.
import json
import os
import logging

_LOGGER = logging.getLogger(__name__)

BASE_PATH = os.path.dirname(os.path.realpath(__file__))
CUSTOM_DIR = os.path.join(BASE_PATH, 'userdata/custom')
custom_presets_path = os.path.join(CUSTOM_DIR, 'presets.json')


def read_custom_presets():
    """Content of userdata/custom/presets.json, None if there is none or it cannot be read."""
    if not os.path.exists(custom_presets_path):
        _LOGGER.info(f"No custom presets file found at {custom_presets_path}")
        return None
    try:
        with open(custom_presets_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        _LOGGER.info("Custom presets loaded successfully.")
        return data
    except (json.JSONDecodeError, OSError) as e:
        _LOGGER.error(f"Error loading custom presets: {e}")
        return None


def load_preset_data():
    """Built-in presets plus custom presets and categories (flagged custom) and image/color overrides."""
    with open(os.path.join(BASE_PATH, 'presets.json'), 'r', encoding='utf-8') as file:
        data = json.load(file)

    custom = read_custom_presets()
    if custom is not None:
        overrides = custom.get("overrides") or {}
        if overrides:
            for preset in data.get("presets", []):
                override = overrides.get(preset.get("id"))
                if not override:
                    continue
                if override.get("img"):
                    preset["original_img"] = preset.get("img")
                    preset["img"] = override["img"]
                if override.get("lights"):
                    preset["lights"] = override["lights"]
                if override.get("bri"):
                    preset["original_bri"] = preset.get("bri")
                    preset["bri"] = override["bri"]
                preset["overridden"] = True
        data.get("presets", []).extend([{**d, 'custom': True} for d in custom.get("presets", [])])
        data.get("categories", []).extend([{**d, 'custom': True} for d in custom.get("categories", [])])
    return data


# filled by async_reload_preset_data() when the config entry is set up, changed in place afterwards
PRESET_DATA: dict = {"categories": [], "presets": []}

# Added by andrejem (2026): presets that only exist at runtime (colors of a music scene's cover).
# Not shown in the panel, looked up by apply_preset before the regular presets.
RUNTIME_PRESETS: dict[str, dict] = {}


def reload_preset_data():
    """Reload in place: every module keeps its reference to PRESET_DATA."""
    data = load_preset_data()
    PRESET_DATA.clear()
    PRESET_DATA.update(data)


async def async_ensure_directories(hass):
    """Folder for the user's own presets and pictures (kept by HACS updates)."""
    await hass.async_add_executor_job(
        lambda: os.makedirs(os.path.join(CUSTOM_DIR, 'assets'), exist_ok=True)
    )


async def async_reload_preset_data(hass):
    """Read the files in the executor, swap the data on the event loop (no change from a thread)."""
    data = await hass.async_add_executor_job(load_preset_data)
    PRESET_DATA.clear()
    PRESET_DATA.update(data)
