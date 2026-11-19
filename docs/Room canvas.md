# Room canvas: colors by place in the room

Normally the colors of a preset are spread over the lights by chance. With the room canvas a scene
knows **where the lights are**. The picture of the preset is laid over the room, and every light
takes the color the picture has at its place: the warm side of a sunset is on one side of the room,
the dark blue on the other – every time the scene starts.

## In short

- You place the lights of a room **once** on its room plan, with the mouse or the finger. Every
  scene of that room uses the places; a scene only has a switch.
- The switch **Colors by place in the room** is off by default. Scenes without it, and lights
  without a place, behave as before.
- It works with every light Home Assistant knows, with built-in presets, your own photos and
  music scenes.
- Dynamic scenes **move the picture through the room** in a direction you choose, instead of
  changing colors by chance.

## Setting it up

**1. The room plan – once per room**

1. Tab **Scenes** → the floor plan symbol next to the name of the room opens its **room plan**.
2. Below the plan are all lights of the room that have no place yet: tap a light to put it on the
   plan, then drag it to where it is in the room. The plan is the room seen from above; which wall
   is at the top is up to you, as long as it is the same for all lights.
3. Choose the **format** of the plan with the symbols above it: landscape, square or portrait, so a
   narrow corridor or a balcony is not distorted. Or load your **own floor plan** (a drawing or a
   photo) with the floor plan symbol: the plan takes its format, and you place the lights right on
   it. A room with corners or niches needs no special form: the plan is the rectangle around the room.
4. A **light strip** or another long light: tap the light on the plan, then the strip symbol. It
   gets a second handle for its other end. Gradient lamps then show the colors along their length.

Everything is saved at once. The cross takes a light off the plan again. The room plan needs an
administrator.

**2. The scenes**

In the scene editor turn on **Colors by place in the room**. The scene shows the plan of its room
with the picture of the preset over it; the picture is cut to the format of the plan. If lights of
the scene have no place yet, the editor says so – the symbol next to it opens the room plan.
**Try** shows the result on the lights.

## How the colors are chosen

The lights only ever get the **colors of the preset** – the picture decides which light gets which
of them. The preset colors are put in the order in which the picture changes its colors, each with
the share it has in the preset. So a picture with colors that are close together (an aurora in blue
and green) still spreads all preset colors through the room, and no color is lost.

- All colors of the preset stay in use, as far as there are lights for them.
- Presets without a picture, and pictures in a single color, run their colors from left to right.
- Color intensity, brightness per light and the other settings of the scene apply as usual.
- A group that is used as one light sits in the middle of its lights.

## Dynamic scenes

A dynamic scene with the room canvas moves the picture slowly through the room: the colors wander
from one side to the other and come back. Choose the direction with the arrows below the plan
(the arrow in the plan shows it). The picture crosses the room once in ten color changes, so the
interval of the scene sets the speed.

## Music scenes

For a music scene the **album cover** is laid over the room: what is on the left of the cover is on
the left of the room. Main and accent lights keep their own colors and get the one of them that
fits their place.

## Services

`apply_preset`, `start_dynamic_scene` and `save_scene` accept `spatial`:

```yaml
action: scene_studio.start_dynamic_scene
data:
  preset_id: 940fd864-51e1-4761-95d3-75d4d68835ea
  targets:
    area_id: living_room
  interval: 60
  spatial:
    direction: 90   # 0 = to the right, 90 = down on the plan; only used by dynamic scenes
```

Without `spatial` the colors are spread as before.
