# Modified by andrejem (2026): filter_targets() for the exclude list, groups kept as one light
# and segment lights. Brightness per light (light_brightness), 0 % = off when the scene starts.

import re
from homeassistant.helpers import entity_registry, device_registry, area_registry


def ensure_list(data):
    if isinstance(data, list):
        data = data
    elif isinstance(data, str):
        data = [data]
    else:
        data = []

    return data


def resolve_targets(hass, entity_ids, device_ids, area_ids, floor_ids, label_ids):
    entity_reg = entity_registry.async_get(hass)
    device_reg = device_registry.async_get(hass)
    area_reg = area_registry.async_get(hass)


    entity_ids_to_process = set(entity_ids)
    device_ids_to_process = set(device_ids)
    area_ids_to_process = set(area_ids)

    # 1. Process labels: can yield entities, devices, or areas
    for label_id in label_ids:
        for entry in entity_registry.async_entries_for_label(entity_reg, label_id):
            entity_ids_to_process.add(entry.entity_id)
        for entry in device_registry.async_entries_for_label(device_reg, label_id):
            device_ids_to_process.add(entry.id)
        for entry in area_registry.async_entries_for_label(area_reg, label_id):
            area_ids_to_process.add(entry.id)

    # 2. Process floors: can yield areas
    for floor_id in floor_ids:
        for entry in area_registry.async_entries_for_floor(area_reg, floor_id):
            area_ids_to_process.add(entry.id)

    # 3. Process areas: can yield devices or entities
    for area_id in area_ids_to_process:
        # 3.1 Add entities directly assigned to this area
        for entity in entity_registry.async_entries_for_area(entity_reg, area_id):
            entity_ids_to_process.add(entity.entity_id)

        # 3.2 Process devices of areas here, as entities of devices may not be part of the same area the device is in
        #     Only here do we know that the parent device was only referenced by an area + _which_ area it was
        for device in device_registry.async_entries_for_area(device_reg, area_id):
            for entity in entity_registry.async_entries_for_device(entity_reg, device.id):
                # Skip any device entities that are in a different area than their parent device
                if entity.area_id is None or entity.area_id == area_id:
                    entity_ids_to_process.add(entity.entity_id)

    # 4. Process explicitly targeted devices: can yield entities
    for device_id in device_ids_to_process:
        for entity in entity_registry.async_entries_for_device(entity_reg, device_id):
            entity_ids_to_process.add(entity.entity_id)

    # 5. Process entities: can yield even more entities
    #    This resolves any groups and also filters down to light entities only
    resolved_entity_ids = []
    for entity_id in entity_ids_to_process:
        resolved_entity_ids.extend(resolve_entity_ids(hass, entity_id))

    # 6. Deduplicate all resolved entity_ids
    #    This is required, because we may have resolved multiple groups that share one or more members
    resolved_entity_ids = list(set(resolved_entity_ids))

    return resolved_entity_ids


def resolve_entity_ids(hass, entity_id, depth=0):
    resolved_ids = []

    if not entity_id.startswith(("light", "group")):
        return resolved_ids

    # If you have groups nested 4+ layers deep, you should rethink your life choices
    if depth > 4:
        return resolved_ids

    if entity := hass.states.get(entity_id):
        nested_entity_ids = entity.attributes.get("entity_id", [])

        if not nested_entity_ids: # It's just a plain old light
            resolved_ids.append(entity_id)

        else: # It's a group possibly pretending to be a light
            conf_entry = get_config_entry(hass, entity_id)

            if conf_entry is not None:
                if conf_entry.domain != "group":
                    # If the domain isn't "group", the entity is something unexpected (e.g. a lightener custom_component entity)
                    # Thus, we don't resolve them further as we can't make assumptions over the purpose of the entity
                    resolved_ids.append(entity_id)
                else:
                    # It's a group
                    # noinspection PySimplifyBooleanCheck
                    if conf_entry.options.get("hide_members", False) == False:
                        # If hide_members is not enabled, we assume that the user uses this group to just organize multiple things
                        # Therefore, we do resolve them further
                        for nested_entity_id in nested_entity_ids:
                            resolved_ids.extend(resolve_entity_ids(hass, nested_entity_id, depth + 1))
                    else:
                        # If hide_members is enabled, we assume that the user intended to have a single logical light
                        # consisting of multiple physical ones
                        # Consequently, we don't resolve further to not make a single fixture light up with different settings
                        resolved_ids.append(entity_id)
            else:
                # If there is no config entry (e.g. YAML-configured group), continue resolving further
                for nested_entity_id in nested_entity_ids:
                    resolved_ids.extend(resolve_entity_ids(hass, nested_entity_id, depth + 1))

    return resolved_ids


