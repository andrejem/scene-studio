# Lamp modes

A lamp mode gives **one lamp** (or a few) another scene of the room, while the rest of the room
keeps its scene. Example: the living room runs *Northern lights*, the reading lamp switches to
*Bright*.

`activate_saved_scene` with `targets` applies a saved scene (its preset and settings) to these
lights instead of the scene's own lights:

```yaml
action: scene_studio.activate_saved_scene
data:
  id: 7f3c...            # the "Living room bright" scene
  targets:
    entity_id: light.reading_lamp
```

- `exclude`, `keep_groups` and `optional` of the scene are ignored then; `light_brightness` is used.
  A light with 0 % is turned on with the scene brightness instead of being turned off.
- If the lamp is part of a running **dynamic scene**, only the lamp leaves it, the other lights keep
  going. The dynamic scene stops only when no light is left.
- `dynamic: false` / `dynamic: true` work as for the whole scene (apply once / start dynamic).

The scene ID is shown in the scene entity's attributes (`saved_scene_id`) and returned by
`save_scene`.

Typical use: a button or a Tap Dial on a lamp that cycles through the scenes of the room for this
lamp only.
