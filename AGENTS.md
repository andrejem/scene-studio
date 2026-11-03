# AGENTS.md

Guidance for contributors and coding agents working on this repository.

## About this repository

Scene Studio is a Home Assistant custom integration (domain `scene_studio`) that applies color
presets to any `light` entity, saves scenes as scene entities and brings a panel and a room card.
It is based on [Scene Presets](https://github.com/Hypfer/hass-scene_presets) by Sören Beye and can
be installed next to it; `migrate.py` imports data from Scene Presets (domain `scene_presets`).

## Layout

- `custom_components/scene_studio/` - the integration (Python, no external requirements)
  - `__init__.py` - service registration and schemas
  - `dynamic_scenes.py` - dynamic scene engine (endless loops applying shuffled presets)
  - `saved_scenes.py` - persistent saved scenes (HA storage) and mapping to service calls
  - `custom_presets.py` - presets created in the panel and overrides of built-in presets, stored in
    `userdata/custom/presets.json` and `userdata/custom/assets/user/`
  - `migrate.py` - import from Scene Presets (saved scenes, own presets, scene entities)
  - `scene.py` - scene platform, one entity per saved scene
  - `optional_lights.py` - optional lights that join an active scene when turned on
  - `gradient.py` - gradient lamps (Hue Signe, Play gradient … in Zigbee2MQTT): found via
    `+/bridge/devices`, mapped to light entities by the IEEE address in the device identifiers;
    `apply_preset` sends them all preset colors as `gradient` over MQTT (option `gradient`, default true)
  - `music_scenes.py` - music scenes: saved scenes with the preset Music (`MUSIC_PRESET_ID`) take the
    colors of the album cover of a speaker. Colors live in `RUNTIME_PRESETS` (`file_utils.py`,
    `music_<scene id>`), which `apply_preset` checks first. Sessions per scene: snapshot of the lights,
    auto start (`never`/`follow`/`always`, `when_on`), cover/track changes, return to the snapshot
    30 s after the music stops. Other scenes on the same lights end a session (`release_lights`).
  - `presets.py` - applies a preset to a list of light entities
  - `util.py` - target resolution, exclude / keep_groups, brightness per light (0 % = off at start)
  - `color_management.py`, `color_temperature.py` - color selection and CT fallback
  - `view.py`, `websocket_api.py` - panel registration, static assets, websocket commands
  - `images.py` - preset pictures: built-in ones are public static files, the user's own pictures
    (uploads, hand-written custom presets) need a login and are linked with signed URLs (panel data,
    `entity_picture` of the scene entities, renewed every 12 hours)
    (`id` is the message id of the websocket protocol, use `preset_id`).
    Panel and room card URLs carry a hash of the file (`?<hash>`); the hash is computed when
    Home Assistant starts, so a new build needs a restart to reach the browsers.
  - `presets.json`, `assets/` - built-in presets and their images. Every picture needs a free
    license and an entry in `assets/CREDITS.md` (photos with a known author and source; no logos,
    brands or recognizable people). Presets are never removed: `"hidden": true` takes them out of the panel
    lists, `replacedBy` names the preset whose picture they show; their ID keeps working.
  - `brand/` - icon shown by Home Assistant (2026.3+), made from `assets/logo/scene-studio.svg`
  - `frontend/scene_studio_panel.js` - **built** panel bundle, committed to the repo
  - `frontend/scene-studio-room-card.js` - room card (plain JS, no build step), served and
    auto-loaded via `view.py`; borrows Lit from Home Assistant's own elements
  - `services.yaml` - service fields and selectors (names and descriptions as fallback)
  - `translations/en.json` - texts Home Assistant shows at runtime: config flow (abort reasons) and
    service names, descriptions and field labels. Custom integrations do not read `strings.json`;
    `en.json` is the fallback for every language without its own file
- `js/` - panel source (React + TypeScript), built with webpack into `frontend/`:
  `App.tsx` tabs and data, `pages/ScenesPage.tsx` saved scenes by room, `pages/PresetApplyPage.tsx`
  presets tab, `components/SceneEditor.tsx` scene editor, `components/Controls.tsx` form controls,
  `components/RunningStrip.tsx` running dynamic scenes, `components/PhotoPresetDialog.tsx` presets
  from photos, `components/ImportBanner.tsx` import from Scene Presets, `tunables.ts` settings ↔
  service calls, `styles.ts` CSS with Home Assistant theme variables, `i18n.ts` texts EN/DE,
  `palette.ts` color picking
- `tests/` - pytest tests
- `docs/` - user documentation (one page per feature, `Services.md` reference); `img/` screenshots
  for README and docs, made with the English UI

## Rules

- Language in the repository (commits, branches, issues, PRs, code comments) is English.
- License is Apache-2.0. Keep `LICENSE`, `NOTICE` and the copyright notices of the original author.
  Every file of Scene Presets you modify gets a short header comment
  `# Modified by <name> (<year>): <what changed>` (or the `//` equivalent in TypeScript).
- Never break an existing feature unless the maintainer decided so explicitly. This includes
  services, saved scenes, custom presets, card options and the behavior of the panel and the room
  card. New options are optional and default to the current behavior; a deliberate break is noted
  in the release notes.
- New service parameters are optional and keep the current behavior by default.
- Security (from the HACS review): no view with `requires_auth = False` that returns user data;
  pictures of the user only through `images.py`. Filesystem calls never on the event loop, use
  `hass.async_add_executor_job`. Commands and services that read or change other integrations or the
  user's files are for admins (`@websocket_api.require_admin`, `async_register_admin_service`).
- A new or changed service, service field or config flow text goes into `services.yaml` **and**
  `translations/en.json` (name and description for every service and field).
  No curly braces in these texts: hassfest reads `{...}` as a placeholder and fails.
- Do not use names of Scene Presets (domain, services, panel, card, storage keys, browser storage
  keys): both integrations must work side by side.
- Update `README.md` and `docs/` together with every functional change. `README.md` is also shown
  in HACS, so it uses absolute URLs for images and links.
- Code changes go through a feature branch and a pull request.

## Frontend notes

- Custom elements receive props as JS properties (React 19), not as HTML attributes. Selectors such as
  `ha-icon[icon=...]` do not match; query the `icon` property instead.
- `mwc-button` is no longer rendered by Home Assistant 2026.x. Use plain styled `<button>` elements.

## Building the panel

Only needed when `js/` changes:

```
npm ci
npm run build
```

Commit the resulting `custom_components/scene_studio/frontend/scene_studio_panel.js`.

## Testing

Automated tests (websocket commands, presets created in the panel, import from Scene Presets) run
with `pytest-homeassistant-custom-component` (Python 3.13):

```
pip install pytest-homeassistant-custom-component==0.13.316
pytest
```

Everything else is tested in Home Assistant:

1. Copy `custom_components/scene_studio` to `/config/custom_components/` (or install it via HACS).
2. Restart Home Assistant.
3. Use Developer Tools > Actions to call the services and watch the lights / the HA log.
