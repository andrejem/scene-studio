# Modified by andrejem (2026): added scene_studio/get_saved_scenes and
# scene_studio/resolve_targets (lights of a scene, for brightness per light) commands,
# commands for presets created in the panel and replaced preset images (admin only),
# import from Scene Presets, active music scenes (get_music_scenes), gradient lamps in resolve_targets

import voluptuous as vol
from homeassistant.components import websocket_api
import homeassistant.helpers.config_validation as cv

from .optional_lights import split_optional
from .util import ensure_list, filter_targets, resolve_targets
from .migrate import async_import_status, async_import_scene_presets
from .custom_presets import CustomPresetError, save_preset, delete_preset, set_override, reset_override
from .file_utils import async_reload_preset_data

LIGHT_COLOR = vol.Schema({vol.Required("x"): vol.Coerce(float), vol.Required("y"): vol.Coerce(float)})

def async_setup_websocket_api(_hass, dynamic_scene_manager, saved_scene_store=None) -> None:
    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_studio/get_dynamic_scenes",
        }
    )
    def ws_get_dynamic_scenes(
            hass, connection, msg
    ) -> None:
        connection.send_result(msg["id"], dynamic_scene_manager.get_all_as_dict())


    websocket_api.async_register_command(_hass, ws_get_dynamic_scenes)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_studio/get_saved_scenes",
        }
    )
    def ws_get_saved_scenes(
            hass, connection, msg
    ) -> None:
        scenes = saved_scene_store.get_all() if saved_scene_store is not None else []
        connection.send_result(msg["id"], {"saved_scenes": scenes})

    websocket_api.async_register_command(_hass, ws_get_saved_scenes)

    @websocket_api.websocket_command({vol.Required("type"): "scene_studio/get_music_scenes"})
    @websocket_api.callback
    def ws_get_music_scenes(hass, connection, msg) -> None:
        """Active music scenes with their media player, album and current colors."""
        music = hass.data.get("scene_studio", {}).get("music_scenes")
        connection.send_result(msg["id"], {"active": music.get_state() if music else {}})

    websocket_api.async_register_command(_hass, ws_get_music_scenes)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_studio/resolve_targets",
            vol.Required("targets"): dict,
            vol.Optional("exclude"): cv.entity_ids,
            vol.Optional("keep_groups"): cv.entity_ids,
            vol.Optional("optional"): cv.entity_ids,
        }
    )
    def ws_resolve_targets(
            hass, connection, msg
    ) -> None:
        """The lights a scene with these targets controls (same rules as the services)."""
        targets = msg["targets"]
        entity_ids = ensure_list(targets.get("entity_id"))
        lights = filter_targets(
            hass,
            resolve_targets(
                hass,
                entity_ids,
                ensure_list(targets.get("device_id")),
                ensure_list(targets.get("area_id")),
                ensure_list(targets.get("floor_id")),
                ensure_list(targets.get("label_id")),
            ),
            entity_ids,
            msg.get("exclude"),
            msg.get("keep_groups"),
        )
        base, _on, optional_ids = split_optional(hass, lights, msg.get("optional"), msg.get("keep_groups"))
        gradients = hass.data.get("scene_studio", {}).get("gradient")
        result = []
        for entity_id in base + optional_ids:
            state = hass.states.get(entity_id)
            result.append({
                "entity_id": entity_id,
                "name": state.name if state else entity_id,
                "optional": entity_id in optional_ids,
                "gradient": bool(gradients and gradients.is_gradient(entity_id)),
            })
        result.sort(key=lambda light: light["name"].lower())
        connection.send_result(msg["id"], {"lights": result})

    websocket_api.async_register_command(_hass, ws_resolve_targets)

    def _scenes_using(preset_id):
        scenes = saved_scene_store.get_all() if saved_scene_store is not None else []
        return [s for s in scenes if s.get("preset_id") == preset_id]

    def _refresh_scenes(preset_id):
        # scene entities show the preset image: let them pick up the new one
        if saved_scene_store is not None:
            saved_scene_store.notify_preset_changed(preset_id)

    async def _run(hass, connection, msg, job, *args):
        try:
            result = await hass.async_add_executor_job(job, *args)
        except CustomPresetError as err:
            connection.send_error(msg["id"], "invalid_preset", str(err))
            return None, False
        await async_reload_preset_data(hass)
        return result, True

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_studio/save_custom_preset",
            vol.Optional("preset_id"): cv.string,
            vol.Required("name"): cv.string,
            vol.Optional("category_id"): cv.string,
            vol.Optional("new_category"): cv.string,
            vol.Optional("default_category_name"): cv.string,
            vol.Required("bri"): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
            vol.Required("lights"): [LIGHT_COLOR],
            vol.Optional("image"): cv.string,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_save_custom_preset(hass, connection, msg) -> None:
        preset, ok = await _run(hass, connection, msg, save_preset, msg)
        if ok:
            _refresh_scenes(preset["id"])
            connection.send_result(msg["id"], {"preset": preset})

    websocket_api.async_register_command(_hass, ws_save_custom_preset)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_studio/delete_custom_preset",
            vol.Required("preset_id"): cv.string,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_delete_custom_preset(hass, connection, msg) -> None:
        used_by = [s["name"] for s in _scenes_using(msg["preset_id"])]
        _, ok = await _run(hass, connection, msg, delete_preset, msg["preset_id"], used_by)
        if ok:
            connection.send_result(msg["id"], {})

    websocket_api.async_register_command(_hass, ws_delete_custom_preset)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_studio/set_preset_image",
            vol.Required("preset_id"): cv.string,
            vol.Optional("image"): cv.string,
            vol.Optional("lights"): [LIGHT_COLOR],
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_set_preset_image(hass, connection, msg) -> None:
        _, ok = await _run(hass, connection, msg, set_override, msg["preset_id"], msg.get("image"), msg.get("lights"))
        if ok:
            _refresh_scenes(msg["preset_id"])
            connection.send_result(msg["id"], {})

    websocket_api.async_register_command(_hass, ws_set_preset_image)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_studio/reset_preset",
            vol.Required("preset_id"): cv.string,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_reset_preset(hass, connection, msg) -> None:
        _, ok = await _run(hass, connection, msg, reset_override, msg["preset_id"])
        if ok:
            _refresh_scenes(msg["preset_id"])
            connection.send_result(msg["id"], {})

    websocket_api.async_register_command(_hass, ws_reset_preset)

    @websocket_api.websocket_command({vol.Required("type"): "scene_studio/import_status"})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_import_status(hass, connection, msg) -> None:
        connection.send_result(msg["id"], await async_import_status(hass, saved_scene_store))

    websocket_api.async_register_command(_hass, ws_import_status)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "scene_studio/import",
            vol.Optional("take_over_entities", default=True): bool,
            vol.Optional("overwrite", default=False): bool,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_import(hass, connection, msg) -> None:
        result = await async_import_scene_presets(
            hass, saved_scene_store, take_over_entities=msg["take_over_entities"], overwrite=msg["overwrite"]
        )
        connection.send_result(msg["id"], result)

    websocket_api.async_register_command(_hass, ws_import)
