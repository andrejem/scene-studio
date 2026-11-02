# Modified by andrejem (2026): constants for per-light timing, saved scenes, room card, exclude
# and the music preset.

DOMAIN = "scene_studio"
NAME = "Scene Studio"

PANEL_URL = "/scene_studio_panel.js"
ROOM_CARD_URL = "/scene_studio_room_card.js"  # added by andrejem (2026)

SERVICE_APPLY_PRESET = "apply_preset"
SERVICE_START_DYNAMIC_SCENE = "start_dynamic_scene"
SERVICE_STOP_DYNAMIC_SCENE = "stop_dynamic_scene"
SERVICE_STOP_ALL_DYNAMIC_SCENES = "stop_all_dynamic_scenes"
SERVICE_STOP_DYNAMIC_SCENES_FOR_TARGETS = "stop_dynamic_scenes_for_targets"
SERVICE_GET_DYNAMIC_SCENES = "get_dynamic_scenes"

ATTR_SCENE_PRESET_ID = "preset_id"
ATTR_TARGETS = "targets"
ATTR_BRIGHTNESS = "brightness"
ATTR_TRANSITION = "transition"
ATTR_SHUFFLE = "shuffle"
ATTR_SMART_SHUFFLE = "smart_shuffle"
ATTR_INTERVAL = "interval"

ATTR_DYNAMIC_SCENE_ID = "id"

# Added by andrejem (2026): per-light random timing
ATTR_INTERVAL_MIN = "interval_min"
ATTR_INTERVAL_MAX = "interval_max"
ATTR_TRANSITION_MIN = "transition_min"
ATTR_TRANSITION_MAX = "transition_max"
ATTR_PER_LIGHT = "per_light"
ATTR_INTERVAL_RANGE = "interval_range"
ATTR_TRANSITION_RANGE = "transition_range"

# Added by andrejem (2026): saved scenes
SERVICE_SAVE_SCENE = "save_scene"
SERVICE_DELETE_SAVED_SCENE = "delete_saved_scene"
SERVICE_ACTIVATE_SAVED_SCENE = "activate_saved_scene"
ATTR_NAME = "name"
ATTR_DYNAMIC = "dynamic"
ATTR_EXCLUDE = "exclude"
ATTR_KEEP_GROUPS = "keep_groups"
ATTR_OPTIONAL = "optional"
# Brightness per light in a scene: {entity_id: percent 1-100}, overrides the scene brightness
ATTR_LIGHT_BRIGHTNESS = "light_brightness"

# Added by andrejem (2026): import from Scene Presets
SERVICE_IMPORT_SCENE_PRESETS = "import_scene_presets"

# Added by andrejem (2026): built-in preset "Music" - colors from the album cover of a speaker
MUSIC_PRESET_ID = "b1c7e3d2-2f4a-4c39-9d7e-6a1f0c5e8b42"
