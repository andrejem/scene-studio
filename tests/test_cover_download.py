"""Download of album covers for music scenes: size limit, internal and external URLs."""

import pytest

from homeassistant.core import HomeAssistant

from .test_custom_presets import setup, userdata  # noqa: F401  (fixture and helpers)
from .test_music_scenes import _image

PLAYER = "media_player.living_room"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def colors(hass, picture):
    hass.states.async_set(PLAYER, "playing", {"entity_picture": picture, "media_album_name": "A"})
    music = hass.data["scene_studio"]["music_scenes"]
    return await music._colors_from_cover("test", hass.states.get(PLAYER))


async def test_cover_from_home_assistant(hass: HomeAssistant, aioclient_mock, monkeypatch, userdata):
    await setup(hass, monkeypatch)
    hass.config.internal_url = "http://ha.local:8123"
    aioclient_mock.get("http://ha.local:8123/api/media_player_proxy/x?token=t",
                       content=_image([(220, 20, 30), (20, 40, 200)]))
    assert await colors(hass, "/api/media_player_proxy/x?token=t")


async def test_cover_from_the_internet(hass: HomeAssistant, aioclient_mock, monkeypatch, userdata):
    await setup(hass, monkeypatch)
    aioclient_mock.get("https://covers.example/a.png", content=_image([(220, 20, 30), (20, 40, 200)]))
    assert await colors(hass, "https://covers.example/a.png")


async def test_cover_too_large(hass: HomeAssistant, aioclient_mock, monkeypatch, userdata):
    from custom_components.scene_studio import music_scenes

    await setup(hass, monkeypatch)
    monkeypatch.setattr(music_scenes, "MAX_COVER_BYTES", 100)
    aioclient_mock.get("https://covers.example/big.png", content=_image([(220, 20, 30), (20, 40, 200)]))
    assert await colors(hass, "https://covers.example/big.png") is None
