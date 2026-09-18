# Brag Plan: Madroño

## What is this app?
Madroño is a Madrid urban-intelligence platform for a Master's thesis (TFM): it ingests 24 real open-data sources into an AWS lakehouse, trains ML models (LightGBM + a graph neural net) on a 1798-node Neo4j urban graph, and exposes it all as a conversational assistant — 19 MCP tools — with a public animated map that plays the city's traffic and air quality hour by hour.

## The angle
This isn't a toy demo — it's real Madrid open data (traffic sensors, air quality stations, noise, weather, transit) turned into something you can *watch move*. The angle: treat the animated map like the trailer for a living system, then prove it's not just a pretty map by showing the assistant answer a real question live, tool trace and all. Academic rigor rendered as something worth watching.

## Hook (first 2-3 seconds)
Black canvas. A faint radial glow over Madrid's outline. Then the graph snaps alive — hundreds of nodes lighting up in a wave across the city — as the wordmark "Madroño" (the crimson mark) settles center, tagline beneath: "Inteligencia urbana de Madrid."

## Key moments (the middle)
- The guided tour in motion: the map cycles a chapter, nodes recoloring hour by hour (the actual `viz/mapa` UI — title bar, chapter rail, legend — glimpsed, not just the canvas).
- The Sol → Atocha route moment: two routes drawn over the map, the clean one in green, the shortest in gray, with the real stat "−27% de exposición" landing as the routes settle.
- The assistant, live: a chat bubble asks "¿Cómo está el tráfico cerca de Atocha ahora?", the bot's reply types in, and the tool trace chip appears beneath it — a real, small piece of proof this isn't scripted marketing copy.

## Outro / punchline
Hold on the wordmark again, now with the payoff line: "19 herramientas. 24 fuentes abiertas. Un asistente que conoce Madrid." Fade to the dark map canvas, still breathing faintly.

## User flow worth showing
Entry: open the animated map, guided tour chapter running (nodes recoloring hour by hour).
Key action: jump to the clean-route chapter (Sol → Atocha) — the map redraws two routes live.
Result: cut to the chat assistant answering a real traffic question with a visible tool-call trace, proving the same backend drives both surfaces.

## Tone
- Preset: cinematic
- Creative direction: a city's data made visible — restrained, dark, dramatic wide shots of the map itself as the hero, not a chirpy product-launch energy. Real numbers, no hype language.
- Interpretation: wide, held shots on the map canvas; big confident type for stats; dramatic crossfades rather than hard cuts; music swells under the reveal and the route moment, pulls back under the chat scene so the typed reply stays legible.

## Format: landscape — 1920x1080
## Duration: 23s

