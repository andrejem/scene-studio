# Modified by andrejem (2026): start_dynamic_scene accepts optional per-light
# interval/transition ranges (interval_min/max, transition_min/max).
# Saved scenes: save/delete/activate services and a scene platform.
# Optional exclude list, keep_groups and optional lights for apply_preset, start_dynamic_scene
# and saved scenes. activate_saved_scene can apply a saved scene to other lights (targets).
# Brightness per light (light_brightness), 0 % turns the light off when the scene starts.
# Import from Scene Presets (import_scene_presets).
# Music scenes: colors from the album cover of a media player (music_scenes.py).

import voluptuous as vol
import homeassistant.helpers.config_validation as cv
import logging
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.config_entries import ConfigEntry
from .const import *

from .dynamic_scenes import DynamicScene, DynamicSceneManager
from .presets import apply_preset
from .view import async_setup_view, async_remove_view
from .util import ensure_list, resolve_targets, filter_targets, resolve_entity_ids, split_off, turn_off_lights
from .websocket_api import async_setup_websocket_api
from .saved_scenes import SavedSceneStore, build_service_call
from .optional_lights import OptionalLights, split_optional
from .migrate import async_import_scene_presets
from .music_scenes import MusicScenes, AUTO_START_OPTIONS, AUTO_START_NEVER, runtime_preset_id, is_music_scene
from .file_utils import RUNTIME_PRESETS

PLATFORMS = ["scene"]

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# 0 = the light is turned off when the scene starts
LIGHT_BRIGHTNESS = vol.Schema({cv.entity_id: vol.All(vol.Coerce(float), vol.Range(min=0, max=100))})

APPLY_PRESET_SCHEMA = vol.Schema({
    vol.Required(ATTR_SCENE_PRESET_ID): cv.string,
    vol.Required(ATTR_TARGETS): vol.Any(dict),
    vol.Optional(ATTR_BRIGHTNESS): vol.Coerce(int),
    vol.Optional(ATTR_TRANSITION, default=1): vol.Coerce(int),
    vol.Optional(ATTR_SHUFFLE, default=False): cv.boolean,
    vol.Optional(ATTR_SMART_SHUFFLE, default=False): cv.boolean,
    vol.Optional(ATTR_EXCLUDE): cv.entity_ids,
    vol.Optional(ATTR_KEEP_GROUPS): cv.entity_ids,
    vol.Optional(ATTR_OPTIONAL): cv.entity_ids,
    vol.Optional(ATTR_LIGHT_BRIGHTNESS): LIGHT_BRIGHTNESS,
})

START_DYNAMIC_SCENE_SCHEMA = vol.Schema({
    vol.Required(ATTR_SCENE_PRESET_ID): cv.string,
    vol.Required(ATTR_TARGETS): vol.Any(dict),
    vol.Optional(ATTR_INTERVAL, default=60): vol.Coerce(int),
    vol.Optional(ATTR_BRIGHTNESS): vol.Coerce(int),
    vol.Optional(ATTR_TRANSITION, default=1): vol.Coerce(int),
    vol.Optional(ATTR_INTERVAL_MIN): vol.All(vol.Coerce(float), vol.Range(min=1)),
    vol.Optional(ATTR_INTERVAL_MAX): vol.All(vol.Coerce(float), vol.Range(min=1)),
    vol.Optional(ATTR_TRANSITION_MIN): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(ATTR_TRANSITION_MAX): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(ATTR_EXCLUDE): cv.entity_ids,
    vol.Optional(ATTR_KEEP_GROUPS): cv.entity_ids,
    vol.Optional(ATTR_OPTIONAL): cv.entity_ids,
    vol.Optional(ATTR_LIGHT_BRIGHTNESS): LIGHT_BRIGHTNESS,
})


def _build_range(data, attr_min, attr_max, fallback):
    low = data.get(attr_min, fallback)
    high = data.get(attr_max, fallback)
    if low > high:
        raise vol.Invalid(f"'{attr_min}' must not be greater than '{attr_max}'.")
    return [low, high]

