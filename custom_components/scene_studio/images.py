# Added by andrejem (2026): preset pictures. Built-in pictures are part of the integration and are
# served as static files. Pictures of the user (uploaded in the panel or used by hand-written custom
# presets) are private: they are served only to logged-in users, and the panel and the scene entities
# get signed URLs for them, like Home Assistant does for camera pictures.

import os
from datetime import timedelta

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .custom_presets import USER_IMG_PREFIX, user_image_path
from .file_utils import CUSTOM_DIR, PRESET_DATA

PRIVATE_IMAGE_URL = f"/api/{DOMAIN}/image/"
PUBLIC_IMAGE_URL = f"/assets/{DOMAIN}/"
SIGNED_URL_VALIDITY = timedelta(hours=24)

_CUSTOM_ASSETS = os.path.join(CUSTOM_DIR, "assets")


def is_private(preset: dict) -> bool:
    img = preset.get("img")
    return bool(img) and (img.startswith(USER_IMG_PREFIX) or bool(preset.get("custom")))


def image_url(hass: HomeAssistant, preset: dict, *, use_content_user: bool = False) -> str | None:
    """URL of the preset picture: static for built-in pictures, signed for private ones.

    Without use_content_user the URL is signed for the user of the current request or websocket
    connection; scene entities use the content user, as their picture is shown to everyone who may
    see the entity.
    """
    img = preset.get("img")
    if not img:
        return None
    if not is_private(preset):
        return PUBLIC_IMAGE_URL + img
    from homeassistant.components.http.auth import async_sign_path

    try:
        return async_sign_path(
            hass, PRIVATE_IMAGE_URL + img, SIGNED_URL_VALIDITY, use_content_user=use_content_user
        )
    except KeyError:  # http not set up (yet)
        return None


def is_known_private_image(img: str) -> bool:
    """Only pictures of the user's own presets are served, nothing else from the disk."""
    return any(p.get("img") == img and is_private(p) for p in PRESET_DATA.get("presets", []))


def private_image_path(img: str) -> str | None:
    """Path of a private picture (blocking, run in the executor). None if there is none."""
    if img.startswith(USER_IMG_PREFIX):
        return user_image_path(img[len(USER_IMG_PREFIX):])
    path = os.path.realpath(os.path.join(_CUSTOM_ASSETS, img))
    if not path.startswith(os.path.realpath(_CUSTOM_ASSETS) + os.sep):
        return None
    return path if os.path.isfile(path) else None
