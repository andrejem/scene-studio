# Modified by andrejem (2026): serves and auto-loads the room card (scene-studio-room-card);
# frontend URLs carry a hash of the file, so browsers load a new build without a version bump;
# images of presets created in the panel are served by a view (available without a restart);
# a picture shared by several presets (hidden presets) is registered once
import hashlib
from .const import NAME, DOMAIN, PANEL_URL, ROOM_CARD_URL
from .file_utils import VERSION, PRESET_DATA, BASE_PATH
from aiohttp import web
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from .custom_presets import USER_IMG_PREFIX, user_image_path
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
    url = f'/assets/{DOMAIN}/scene_studio.json'
    name = f'assets:{DOMAIN}:preset_data'
    requires_auth = False

    async def get(self, request):
        return self.json(
            result=PRESET_DATA,
        )

class CustomPresetImageView(HomeAssistantView):
    url = f'/assets/{DOMAIN}/{USER_IMG_PREFIX}{{name}}'
    name = f'assets:{DOMAIN}:user_image'
    requires_auth = False

    async def get(self, request, name):
        path = user_image_path(name)
        if path is None:
            return web.Response(status=404)
        # file names are unique per upload, so the image never changes behind a URL
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})

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
    hass.http.register_view(CustomPresetImageView)
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
        is_custom = preset.get("custom")

        if img_filename is not None and img_filename.startswith(USER_IMG_PREFIX):
            continue  # served by CustomPresetImageView
        if img_filename is not None:
            path = f"{BASE_PATH}/assets/{img_filename}"
            if is_custom is not None and is_custom:
                path = f"{BASE_PATH}/userdata/custom/assets/{img_filename}"

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