STOP_DYNAMIC_SCENE_SCHEMA = vol.Schema({
    vol.Required(ATTR_DYNAMIC_SCENE_ID): cv.string,
})

MUSIC_SCHEMA = vol.Schema({
    vol.Optional("media_player"): cv.entity_domain("media_player"),  # default: speaker of the room
    vol.Optional("auto_start", default=AUTO_START_NEVER): vol.In(AUTO_START_OPTIONS),
    vol.Optional("when_on", default=False): cv.boolean,
})

SAVE_SCENE_SCHEMA = vol.Schema({
    vol.Optional(ATTR_DYNAMIC_SCENE_ID): cv.string,
    vol.Required(ATTR_NAME): vol.All(cv.string, vol.Length(min=1)),
    vol.Required(ATTR_SCENE_PRESET_ID): cv.string,
    vol.Required(ATTR_TARGETS): vol.Any(dict),
    vol.Optional(ATTR_DYNAMIC, default=False): cv.boolean,
    vol.Optional(ATTR_BRIGHTNESS): vol.Coerce(int),
    vol.Optional(ATTR_TRANSITION): vol.Coerce(int),
    vol.Optional(ATTR_SHUFFLE): cv.boolean,
    vol.Optional(ATTR_SMART_SHUFFLE): cv.boolean,
    vol.Optional(ATTR_INTERVAL): vol.Coerce(int),
    vol.Optional(ATTR_INTERVAL_MIN): vol.All(vol.Coerce(float), vol.Range(min=1)),
    vol.Optional(ATTR_INTERVAL_MAX): vol.All(vol.Coerce(float), vol.Range(min=1)),
    vol.Optional(ATTR_TRANSITION_MIN): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(ATTR_TRANSITION_MAX): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(ATTR_EXCLUDE): cv.entity_ids,
    vol.Optional(ATTR_KEEP_GROUPS): cv.entity_ids,
    vol.Optional(ATTR_OPTIONAL): cv.entity_ids,
    vol.Optional(ATTR_LIGHT_BRIGHTNESS): LIGHT_BRIGHTNESS,
    vol.Optional("music"): MUSIC_SCHEMA,
})

SAVED_SCENE_ID_SCHEMA = vol.Schema({
    vol.Required(ATTR_DYNAMIC_SCENE_ID): cv.string,
})

ACTIVATE_SAVED_SCENE_SCHEMA = vol.Schema({
    vol.Required(ATTR_DYNAMIC_SCENE_ID): cv.string,
    vol.Optional(ATTR_DYNAMIC): cv.boolean,
    vol.Optional(ATTR_TARGETS): vol.Any(dict),
})

STOP_DYNAMIC_SCENES_FOR_TARGETS_SCHEMA = vol.Schema({
    vol.Required(ATTR_TARGETS): vol.Any(dict),
})


_LOGGER = logging.getLogger(__name__)

dynamic_scene_manager = DynamicSceneManager()


def _detach_from_dynamic_scenes(hass, light_entity_ids):
    """Remove lights from running dynamic scenes; a scene without lights left is stopped."""
    targets = set(light_entity_ids)
    for light_entity_id in light_entity_ids:
        targets.update(resolve_entity_ids(hass, light_entity_id))
    for scene in list(dynamic_scene_manager.get_all()):
        scene_ids = list(scene.parameters.get("light_entity_ids", []))
        leaving = [
            entity_id for entity_id in scene_ids
            if entity_id in targets or targets & set(resolve_entity_ids(hass, entity_id))
        ]
        if not leaving:
            continue
        if len(leaving) == len(scene_ids):
            dynamic_scene_manager.delete_by_id(scene.id)
        else:
            for entity_id in leaving:
                scene.remove_light(entity_id)


