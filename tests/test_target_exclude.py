"""Targets with an "exclude" block (Home Assistant 2026.11): the excluded lights are left out (#16)."""

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, label_registry as lr

from .test_custom_presets import setup, userdata  # noqa: F401  (fixture and helper)

PRESET = "940fd864-51e1-4761-95d3-75d4d68835ea"  # Arctic aurora


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _home(hass, monkeypatch):
    """Two areas (office, hallway) with a ceiling and a lamp each, a group of the two ceilings, a label."""
    calls = []

    async def turn_on(call):
        calls.append(dict(call.data))

    hass.services.async_register("light", "turn_on", turn_on)
    areas, entities, labels = ar.async_get(hass), er.async_get(hass), lr.async_get(hass)
    devices = dr.async_get(hass)
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain="test")
    entry.add_to_hass(hass)
    night = labels.async_create("Night")
    attrs = {"supported_color_modes": ["xy"], "color_mode": "xy"}
    for area_name in ("office", "hallway"):
        area = areas.async_create(area_name)
        for name in ("ceiling", "lamp"):
            device = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={("test", f"{area_name}_{name}")})
            devices.async_update_device(device.id, area_id=area.id)
            entity = entities.async_get_or_create("light", "test", f"{area_name}_{name}", device_id=device.id,
                                                  suggested_object_id=f"{area_name}_{name}")
            if name == "lamp" and area_name == "hallway":
                entities.async_update_entity(entity.entity_id, labels={night.label_id})
            hass.states.async_set(entity.entity_id, "on", attrs)
    hass.states.async_set("light.ceilings", "on", {**attrs, "entity_id": ["light.office_ceiling", "light.hallway_ceiling"]})
    await setup(hass, monkeypatch)
    return calls, areas, devices, night


async def _lit(hass, calls, targets, **extra):
    calls.clear()
    await hass.services.async_call(
        "scene_studio", "apply_preset", {"preset_id": PRESET, "targets": targets, **extra}, blocking=True)
    await hass.async_block_till_done()
    return sorted(c["entity_id"] for c in calls)


async def test_the_exclude_block_leaves_lights_out(hass: HomeAssistant, monkeypatch, userdata, hass_ws_client):
    calls, areas, devices, night = await _home(hass, monkeypatch)
    office, hallway = areas.async_get_area_by_name("office").id, areas.async_get_area_by_name("hallway").id
    both = [office, hallway]
    everything = ["light.hallway_ceiling", "light.hallway_lamp", "light.office_ceiling", "light.office_lamp"]

    assert await _lit(hass, calls, {"area_id": both}) == everything   # without exclude: as before
    # the case of the issue: the ceiling of each area excluded
    assert await _lit(hass, calls, {"area_id": both, "exclude": {"entity_id": ["light.office_ceiling", "light.hallway_ceiling"]}}) \
        == ["light.hallway_lamp", "light.office_lamp"]
    assert await _lit(hass, calls, {"area_id": both, "exclude": {"area_id": hallway}}) == ["light.office_ceiling", "light.office_lamp"]
    device = devices.async_get_device(identifiers={("test", "office_lamp")})
    assert await _lit(hass, calls, {"area_id": both, "exclude": {"device_id": [device.id]}}) \
        == ["light.hallway_ceiling", "light.hallway_lamp", "light.office_ceiling"]
    assert await _lit(hass, calls, {"area_id": both, "exclude": {"label_id": night.label_id}}) \
        == ["light.hallway_ceiling", "light.office_ceiling", "light.office_lamp"]
    # a group in the exclude block leaves out its members
    assert await _lit(hass, calls, {"area_id": both, "exclude": {"entity_id": "light.ceilings"}}) == ["light.hallway_lamp", "light.office_lamp"]
    # together with Scene Studio's own exclude
    assert await _lit(hass, calls, {"area_id": both, "exclude": {"area_id": hallway}}, exclude=["light.office_lamp"]) == ["light.office_ceiling"]
    # an empty block changes nothing
    assert await _lit(hass, calls, {"area_id": both, "exclude": {}}) == everything

    # the panel lists the same lights
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "scene_studio/resolve_targets",
                                    "targets": {"area_id": both, "exclude": {"entity_id": ["light.office_ceiling", "light.hallway_ceiling"]}}})
    lights = (await client.receive_json())["result"]["lights"]
    assert sorted(l["entity_id"] for l in lights) == ["light.hallway_lamp", "light.office_lamp"]


async def test_a_saved_scene_with_an_exclude_block(hass: HomeAssistant, monkeypatch, userdata):
    calls, areas, _devices, _night = await _home(hass, monkeypatch)
    both = [areas.async_get_area_by_name("office").id, areas.async_get_area_by_name("hallway").id]
    saved = await hass.services.async_call("scene_studio", "save_scene", {
        "name": "Evening", "preset_id": PRESET,
        "targets": {"area_id": both, "exclude": {"entity_id": ["light.office_ceiling", "light.hallway_ceiling"]}},
    }, blocking=True, return_response=True)
    calls.clear()
    await hass.services.async_call("scene", "turn_on", {"entity_id": "scene.evening"}, blocking=True)
    await hass.async_block_till_done()
    assert sorted(c["entity_id"] for c in calls) == ["light.hallway_lamp", "light.office_lamp"], saved
