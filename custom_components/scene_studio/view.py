# Modified by andrejem (2026): serves and auto-loads the room card (scene-studio-room-card);
# frontend URLs carry a hash of the file, so browsers load a new build without a version bump;
# images of presets created in the panel are served by a view (available without a restart);
# a picture shared by several presets (hidden presets) is registered once;
# preset data and the user's own pictures need a login, pictures come with signed URLs (images.py)
import hashlib
from .const import NAME, DOMAIN, PANEL_URL, ROOM_CARD_URL
from .file_utils import VERSION, PRESET_DATA, BASE_PATH
from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView, StaticPathConfig
from .images import PRIVATE_IMAGE_URL, image_url, is_known_private_image, is_private, private_image_path
from homeassistant.components.frontend import async_remove_panel, async_register_built_in_panel

# Adapted from https://github.com/hacs/integration/blob/7d46a52de0df2466aa65e446458b952150398f4c/custom_components/hacs/frontend.py#L58
try:
    from homeassistant.components.frontend import add_extra_js_url
except ImportError:
    def add_extra_js_url(hass: HomeAssistant, url: str, es5: bool = False) -> None:
        if "frontend_extra_module_url" not in hass.data:
            hass.data["frontend_extra_module_url"] = set()
        hass.data["frontend_extra_module_url"].add(url)

class ScenePresetDataView(HomeAssistantView):
    """Presets and categories for the panel. Needs a login: custom presets belong to the user."""
    url = f'/assets/{DOMAIN}/scene_studio.json'
    name = f'assets:{DOMAIN}:preset_data'
    requires_auth = True

    async def get(self, request):
        hass = request.app[KEY_HASS]
        presets = []
        for preset in PRESET_DATA.get("presets", []):
            if is_private(preset):
                # signed for the user of this request, so <img> can load it without an auth header
                preset = {**preset, "img_url": image_url(hass, preset)}
            presets.append(preset)
        return self.json({**PRESET_DATA, "presets": presets})


class PrivatePresetImageView(HomeAssistantView):
    """Pictures of the user's own presets. Needs a login or a signed URL."""
    url = PRIVATE_IMAGE_URL + '{img:.+}'
    name = f'api:{DOMAIN}:image'
    requires_auth = True

    async def get(self, request, img):
        if not is_known_private_image(img):
            return web.Response(status=404)
        hass = request.app[KEY_HASS]
        path = await hass.async_add_executor_job(private_image_path, img)
        if path is None:
            return web.Response(status=404)
        return web.FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})

def _file_hash(path):
    try:
        with open(path, "rb") as file:
            return hashlib.sha1(file.read()).hexdigest()[:10]
    except OSError:
        return VERSION


async def async_setup_view(hass):
    panel_path = hass.config.path(f'{BASE_PATH}/frontend/scene_studio_panel.js')
    card_path = hass.config.path(f'{BASE_PATH}/frontend/scene-studio-room-card.js')
    panel_hash = await hass.async_add_executor_job(_file_hash, panel_path)
    card_hash = await hass.async_add_executor_job(_file_hash, card_path)
    static_paths = [
        StaticPathConfig(PANEL_URL, hass.config.path(f'{BASE_PATH}/frontend/scene_studio_panel.js'), True),
        StaticPathConfig(f'/assets/{DOMAIN}/iconset.js', hass.config.path(f'{BASE_PATH}/res/iconset.js'), True),
        StaticPathConfig(ROOM_CARD_URL, hass.config.path(f'{BASE_PATH}/frontend/scene-studio-room-card.js'), True),
    ]
    
    static_paths.extend(await get_preset_image_paths(hass))

    await hass.http.async_register_static_paths(static_paths)

    hass.http.register_view(ScenePresetDataView)
    hass.http.register_view(PrivatePresetImageView)
    add_extra_js_url(hass, f"/assets/{DOMAIN}/iconset.js?{VERSION}")
    add_extra_js_url(hass, f"{ROOM_CARD_URL}?{card_hash}")

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title=NAME,
        sidebar_icon="scene_studio:scene_studio",
        frontend_url_path="scene-studio",
        require_admin=False,
        config={
            "_panel_custom": {
                "name": "scene-studio-panel",
                "module_url": f"{PANEL_URL}?{panel_hash}"
            },
            "version": VERSION
        },
    )

async def async_remove_view(hass):
    async_remove_panel(hass, "scene-studio")

async def get_preset_image_paths(hass):
    static_paths = []
    seen = set()

    for preset in PRESET_DATA.get("presets", []):
        img_filename = preset.get("img")

        if img_filename is not None and is_private(preset):
            continue  # pictures of the user: PrivatePresetImageView
        if img_filename is not None:
            path = f"{BASE_PATH}/assets/{img_filename}"

            url = f'/assets/{DOMAIN}/{img_filename}'
            if url in seen:
                continue
            seen.add(url)
            static_paths.append(
                StaticPathConfig(
                    url,
                    hass.config.path(path),
                    True
                )
            )

    return static_paths
