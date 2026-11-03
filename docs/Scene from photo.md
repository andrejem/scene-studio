# Scene from photo

Create your own presets from photos in the panel - no JSON, no restart. Admin users only.

## New preset

![Preset from a photo](../img/scene-from-photo.png)

1. Open the panel, tab **Presets**, and click **Preset from a photo**.
2. **Choose photo** - on the phone also straight from the gallery or the camera.
3. The browser picks the dominant colors of the photo (3 to 6, see *Number of colors*). Greys,
   near black and near white are skipped, pale colors are made a bit stronger, so the light does
   not look washed out. One-colored photos give fewer colors instead of near duplicates.
4. Adjust the colors: tap a color to change it, **×** removes it, **+** adds one.
5. **Try on lights** shows the colors on the lights chosen under **Apply to** (choose them in the
   *Presets* tab first). Lights without color support are skipped.
6. Enter a name, choose a category (default *My presets*, or a new category) and the brightness,
   then **Save**. The preset shows up in its category right away.

The photo is stored at up to 1024 px as JPEG. Nothing leaves your Home Assistant: the colors are
picked in the browser.

## Edit or delete own presets

Own presets have a **pencil** on their tile: change name, category, brightness, colors or the
photo (**Other photo**, then **Take colors from the photo** if the colors should follow it).
**Delete** removes the preset and its photo. A preset that is used by a saved scene cannot be
deleted - the message names the scenes.

## Change built-in presets

In the photo dialog, choose a built-in preset in the list at the top (changed presets are marked
with `*` and get a pencil on their tile). You can replace its picture and/or its colors:
**Other photo** replaces only the picture, **Take colors from the photo** also takes its colors,
or change single colors by hand. **Restore original** brings back the original picture and colors.

Saved scenes and dashboards that use the preset show the new picture right away.

## Where it is stored

Everything lives in `custom_components/scene_studio/userdata/custom/` (kept by HACS updates):

- `presets.json` - the same file as for [hand-written custom presets](Custom%20Presets.md).
  Presets from the panel are normal entries; changes of built-in presets are stored under
  `overrides` (`{preset_id: {img, lights}}`). Hand-written entries and unknown keys are kept.
  Before the panel changes the file for the first time, a copy is saved as `presets.json.orig`.
  A file that cannot be read is never overwritten.
- `assets/user/` - the photos (unique file names, removed again when a preset is deleted or its
  photo replaced).

Your photos stay private: they are only served to logged-in users of Home Assistant
(`/api/scene_studio/image/...`). The panel and the scene entities get signed links to them that are
valid for a limited time and renewed automatically, the same way Home Assistant shows camera pictures.
The pictures of [hand-written custom presets](Custom%20Presets.md) are treated the same way; only the
pictures of the built-in presets are public files.

## Websocket commands (admin only)

| Command | Fields |
|---|---|
| `scene_studio/save_custom_preset` | `name`, `bri` (1-255), `lights` (`[{x, y}]`, 1-10), optional `preset_id` (edit), `image` (base64 or data URL, JPEG/PNG/WebP, max 4 MB), `category_id` or `new_category`, `default_category_name` |
| `scene_studio/delete_custom_preset` | `preset_id` |
| `scene_studio/set_preset_image` | `preset_id` of a built-in preset, `image` and/or `lights` |
| `scene_studio/reset_preset` | `preset_id` - restores the original |
