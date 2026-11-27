# Services

All services are in the domain `scene_studio`. `targets` takes the usual Home Assistant target
(`entity_id`, `device_id`, `area_id`, `floor_id`, `label_id`), also with an `exclude` block as the
target picker of Home Assistant 2026.11 writes it ([Lights of a scene](Lights%20of%20a%20scene.md));
light groups are resolved to their members unless they are listed in `keep_groups`. Preset IDs are listed in the
[preset overview](../custom_components/scene_studio/assets/Readme.md); IDs of presets made in the
panel are shown in `userdata/custom/presets.json`.
Hidden presets (no longer shown in the panel) keep working with their ID.
The preset **Music** (`b1c7e3d2-2f4a-4c39-9d7e-6a1f0c5e8b42`) takes the colors of the album cover
that is playing in the room of the lights; without music, `apply_preset` and `start_dynamic_scene`
do nothing with it ([music scenes](Music%20scenes.md)).

## Apply presets

### `apply_preset`

Applies a preset once.

| Field | Required | Description |
|---|---|---|
| `preset_id` | yes | Preset to use |
| `targets` | yes | Lights to apply the preset to |
| `brightness` | | Brightness 0–255, overrides the brightness of the preset |
| `transition` | | Transition in seconds (default 1) |
| `shuffle` | | Shuffle the colors before applying them |
| `smart_shuffle` | | Shuffle so that neighbouring colors blend smoothly ([details](Smart%20Shuffle.md)) |
| `exclude` | | Lights to leave out ([details](Lights%20of%20a%20scene.md)) |
| `keep_groups` | | Light groups controlled as one light |
| `optional` | | Lights that take part only if they are on |
| `light_brightness` | | Brightness in percent per light, e.g. `{light.strip: 20}`; 0 = off at the start |
| `gradient` | | Default `true`: gradient lamps in Zigbee2MQTT show all colors of the preset ([details](Lights%20of%20a%20scene.md#gradient-lamps)); `false` = one color |
| `saturation` | | Color intensity −100 … 100, default 0: more vivid (+) or paler (−) colors, the hue stays ([details](Saved%20scenes.md#color-intensity)) |
| `brighten_deep` | | `true`: lights in deep colors (red, blue, violet) get more brightness, up to 100 % – see [Deep colors](Saved%20scenes.md#deep-colors) |
| `lighten_deep` | | 0 … 100: white mixed into deep colors so the room stays bright; bright colors stay as they are |

### `start_dynamic_scene`

Starts a loop that applies the preset with smart shuffled colors again and again.

| Field | Required | Description |
|---|---|---|
| `preset_id`, `targets`, `brightness` | | as for `apply_preset` (`preset_id` and `targets` required) |
| `interval` | | Seconds between color changes (all lights together) |
| `transition` | | Transition of a color change in seconds |
| `interval_min`, `interval_max` | | Per-light timing: every light waits a random time in this range ([details](Per-light%20timing.md)) |
| `transition_min`, `transition_max` | | Per-light timing: random transition in this range |
| `exclude`, `keep_groups`, `optional`, `light_brightness`, `gradient`, `saturation`, `brighten_deep`, `lighten_deep` | | as for `apply_preset` |

### `stop_dynamic_scene`, `stop_dynamic_scenes_for_targets`, `stop_all_dynamic_scenes`

| Service | Fields |
|---|---|
| `stop_dynamic_scene` | `id` – ID of the running dynamic scene (see `get_dynamic_scenes`) |
| `stop_dynamic_scenes_for_targets` | `targets` – stops every dynamic scene that uses one of these lights |
| `stop_all_dynamic_scenes` | – |

All three also end a [music scene](Music%20scenes.md) on these lights; the lights stay as they are.

`get_dynamic_scenes` returns the running dynamic scenes (also as websocket command
`scene_studio/get_dynamic_scenes`).

## Saved scenes

### `save_scene`

Saves a preset with lights and settings as a scene and creates (or updates) its scene entity.
Returns the stored scene, including its `id`.

| Field | Required | Description |
|---|---|---|
| `name` | yes | Name of the scene and its entity |
| `preset_id` | yes | Preset to use |
| `targets` | yes | Lights of the scene |
| `id` | | ID of an existing scene to overwrite (the entity keeps its ID) |
| `dynamic` | | Start a dynamic scene instead of applying the preset once |
| `music` | | Only for the preset Music: `media_player` (default: speaker of the scene's room; `any`: whichever speaker is playing), `auto_start` (`never`, `follow`, `always`), `when_on` (start by itself also when a light is on), `resume` (continue when the lights were off and come back on within 30 minutes; default `false`), `focus` (which colors of the cover count: `100` the most vivid ones, `0` the largest areas; default `100`), `roles` (lights that show only the main color or only the accent colors, for example `{"light.ceiling": "main", "light.strip": "accent"}`) – see [music scenes](Music%20scenes.md) |
| `daytime` | | Only for the preset Time of day: the ID of a saved scene for `day`, `dusk` and `night`, and `follow` (change with the time of day while the lights are on; default `false`) – see [Time of day scenes](Time%20of%20day.md) |
| all fields of `apply_preset` / `start_dynamic_scene` | | stored with the scene |

### `activate_saved_scene`

Same as turning on the scene entity.

| Field | Required | Description |
|---|---|---|
| `id` | yes | ID of the saved scene |
| `dynamic` | | Override the saved mode: `false` applies a dynamic scene once, `true` starts a static scene as dynamic scene |
| `targets` | | Apply the scene to these lights instead of its own ([lamp modes](Lamp%20modes.md)); a music scene then uses its current cover colors |

### `delete_saved_scene`

| Field | Required | Description |
|---|---|---|
| `id` | yes | ID of the saved scene; its scene entity is removed as well |

## Examples

```yaml
# Living room in "Rest", a bit darker, with a slow transition
action: scene_studio.apply_preset
data:
  preset_id: e03267e7-9914-4f47-97fe-63c0bd317fe7   # Rest
  targets:
    area_id: living_room
  brightness: 150
  transition: 5
```

```yaml
# Colors drifting slowly, every light on its own schedule
action: scene_studio.start_dynamic_scene
data:
  preset_id: e71b2ef3-1b15-4c4b-b036-4b3d6efe58f8
  targets:
    area_id: living_room
  interval_min: 20
  interval_max: 60
  transition_min: 5
  transition_max: 15
```

```yaml
# Stop whatever runs in the living room
action: scene_studio.stop_dynamic_scenes_for_targets
data:
  targets:
    area_id: living_room
```

## Websocket commands (for the panel)

| Command | Purpose |
|---|---|
| `scene_studio/get_saved_scenes` | List saved scenes |
| `scene_studio/get_dynamic_scenes` | List running dynamic scenes |
| `scene_studio/resolve_targets` | Lights a scene with these targets controls |
| `scene_studio/get_soft_fade`, `set_soft_fade`, `set_soft_fade_smoothness` | Lights with [soft fade](Soft%20fade.md) and their steps per second (`rate` 1–20, `null` = off; the levels `coarse`, `normal`, `fine` of 3.8 still work as `level`) and the smoothness (`coarse`, `normal`, `fine`); setting needs an administrator |
| `scene_studio/get_music_scenes` | Active music scenes with speaker, cover and current colors |
| `scene_studio/get_daytime`, `preview_daytime`, `set_daytime` | Time of day: current phase, limits and next changes; what other limits would give; change the limits (admins) |
| `scene_studio/save_custom_preset`, `delete_custom_preset`, `set_preset_image`, `reset_preset` | Own presets from colors or photos, colors and default brightness of built-in presets (admins; the preset is passed as `preset_id`) – see [Own presets](Scene%20from%20photo.md) |
| `scene_studio/set_preset_hidden` | Hide a built-in preset or show it again (admins) |
| `scene_studio/set_scene_order` | Order of the saved scenes, `scene_ids` in the new order (admins) |
| `scene_studio/import_status`, `scene_studio/import` | Import from Scene Presets (admins) |