## Visual identity (from the project)
- Background: `#0b1220` (map canvas navy) — deep radial gradient to `#070a0e`
- Accent (data/motion): `#3d6ce0` (map UI blue); diverging legend `#d7191c → #fdae61 → #ffffbf → #a6d96a → #1a9641` (red→green) for the animated data itself
- Brand accent (mark, wordmark, outro payoff only): crimson `#C81E3A` → `#96162C` gradient, gold `#E8A23C`
- Text: `#e8edf2` (map UI light text) on dark; `#9fb0c0` for secondary/muted lines
- Display font: Sora (600/700/800) — wordmark and headline type
- Body font: Plus Jakarta Sans — chat bubbles, small labels, stat captions
- Strongest visual element: the animated deck.gl map itself — 1798 glowing nodes recoloring across Madrid in the dark canvas; secondary: the Madroño mark (three interlocking circles, the madroño tree/bear from Madrid's own coat of arms)

## Share copy (draft)
Le pregunté a mi TFM cómo iba a estar el tráfico en Madrid dentro de 3 horas — y me contestó cruzando 19 herramientas sobre datos 100% abiertos.

## Audio direction
- Role: cinematic support — a steady bed that swells under the two visual reveals and recedes under the typed chat exchange so the copy stays readable
- Music: `happy-beats-business-moves-vol-12-by-ende-dot-app.mp3` (steady/clean, tagged best-for cinematic & polished; 109.96 BPM)
- Music treatment: starts at 0 under the hook at low-medium volume (~0.3), swells slightly into the map-reveal and route moments, dips under the chat scene (~0.22) so typed text and the reply read clearly, rises again for the outro payoff
- Music cue guidance: preset read from `happy-beats-business-moves-vol-12-by-ende-dot-app.music-cues.json`. Target strong cues — 2.73s/3.27s (hook settle), 8.74s (map-reveal landing), 13.11s (route stat landing), 17.47s/18.56s (chat trace landing), 22.93s/24.56s (outro lockup). Sequential map-node recolor pulses in Scene 2 may loosely track the 3.82–8.19s beat-grid window; do not force strict per-node sync.
- Audio-reactive treatment: subtle — the map's ambient glow / node-highlight brightness may breathe gently with RMS during Scenes 2–3; no waveform or equalizer graphics; nothing that competes with map legibility
- SFX posture: 2-3 restrained cues, cinematic family (`impactBell_heavy_*` for the hook settle and outro lockup, `impactSoft_medium_*` for the route-stat landing). No SFX during the chat scene beyond a soft keypress/typing texture — let the reply read.
- Audio-coupled moments: the chat reply typing in character-by-character (soft keypress texture, low volume, thinned out — not one hit per letter); the two routes drawing onto the map (a single soft draw/whoosh-adjacent cue at landing, not per-segment)
- Restraint rule: no dense per-node stingers during the map animation — the node wave is a visual wash, not a sequence of discrete items to score individually; never let SFX outcompete the chat copy

## Storyboard

### Scene 1 — Hook — 3s
Black canvas → faint radial glow over a suggestion of Madrid's node field. At ~1.2s the graph snaps alive: a wave of nodes lighting up outward from center (recreate the deck.gl node field, not a generic particle effect). At ~2s the Madroño mark (crimson circles) and wordmark "Madroño" settle center, tagline "Inteligencia urbana de Madrid" fades in beneath.
Sequential/interaction: yes — the node wave lights up outward in one continuous sweep, not discrete pops.
Audio intent: hushed anticipation building to a settle, not an explosion.
Audio-coupled idea: node-wave sweep loosely tracks the rising beat-grid into the 2.73s cue; wordmark settle lands on/near 2.73-3.27s.
Music: cinematic bed, low-medium, fading in from 0.
Transition mood: dramatic wipe → Scene 2

### Scene 2 — The map alive — 5.7s (3.0-8.7s)
Cut to the real `viz/mapa` UI: title bar ("Madrid, hora a hora"), chapter rail, legend visible at the edges, canvas dominant. The guided-tour chapter 1 plays — nodes recoloring across the red→green diverging scale as the hour advances. Overlay text, large: "1798 nodos. Hora a hora." then thins to a smaller caption as the map keeps breathing.
Sequential/interaction: yes — simulate stepping the guided tour forward (chapter rail highlight moves), nodes recolor in a continuous wave keyed to the hour slider advancing.
Audio intent: the bed opens up, confident momentum.
Audio-coupled idea: node-recolor wave loosely tracks the 3.82-8.19s beat-grid window; do not sync per-node.
Music: swelling into the 8.74s strong cue.
Transition mood: soft crossfade → Scene 3

### Scene 3 — The clean route — 4.4s (8.7-13.1s)
Push in on a section of the map: Sol and Atocha marked, two routes draw onto the canvas — gray (shortest) first, then green (clean) tracing a slightly different path. Stat text lands large as the green route completes: "−27% de exposición al aire." Small caption beneath: "Sol → Atocha, misma hora."
Sequential/interaction: yes — gray route draws first, green route draws second and holds; stat text lands after both are visible.
Audio intent: a small triumphant landing, not bombastic.
Audio-coupled idea: single draw-in cue on the green route's completion, timed to land on/near 13.11s.
Music: strong cue landing at 13.11s.
Transition mood: dramatic wipe → Scene 4

### Scene 4 — The assistant answers — 4.4s (13.1-17.5s)
Cut to the real chat UI (`web/index.html` styling: warm crimson/gold, Sora/Plus Jakarta Sans) — but staged as a focused close-up, not the full login chrome. A user bubble types in: "¿Cómo está el tráfico cerca de Atocha ahora?" A pending state ("Consultando los datos reales de Madrid…") gives way to the bot's reply typing in, then a small trace chip unfolds beneath: "🔧 trafico_cercano · ok · 240 ms."
Sequential/interaction: yes — user message appears, pending state briefly shown, bot reply types in character-by-character, trace chip unfolds last.
Audio intent: pull back, let this feel real and quiet — the proof beat, not the spectacle beat.
Audio-coupled idea: soft, thinned keypress texture under the typed reply; a small unfold/click cue when the trace chip appears, aimed at the 17.47-18.56s cue window.
Music: dips under this scene (~0.22) then begins rising again toward the end.
Transition mood: clean crossfade → Scene 5

### Scene 5 — Outro / lockup — 5.5s (17.5-23.0s)
Pull back out to the dark map canvas, now quiet and mostly still (a few nodes gently pulsing). The Madroño mark and wordmark return center. Payoff line types/settles in: "19 herramientas. 24 fuentes abiertas. Un asistente que conoce Madrid." Final beat: the share line or a simple close, held.
Sequential/interaction: none — one clean settle, no staggered list.
Audio intent: confident close, warm not triumphant.
Audio-coupled idea: single bell-style cue on the wordmark's return, aimed at 22.93s; a second soft accent at 24.56s for the final line settle.
Music: rises back to hook-level volume, resolves/fades by scene end.
Transition mood: soft fade to hold.

**Music mood for this video:** cinematic
**Audio summary:** A steady, restrained cinematic bed opens hushed under the hook, swells through the map-reveal and route-stat landings, pulls back to let the assistant's real typed reply breathe, then rises once more for the wordmark's return — three light SFX accents (hook settle, route landing, outro lockup) plus a thinned typing texture under the chat scene, nothing denser.
