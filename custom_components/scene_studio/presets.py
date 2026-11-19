# Modified by andrejem (2026): optional brightness per light (light_brightness), runtime presets,
# gradient lamps get the preset colors as gradient (gradient.py), main and accent lights of music
# scenes take their colors from their own part of the preset (roles, pools).

import voluptuous as vol
import asyncio
import logging
from .file_utils import PRESET_DATA, RUNTIME_PRESETS
from .color_management import *
from .color_temperature import find_closest_ct_match
from .util import light_brightness_for, resolve_entity_ids
from .const import DOMAIN
from .gradient import gradient_colors
from .data import find_data
from .spatial import assign, async_field_for, shift_of

_LOGGER = logging.getLogger(__name__)


def _role_for(hass, entity_id, roles):
    """Role of a light in a music scene (main / accent): its own or the one of a group it is part of."""
    role = roles.get(entity_id)
    if role is None:
        for key, value in roles.items():
            if key != entity_id and entity_id in resolve_entity_ids(hass, key):
                return value
    return role


async def apply_preset(
    hass,
    preset_id,
    light_entity_ids,
    transition,
    shuffle,
    smart_shuffle,
    brightness_override=None,
    light_brightness=None,
    gradient=True,
    saturation=None,
    spatial=None,
):
    preset_data = RUNTIME_PRESETS.get(preset_id)
    for preset in [] if preset_data else PRESET_DATA.get("presets", []):
        if preset.get("id") == preset_id:
            preset_data = preset
            break

    if not preset_data:
        raise vol.Invalid(f"Preset '{preset_id}' not found.")

    brightness = brightness_override if brightness_override else preset_data.get("bri", 255)
    # music scenes (3.6): a dark cover without colors gives white light at a part of the brightness;
    # the next cover is applied without it, so the lights get brighter again
    dim = preset_data.get("dim")

    preset_colors = [(light["x"], light["y"]) for light in preset_data["lights"]]
    # color intensity of the scene (Scene Studio 3.5): applied on top of the preset, also for music colors
    preset_colors = adjust_saturation(preset_colors, saturation)

    randomized_colors = None
    if shuffle:
        randomized_colors = get_randomized_colors(preset_colors, len(light_entity_ids))
        random.shuffle(light_entity_ids) # While this _should_ be redundant, the result somehow feels better with it in place

    # Music scenes (3.6): lights with a role use only the main or the accent colors of the cover.
    # Presets without roles (everything else) are not affected.
    roles = preset_data.get("roles") or {}
    pools = {
        role: adjust_saturation([tuple(c) for c in colors], saturation)
        for role, colors in (preset_data.get("pools") or {}).items() if role in ("main", "accent") and colors
    } if roles else {}
    role_index = {}

    # Room canvas (4.0): lights with a place on a room plan get the color the picture has there.
    # Without "spatial", without places or without picture nothing changes.
    placed = {}
    runtime = find_data(hass)
    if spatial and len(preset_colors) > 1 and runtime is not None:
        places = {}
        for entity_id in light_entity_ids:
            place = runtime.room_plans.place_of(entity_id)
            if place is not None:
                places[entity_id] = place
        if places:
            field = await async_field_for(hass, preset_data)
            own = {}
            for entity_id in places if pools else ():
                pool = pools.get(_role_for(hass, entity_id, roles))
                if pool:
                    own[entity_id] = pool
            placed = assign(field, places, preset_colors, shift_of(spatial), own)

    tasks = []

    for index, entity_id in enumerate(light_entity_ids):
        light_params = {
            "brightness": light_brightness_for(hass, entity_id, light_brightness, brightness),
            "transition": transition,
            "entity_id": entity_id,
        }
        if dim and light_params["brightness"]:
            light_params["brightness"] = max(1, round(light_params["brightness"] * dim))
        hass_state = hass.states.get(entity_id)
        if not hass_state:
            continue

        role = _role_for(hass, entity_id, roles) if pools else None
        pool = pools.get(role)
        if entity_id in placed:
            next_color = placed[entity_id]["color"]
        elif pool:
            current_color = hass_state.attributes.get("xy_color", None)
            if shuffle and smart_shuffle and current_color is not None:
                next_color = get_next_smart_random_color(current_color, pool)
            elif shuffle:
                next_color = get_random_color(pool)
            else:
                next_color = get_next_color(role_index.get(role, 0), pool)
            role_index[role] = role_index.get(role, 0) + 1
        elif shuffle:
            current_color = hass_state.attributes.get("xy_color", None)

            if current_color is not None and smart_shuffle:
                next_color = get_next_smart_random_color(current_color, preset_colors)
            elif randomized_colors is not None and index < len(randomized_colors):
                next_color = randomized_colors[index]
            else:
                next_color = get_random_color(preset_colors)
        else:
            next_color = get_next_color(index, preset_colors)

        supported_color_modes = hass_state.attributes.get("supported_color_modes", "")
        color_support = any(mode in supported_color_modes for mode in ["xy", "hs", "rgb", "rgbw"])
        temp_support = "color_temp" in supported_color_modes
        brightness_support = "brightness" in supported_color_modes

        gradients = runtime.gradient if gradient and runtime is not None else None
        if color_support and gradients is not None and len(preset_colors) > 1 and gradients.is_gradient(entity_id):
            # A gradient lamp shows all colors of the preset, starting with the one it would get
            tasks.append(gradients.async_apply(
                entity_id,
                placed.get(entity_id, {}).get("strip") or gradient_colors(preset_colors, next_color),
                light_params["brightness"], transition,
            ))
            continue

        if color_support:
            light_params["xy_color"] = next_color
        elif temp_support:
            light_params["color_temp_kelvin"] = find_closest_ct_match(next_color[0], next_color[1])
        elif brightness_support:
            pass # Nothing to add to the payload. Brightness is already part of it
        else:
            continue # Not turning on the light since it neither supports color nor color temperature and not even dimming

        task = hass.services.async_call(
            "light",
            "turn_on",
            light_params,
            blocking=False,
        )
        tasks.append(task)

    await asyncio.gather(*tasks)