def get_config_entry(hass, entity_id):
    entity_reg = entity_registry.async_get(hass)

    if entity_reg_entry := entity_reg.async_get(entity_id):
        if conf_entry := hass.config_entries.async_get_entry(entity_reg_entry.config_entry_id):
            return conf_entry

    return None


# Added by andrejem (2026): exclude list and segment lights for area/device/label targets
SEGMENT_SUFFIX = re.compile(r"_segment_\d+$")


def filter_targets(hass, light_entity_ids, explicit_entity_ids, exclude, keep_groups=None):
    """Remove excluded lights (groups are resolved to their members) and segment lights.

    Segment lights (e.g. Zigbee2MQTT/Govee ``light.x_segment_001``) are only kept when they were
    targeted explicitly; through an area, device or label they would fight with the main light.

    Groups in ``keep_groups`` are controlled as one light: their members are replaced by the group.
    """
    excluded = set()
    for entity_id in ensure_list(exclude):
        excluded.add(entity_id)
        excluded.update(resolve_entity_ids(hass, entity_id))
    explicit = set()
    for entity_id in ensure_list(explicit_entity_ids):
        explicit.update(resolve_entity_ids(hass, entity_id))
    result = [
        entity_id for entity_id in light_entity_ids
        if entity_id not in excluded
        and (entity_id in explicit or not SEGMENT_SUFFIX.search(entity_id))
    ]
    for group_id in ensure_list(keep_groups):
        if group_id in excluded or hass.states.get(group_id) is None:
            continue
        members = set(resolve_entity_ids(hass, group_id))
        result = [entity_id for entity_id in result if entity_id not in members]
        if group_id not in result:
            result.append(group_id)
    return result


def light_percent_for(hass, entity_id, light_brightness):
    """Percent from ``light_brightness`` for one light, or None when it has no own value.

    A light inside a group that has a value uses the group's value; a group without own value
    uses the value of its first member that has one.
    """
    if not light_brightness:
        return None
    percent = light_brightness.get(entity_id)
    if percent is None:
        for key, value in light_brightness.items():
            if key != entity_id and entity_id in resolve_entity_ids(hass, key):
                percent = value
                break
    if percent is None:
        state = hass.states.get(entity_id)
        for member in (state.attributes.get("entity_id", []) if state else []):
            if member in light_brightness:
                percent = light_brightness[member]
                break
    return None if percent is None else float(percent)


def light_brightness_for(hass, entity_id, light_brightness, default):
    """Brightness (0-255) for one light: its own percent from ``light_brightness`` or the default.

    0 % means "off when the scene starts"; a light with 0 % that is turned on later (optional
    light, lamp mode) gets the default brightness.
    """
    percent = light_percent_for(hass, entity_id, light_brightness)
    if percent is None or percent <= 0:
        return default
    return max(1, min(255, round(percent * 255 / 100)))


def split_off(hass, light_entity_ids, light_brightness):
    """Split lights into (lights to turn on, lights with 0 % that the scene turns off)."""
    on, off = [], []
    for entity_id in light_entity_ids:
        percent = light_percent_for(hass, entity_id, light_brightness)
        (off if percent is not None and percent <= 0 else on).append(entity_id)
    return on, off


async def turn_off_lights(hass, light_entity_ids, transition):
    """Turn off the lights a scene switches off (0 % brightness)."""
    if not light_entity_ids:
        return
    await hass.services.async_call(
        "light", "turn_off",
        {"entity_id": list(light_entity_ids), "transition": transition},
        blocking=False,
    )
