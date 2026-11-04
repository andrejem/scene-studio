# Added by andrejem (2026): presets created in the panel (from a photo or from colors, "generated"
# picture) and replaced images, colors or default brightness of existing presets (blocking file access,
# called in the executor; the caller reloads the presets).
# Everything is stored in userdata/custom/presets.json, the same file that
# hand-written custom presets use: unknown keys and existing entries are kept as they are.

import base64
import binascii
import json
import logging
import os
import re
import shutil
import time
import uuid

from .file_utils import CUSTOM_DIR, PRESET_DATA, custom_presets_path

_LOGGER = logging.getLogger(__name__)

USER_IMG_PREFIX = "user/"
USER_IMG_DIR = os.path.join(CUSTOM_DIR, "assets", "user")
USER_IMG_NAME = re.compile(r"^[0-9a-f-]{36}\.(jpg|png|webp)$")
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_LIGHTS = 10

# Category for presets created in the panel when no other category is chosen
DEFAULT_CATEGORY_ID = "5f0c3a8e-6b2d-4e1f-9a7c-2d8b4e6f1a30"


class CustomPresetError(Exception):
    """Error with a message for the user (shown in the panel)."""


def _read():
    if not os.path.exists(custom_presets_path):
        return {"categories": [], "presets": []}
    try:
        with open(custom_presets_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as err:
        # Never overwrite a file we cannot read: the user would lose hand-written presets
        raise CustomPresetError(f"userdata/custom/presets.json cannot be read: {err}") from err
    if not isinstance(data, dict):
        raise CustomPresetError("userdata/custom/presets.json is not a JSON object")
    data.setdefault("categories", [])
    data.setdefault("presets", [])
    return data


def _write(data):
    os.makedirs(CUSTOM_DIR, exist_ok=True)
    backup = custom_presets_path + ".orig"
    if os.path.exists(custom_presets_path) and not os.path.exists(backup):
        # Keep the hand-written file once, before the panel changes it for the first time
        shutil.copy2(custom_presets_path, backup)
    tmp = custom_presets_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
    os.replace(tmp, custom_presets_path)


def _save_image(image_b64):
    """Store a base64 image (data URL or plain base64), return the img value ("user/<file>")."""
    if "," in image_b64 and image_b64.startswith("data:"):
        image_b64 = image_b64.split(",", 1)[1]
    try:
        raw = base64.b64decode(image_b64, validate=True)
    except (binascii.Error, ValueError) as err:
        raise CustomPresetError("The image could not be read") from err
    if len(raw) > MAX_IMAGE_BYTES:
        raise CustomPresetError("The image is too large")
    if raw[:3] == b"\xff\xd8\xff":
        ext = "jpg"
    elif raw[:8] == b"\x89PNG\r\n\x1a\n":
        ext = "png"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        ext = "webp"
    else:
        raise CustomPresetError("Only JPEG, PNG and WebP images are supported")
    os.makedirs(USER_IMG_DIR, exist_ok=True)
    name = f"{uuid.uuid4()}.{ext}"
    with open(os.path.join(USER_IMG_DIR, name), "wb") as file:
        file.write(raw)
    return USER_IMG_PREFIX + name


def _remove_image(img):
    """Remove an image stored by the panel; hand-made images are never touched."""
    if not img or not img.startswith(USER_IMG_PREFIX):
        return
    name = img[len(USER_IMG_PREFIX):]
    if not USER_IMG_NAME.match(name):
        return
    try:
        os.remove(os.path.join(USER_IMG_DIR, name))
    except OSError:
        pass


def user_image_path(name):
    """Path of an image stored by the panel, None for anything else."""
    if not USER_IMG_NAME.match(name):
        return None
    path = os.path.join(USER_IMG_DIR, name)
    return path if os.path.isfile(path) else None


def _lights(lights):
    out = []
    for light in lights or []:
        x, y = float(light["x"]), float(light["y"])
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise CustomPresetError("Invalid color")
        out.append({"x": round(x, 4), "y": round(y, 4)})
    if not 1 <= len(out) <= MAX_LIGHTS:
        raise CustomPresetError(f"A preset needs 1 to {MAX_LIGHTS} colors")
    return out


def _builtin(preset_id):
    for preset in PRESET_DATA.get("presets", []):
        if preset.get("id") == preset_id and not preset.get("custom"):
            return preset
    return None


def _category_exists(category_id):
    return any(c.get("id") == category_id for c in PRESET_DATA.get("categories", []))


def _category(data, category_id, new_category, default_category_name):
    if new_category:
        name = new_category.strip()
        for category in data["categories"]:
            if category.get("name") == name:
                return category["id"]
        category = {"id": str(uuid.uuid4()), "name": name}
        data["categories"].append(category)
        return category["id"]
    if category_id:
        if not _category_exists(category_id) and not any(c.get("id") == category_id for c in data["categories"]):
            raise CustomPresetError("Unknown category")
        return category_id
    if not any(c.get("id") == DEFAULT_CATEGORY_ID for c in data["categories"]):
        data["categories"].append({"id": DEFAULT_CATEGORY_ID, "name": default_category_name or "My presets"})
    return DEFAULT_CATEGORY_ID


def save_preset(msg):
    """Create or update a preset of the custom presets file. Returns the stored preset."""
    data = _read()
    preset_id = msg.get("preset_id")
    existing = None
    if preset_id:
        existing = next((p for p in data["presets"] if p.get("id") == preset_id), None)
        if existing is None:
            raise CustomPresetError("Only own presets can be edited here")
    name = (msg.get("name") or "").strip()
    if not name:
        raise CustomPresetError("Please enter a name")

    preset = existing if existing is not None else {"id": str(uuid.uuid4())}
    preset["name"] = name
    preset["categoryId"] = _category(data, msg.get("category_id"), msg.get("new_category"), msg.get("default_category_name"))
    preset["bri"] = max(1, min(255, int(msg.get("bri", preset.get("bri", 255)))))
    preset["lights"] = _lights(msg.get("lights"))
    if msg.get("image"):
        old_img = preset.get("img")
        preset["img"] = _save_image(msg["image"])
        _remove_image(old_img)
    elif existing is None:
        raise CustomPresetError("Please choose a photo or colors")
    if "generated" in msg:
        # the picture is the gradient of the colors (made in the panel), renewed with the colors
        if msg["generated"]:
            preset["generated"] = True
        else:
            preset.pop("generated", None)
    if existing is None:
        data["presets"].append(preset)
    _write(data)
    return preset


def delete_preset(preset_id, used_by):
    data = _read()
    preset = next((p for p in data["presets"] if p.get("id") == preset_id), None)
    if preset is None:
        raise CustomPresetError("Only own presets can be deleted")
    if used_by:
        raise CustomPresetError("Used by saved scenes: " + ", ".join(used_by))
    data["presets"] = [p for p in data["presets"] if p.get("id") != preset_id]
    # remove the panel's default category again when it is empty
    if not any(p.get("categoryId") == DEFAULT_CATEGORY_ID for p in data["presets"]):
        data["categories"] = [c for c in data["categories"] if c.get("id") != DEFAULT_CATEGORY_ID]
    _write(data)
    _remove_image(preset.get("img"))


def set_override(preset_id, image, lights, bri=None):
    """New image, colors and/or default brightness for a built-in preset. The original stays untouched."""
    if _builtin(preset_id) is None:
        raise CustomPresetError("Unknown preset")
    if not image and not lights and bri is None:
        raise CustomPresetError("Nothing to change")
    data = _read()
    overrides = data.setdefault("overrides", {})
    override = overrides.setdefault(preset_id, {})
    if image:
        old_img = override.get("img")
        override["img"] = _save_image(image)
        _remove_image(old_img)
    if lights:
        override["lights"] = _lights(lights)
    if bri is not None:
        override["bri"] = max(1, min(255, int(bri)))
    override["changed"] = int(time.time())
    _write(data)


def reset_override(preset_id):
    data = _read()
    override = (data.get("overrides") or {}).pop(preset_id, None)
    if override is None:
        return
    if not data["overrides"]:
        del data["overrides"]
    _write(data)
    _remove_image(override.get("img"))
