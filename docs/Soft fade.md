# Soft fade

Some lights fade on and off nicely but **jump** to a new color, whatever transition they get. With
soft fade, Scene Studio does the fade for them: it sends the color in small steps over the transition
time. The steps go around the color wheel at even brightness, so red to blue passes through magenta
instead of a dark, muddy middle.

It will not be as smooth as a light that fades by itself (e.g. Philips Hue), but the jump is gone –
most of all in dynamic scenes and time of day scenes, where the colors change slowly.

## Setting it up

1. In the panel, the **Soft fade** symbol at the top right opens the list of your color lights.
2. Turn on the switch for every light that jumps. Lights that report no transition of their own are
   listed first, but many lights that do report one still jump to a new color – a look at the lamp
   tells. Try a dynamic scene with a long transition and watch it.
3. Choose how many steps it gets:

| Level | Steps per second | For |
|---|---|---|
| Coarse | 1 | lights in the cloud, many lights, a busy Zigbee network |
| Normal | 2 | the default |
| Fine | 4 | lights in the local network, a few lights |

The setting belongs to the light and is used by every scene: presets, saved scenes, dynamic scenes,
music scenes and time of day scenes. In the list of lights of a scene, faded lights are marked
**soft fade**. The list needs an administrator.

## How it works

- Only when a light is **on** and its color or brightness changes. A light that is off fades on by
  itself and gets its color at once, as before.
- Transitions under one second are sent as before.
- A small change gets fewer steps; the level is the upper limit.
- The last step is the exact color of the preset.
- **Any other command** to the light ends a running fade at once: another scene, a light switch, an
  app, an automation. A light that is turned off during a fade stays off.
- Light groups are not listed: their lights are faded one by one. A group in "as one light" gets one
  command as before.
- Gradient lamps get their gradient as before.

Every step is a command to the light. A dynamic scene with a 45 second transition sends about 90
commands per light and change at **Normal**. If lights lag or the network gets slow, choose
**Coarse**.