async def async_setup(hass, config):
    saved_scene_store = SavedSceneStore(hass)
    await saved_scene_store.async_load()
    hass.data.setdefault(DOMAIN, {})["saved_scenes"] = saved_scene_store
    optional_lights = OptionalLights(hass, dynamic_scene_manager)
    hass.data[DOMAIN]["optional_lights"] = optional_lights
    music_scenes = MusicScenes(hass, saved_scene_store, dynamic_scene_manager)
    hass.data[DOMAIN]["music_scenes"] = music_scenes

    async def apply_preset_service(call):
        preset_id = call.data.get(ATTR_SCENE_PRESET_ID)
        targets = call.data.get(ATTR_TARGETS)
        if preset_id == MUSIC_PRESET_ID:
            # Colors of the cover playing in the room right now; no music, nothing happens
            preset_id = await music_scenes.async_adhoc_preset(targets)
            if preset_id is None:
                return
        brightness_override = call.data.get(ATTR_BRIGHTNESS)
        transition = call.data.get(ATTR_TRANSITION, 1)
        shuffle = call.data.get(ATTR_SHUFFLE, False)
        smart_shuffle = call.data.get(ATTR_SMART_SHUFFLE, False)

        entity_ids = ensure_list(targets.get("entity_id"))
        device_ids = ensure_list(targets.get("device_id"))
        area_ids = ensure_list(targets.get("area_id"))
        floor_ids = ensure_list(targets.get("floor_id"))
        label_ids = ensure_list(targets.get("label_id"))


        light_entity_ids = filter_targets(
            hass,
            resolve_targets(hass, entity_ids, device_ids, area_ids, floor_ids, label_ids),
            entity_ids,
            call.data.get(ATTR_EXCLUDE),
            call.data.get(ATTR_KEEP_GROUPS),
        )
        light_entity_ids, optional_on, optional_ids = split_optional(
            hass, light_entity_ids, call.data.get(ATTR_OPTIONAL), call.data.get(ATTR_KEEP_GROUPS)
        )
        optional_lights.forget_overlapping(light_entity_ids, optional_ids)
        music_scenes.release_lights(light_entity_ids + optional_ids)
        light_brightness = call.data.get(ATTR_LIGHT_BRIGHTNESS)
        light_entity_ids, off_ids = split_off(hass, light_entity_ids, light_brightness)
        optional_on, optional_off = split_off(hass, optional_on, light_brightness)
        await turn_off_lights(hass, off_ids + optional_off, transition)

        await apply_preset(
            hass,
            preset_id,
            light_entity_ids + optional_on,
            transition,
            shuffle,
            smart_shuffle,
            brightness_override,
            light_brightness=call.data.get(ATTR_LIGHT_BRIGHTNESS),
        )
        optional_lights.register(
            optional_ids, light_entity_ids, preset_id, brightness_override,
            light_brightness=call.data.get(ATTR_LIGHT_BRIGHTNESS),
        )


    async def start_dynamic_scene(call):
        preset_id = call.data.get(ATTR_SCENE_PRESET_ID)
        targets = call.data.get(ATTR_TARGETS)
        interval = call.data.get(ATTR_INTERVAL)
        if preset_id == MUSIC_PRESET_ID:
            # Colors of the cover playing in the room right now; no music, nothing happens
            preset_id = await music_scenes.async_adhoc_preset(targets)
            if preset_id is None:
                return None

        # always stop any existing actions first
        await stop_dynamic_scenes_for_targets(call)

        brightness_override = call.data.get(ATTR_BRIGHTNESS)
        transition = call.data.get(ATTR_TRANSITION, 1)
        shuffle = True

        entity_ids = ensure_list(targets.get("entity_id"))
        device_ids = ensure_list(targets.get("device_id"))
        area_ids = ensure_list(targets.get("area_id"))
        floor_ids = ensure_list(targets.get("floor_id"))
        label_ids = ensure_list(targets.get("label_id"))

        light_entity_ids = filter_targets(
            hass,
            resolve_targets(hass, entity_ids, device_ids, area_ids, floor_ids, label_ids),
            entity_ids,
            call.data.get(ATTR_EXCLUDE),
            call.data.get(ATTR_KEEP_GROUPS),
        )
        light_entity_ids, optional_on, optional_ids = split_optional(
            hass, light_entity_ids, call.data.get(ATTR_OPTIONAL), call.data.get(ATTR_KEEP_GROUPS)
        )
        optional_lights.forget_overlapping(light_entity_ids, optional_ids)
        music_scenes.release_lights(light_entity_ids + optional_ids)
        light_brightness = call.data.get(ATTR_LIGHT_BRIGHTNESS)
        light_entity_ids, off_ids = split_off(hass, light_entity_ids, light_brightness)
        optional_on, optional_off = split_off(hass, optional_on, light_brightness)
        await turn_off_lights(hass, off_ids + optional_off, transition)

        parameters = {
            "preset_id": preset_id,
            "light_entity_ids": light_entity_ids + optional_on,
            "brightness": brightness_override,
            "transition": transition,
            "shuffle": shuffle,
            ATTR_LIGHT_BRIGHTNESS: call.data.get(ATTR_LIGHT_BRIGHTNESS),
        }

        range_attrs = (ATTR_INTERVAL_MIN, ATTR_INTERVAL_MAX, ATTR_TRANSITION_MIN, ATTR_TRANSITION_MAX)
        if any(attr in call.data for attr in range_attrs):
            # Every light gets its own schedule with randomized interval and transition
            parameters[ATTR_PER_LIGHT] = True
            parameters[ATTR_INTERVAL_RANGE] = _build_range(call.data, ATTR_INTERVAL_MIN, ATTR_INTERVAL_MAX, interval)
            parameters[ATTR_TRANSITION_RANGE] = _build_range(call.data, ATTR_TRANSITION_MIN, ATTR_TRANSITION_MAX, transition)

        result = dynamic_scene_manager.create_new(hass, parameters, interval)
        optional_lights.register(
            optional_ids, light_entity_ids, preset_id, brightness_override, result["id"],
            light_brightness=call.data.get(ATTR_LIGHT_BRIGHTNESS),
        )
        return result

    async def stop_dynamic_scene(call):
        scene_id = call.data.get(ATTR_DYNAMIC_SCENE_ID)

        dynamic_scene_manager.delete_by_id(scene_id)

    async def stop_dynamic_scenes_for_targets(call):
        targets = call.data.get(ATTR_TARGETS)

        entity_ids = ensure_list(targets.get("entity_id"))
        device_ids = ensure_list(targets.get("device_id"))
        area_ids = ensure_list(targets.get("area_id"))
        floor_ids = ensure_list(targets.get("floor_id"))
        label_ids = ensure_list(targets.get("label_id"))

        light_entity_ids = filter_targets(
            hass,
            resolve_targets(hass, entity_ids, device_ids, area_ids, floor_ids, label_ids),
            entity_ids,
            call.data.get(ATTR_EXCLUDE),
            call.data.get(ATTR_KEEP_GROUPS),
        )

        # A dynamic scene may control a group as one light, so compare on member level too
        target_ids = set(light_entity_ids)
        for target_id in light_entity_ids:
            target_ids.update(resolve_entity_ids(hass, target_id))
        for scene in list(dynamic_scene_manager.get_all()):
            scene_ids = set(scene.parameters.get("light_entity_ids", []))
            for scene_light_id in list(scene_ids):
                scene_ids.update(resolve_entity_ids(hass, scene_light_id))
            if scene_ids & target_ids:
                dynamic_scene_manager.delete_by_id(scene.id)

        return True

    async def stop_all_dynamic_scenes(call):
        dynamic_scene_manager.stop_all()

    async def get_dynamic_scenes(call):
        return dynamic_scene_manager.get_all_as_dict()

    async def save_scene(call):
        scene = await saved_scene_store.async_save_scene(dict(call.data))
        return {"scene": scene}

    async def delete_saved_scene(call):
        scene_id = call.data.get(ATTR_DYNAMIC_SCENE_ID)
        if not await saved_scene_store.async_delete_scene(scene_id):
            raise vol.Invalid(f"Saved scene '{scene_id}' not found.")

    async def activate_saved_scene(call):
        scene_id = call.data.get(ATTR_DYNAMIC_SCENE_ID)
        scene = saved_scene_store.get(scene_id)
        if scene is None:
            raise vol.Invalid(f"Saved scene '{scene_id}' not found.")

        override = call.data.get(ATTR_TARGETS)
        if is_music_scene(scene) and not override:
            await music_scenes.async_activate(scene)
            return

        service, service_data = build_service_call(scene, call.data.get(ATTR_DYNAMIC))
        if is_music_scene(scene) and runtime_preset_id(scene_id) in RUNTIME_PRESETS:
            # A lamp mode of a music scene shows the current cover colors
            service_data[ATTR_SCENE_PRESET_ID] = runtime_preset_id(scene_id)
        if override:
            # Apply the saved scene to other lights, e.g. one lamp of the room (lamp modes)
            for key in (ATTR_EXCLUDE, ATTR_KEEP_GROUPS, ATTR_OPTIONAL):
                service_data.pop(key, None)
            service_data[ATTR_TARGETS] = override
            # A lamp mode turns these lamps on: 0 % (off) does not apply, they get the scene brightness
            if service_data.get(ATTR_LIGHT_BRIGHTNESS):
                service_data[ATTR_LIGHT_BRIGHTNESS] = {
                    key: value for key, value in service_data[ATTR_LIGHT_BRIGHTNESS].items() if value > 0
                }
            override_entity_ids = ensure_list(override.get("entity_id"))
            lights = filter_targets(
                hass,
                resolve_targets(
                    hass,
                    override_entity_ids,
                    ensure_list(override.get("device_id")),
                    ensure_list(override.get("area_id")),
                    ensure_list(override.get("floor_id")),
                    ensure_list(override.get("label_id")),
                ),
                override_entity_ids,
                None,
            )
            # These lights leave running dynamic scenes, the other lights of those scenes keep going
            _detach_from_dynamic_scenes(hass, lights)
        elif service == SERVICE_APPLY_PRESET:
            # A running dynamic scene on these lights would immediately override the static one
            await hass.services.async_call(
                DOMAIN, SERVICE_STOP_DYNAMIC_SCENES_FOR_TARGETS,
                {ATTR_TARGETS: service_data[ATTR_TARGETS]}, blocking=True,
            )
        await hass.services.async_call(DOMAIN, service, service_data, blocking=True)


    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_PRESET,
        apply_preset_service,
        schema=APPLY_PRESET_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_DYNAMIC_SCENES,
        get_dynamic_scenes,
        supports_response=SupportsResponse.ONLY
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_DYNAMIC_SCENE,
        start_dynamic_scene,
        schema=START_DYNAMIC_SCENE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_DYNAMIC_SCENE,
        stop_dynamic_scene,
        schema=STOP_DYNAMIC_SCENE_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_DYNAMIC_SCENES_FOR_TARGETS,
        stop_dynamic_scenes_for_targets,
        schema=STOP_DYNAMIC_SCENES_FOR_TARGETS_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_ALL_DYNAMIC_SCENES,
        stop_all_dynamic_scenes,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_SCENE,
        save_scene,
        schema=SAVE_SCENE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_SAVED_SCENE,
        delete_saved_scene,
        schema=SAVED_SCENE_ID_SCHEMA
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ACTIVATE_SAVED_SCENE,
        activate_saved_scene,
        schema=ACTIVATE_SAVED_SCENE_SCHEMA
    )

    async def import_scene_presets(call):
        return await async_import_scene_presets(
            hass, saved_scene_store,
            take_over_entities=call.data["take_over_entities"],
            overwrite=call.data["overwrite"],
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_IMPORT_SCENE_PRESETS,
        import_scene_presets,
        schema=vol.Schema({
            vol.Optional("take_over_entities", default=True): cv.boolean,
            vol.Optional("overwrite", default=False): cv.boolean,
        }),
        supports_response=SupportsResponse.OPTIONAL
    )


    return True

async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    hass.data.setdefault(DOMAIN, {})

    await async_setup_view(hass)

    async_setup_websocket_api(hass, dynamic_scene_manager, hass.data[DOMAIN]["saved_scenes"])

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

async def async_remove_entry(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:

    await async_remove_view(hass)
