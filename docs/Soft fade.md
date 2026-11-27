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
3. Choose with the slider how many **steps per second** it gets, from 1 to 20 (default 2). More steps
   look smoother but send more commands: start low for lights in the cloud, many lights or a busy
   Zigbee network, and go higher for a few lights in the local network.
4. **Smoothness** at the top is one setting for all lights: how fine a single step may be.

| Smoothness | Largest step | |
|---|---|---|
| Fine | 1° of hue (1 % saturation) | most steps, needs a long transition or many steps per second |
| Normal | 2° of hue (2 % saturation) | the default |
| Coarse | 5° of hue (5 % saturation) | fewer, larger steps |

The setting belongs to the light and is used by every scene: presets, saved scenes, dynamic scenes,
music scenes and time of day scenes. In the list of lights of a scene, faded lights are marked
**soft fade**. The list needs an administrator.

## How it works

- Only when a light is **on** and its color or brightness changes. A light that is off fades on by
  itself and gets its color at once, as before.
- Transitions under one second are sent as before.
- The number of steps is the transition time × steps per second, but never more than the change
  needs at the chosen smoothness: a small change gets just a few steps.
- The steps start and end gently: smaller at the beginning and the end, larger in the middle, where
  the eye notices them least.
- The last step is the exact color of the preset.
- **Any other command** to the light ends a running fade at once: another scene, a light switch, an
  app, an automation. A light that is turned off during a fade stays off.
- Light groups are not listed: their lights are faded one by one. A group in "as one light" gets one
  command as before.
- Gradient lamps get their gradient as before.

## How long should the transition be?

Blue to red goes the short way around the color wheel (through magenta), 120° of hue. At **Normal**
smoothness that is about 95 steps, at **Fine** about 190. With 2 steps per second a smooth fade takes
about 45 seconds, with 10 steps per second about 10 seconds. Shorter transitions still fade, just in
larger steps. Dynamic scenes (45 seconds by default) are ideal; a one-time scene gets its transition
in the scene editor under **More options**.

Every step is a command to the light. If lights lag or the network gets slow, use fewer steps per
second.

Up to 3.9 there were three levels (coarse, normal, fine); they became 1, 2 and 4 steps per second.
