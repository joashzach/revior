---
name: "interface-craft"
description: "Use when building, restyling, animating or reviewing any web frontend (pages, apps, dashboards, components) so it looks crafted and distinctive, not AI-generated."
---

# Interface Craft

A design-engineering skill for interfaces that make people ask "how was this made?" rather than "which AI made this?". It combines a clear aesthetic direction, a token system (color, type, space, motion), interaction polish, purposeful scroll and 3D motion, and an explicit anti-slop audit.

Distilled from: Impeccable (anti-patterns, OKLCH color, design vocabulary), make-interfaces-feel-better (micro-detail polish), Transitions.dev (portable semantic CSS transitions), the official GSAP skills (timelines, ScrollTrigger, useGSAP, performance), and award-site patterns (CSS Design Awards / Awwwards: scroll-driven narrative, restrained palettes, mobile-first, accessible).

---

## 0. Workflow (follow in order)

1. **Read context first.**
   - Find the closest `design.md` (walk up from the file being edited: component folder → app folder → repo root). If one exists, it overrides the defaults in this skill. Follow its tokens, fonts, components and voice exactly.
   - Detect the existing styling system (Tailwind, CSS modules, plain CSS, CSS-in-JS) and component library. Express every change in that system. Never add a second styling system for a polish fix.
   - Read the product brief/PRD/contract if present: who uses it, on what device, in what situation (calm desk vs. stressed on a platform).
2. **Choose a direction before writing code.** Write one sentence: *"<Aesthetic name>: <mood>, for <user> on <device>, inspired by <1–2 non-AI references>."* Example: "Transit-signal editorial: calm, high-legibility, for stranded commuters on phones, inspired by railway wayfinding signage and print timetables." Commit to it; every choice below must serve it.
3. **Define tokens** (§2–§5) as CSS custom properties / Tailwind theme before building screens.
4. **Build structure** (§6) with real content, not lorem ipsum.
5. **Design every state** (§7): hover, focus-visible, active, disabled, loading, empty, error, success, offline.
6. **Add motion last** (§8–§10), only where it explains something.
7. **Polish pass** (§11 checklist).
8. **Anti-slop audit** (§1). Fix every hit.
9. **Verify**: view at 360 px and ≥1366 px, keyboard-only pass, `prefers-reduced-motion` on, contrast check, Lighthouse/perf on scroll/3D pages. Report what you checked and what you could not.
10. If no `design.md` existed and you made direction decisions, offer to write one capturing them (tokens, fonts, components, voice) so future work stays consistent.

---

## 1. Anti-AI-slop rules (hard bans unless design.md explicitly asks)

These are the fingerprints of templated AI output. Avoiding them forces deliberate choices.

**Typography**
- No Inter, Roboto, Arial, Open Sans, Helvetica or bare system stack as the brand face. Also avoid the new defaults: Geist, Plus Jakarta Sans, Space Grotesk, Fraunces, Poppins, Montserrat.
- No single-weight pages. Hierarchy needs at least 3 distinct weights/sizes.
- No monospace for "developer vibes". Mono only for code, IDs, tabular data.
- No gradient text on headings or metrics.
- No rounded-square icon tile above every heading.

**Color**
- No purple-to-blue (or violet/indigo/fuchsia) gradient heroes or "AI palette" (indigo-500 + pink-500 + cyan glow).
- No pure `#000` / pure `#fff` / untinted grays. Tint neutrals toward the brand hue.
- No gray text on colored backgrounds. Use a tint of the background hue or the on-color token.
- No default dark mode with neon glow accents as a personality substitute.
- No rainbow of accents. One accent, used sparingly (≈5–10% of pixels).

**Layout**
- No "Cardocalypse": not everything needs a card. Use spacing, type and dividers.
- No cards inside cards.
- No identical 3-up feature grid (icon + heading + two lines) as the default section.
- No centered hero + big glowing number + three stat pills + gradient blob.
- No monotonous spacing (same gap everywhere). Vary rhythm deliberately.
- No glassmorphism/blur/glow borders as decoration. Use blur only for real overlays.
- No emoji as icons in production UI (fine as user content or playful persona labels).

**Motion**
- No bounce/elastic easing on UI (reads dated). No `transition: all`.
- No everything-fades-up-on-scroll. Reveal only what benefits from sequencing.
- No scroll-jacking that fights the user, no parallax on body text.

**Copy**
- No "Unlock the power of…", "Seamless", "Revolutionize", "Elevate", "Effortlessly", "Supercharge", em-dash-heavy marketing filler, or lorem ipsum.
- Buttons say what happens ("Accept seat", "Run allocation"), not "Submit" / "Get started" by default.
- Write like the product's best support person: short, specific, kind.

**Components**
- Never ship unstyled library defaults (stock shadcn/ui look, default Tailwind blue-500, default Recharts colors). Re-theme every component to the tokens.
- Flashy copy-paste effect libraries (spotlight cards, meteors, beams, marquee logos) are allowed at most once per page, only if they serve the direction.

---

## 2. Color system (OKLCH)

- Define colors in `oklch()` so lightness steps are perceptually even; provide a hex fallback only if the project requires it.
- Structure: `--bg`, `--surface`, `--surface-2`, `--border`, `--text`, `--text-muted`, `--accent`, `--accent-contrast`, plus semantic `--success`, `--warning`, `--danger`, `--info`, each with `-bg` (tinted fill) and `-fg` (readable text on it).
- Neutrals: low chroma (0.005–0.02) tinted toward the brand hue. Build a 50→950 ramp with lightness ≈ 0.98, 0.96, 0.92, 0.86, 0.76, 0.62, 0.50, 0.40, 0.30, 0.22, 0.16.
- Accent: one hue, chroma 0.12–0.20 at L 0.55–0.70. Derive hover (L −0.05), pressed (L −0.10), subtle bg (L 0.95, C 0.03).
- Semantic colors carry meaning, not decoration. Never rely on color alone: pair with icon + text ("Cancelled", "Waitlisted #2").
- Contrast: body text ≥ 4.5:1, large text/UI glyphs ≥ 3:1, focus ring ≥ 3:1 against adjacent colors. Verify, don't eyeball.
- Dark mode: not an inversion. Raise surfaces by lightness (elevated = lighter), lower accent chroma ~15%, avoid pure black (use L ≈ 0.16–0.20 tinted).

**Starter palettes (choose one, or derive from brand; all avoid the AI palette)**

| Name | Mood | bg | text | accent | notes |
|---|---|---|---|---|---|
| Signal | wayfinding, civic, calm urgency | `oklch(0.975 0.008 85)` warm paper | `oklch(0.22 0.02 260)` ink navy | `oklch(0.68 0.17 50)` signal orange | great for transit/ops; danger = `oklch(0.58 0.2 27)` |
| Harbor | trustworthy, maritime | `oklch(0.97 0.01 200)` | `oklch(0.24 0.03 220)` | `oklch(0.56 0.10 190)` deep teal | sand secondary `oklch(0.86 0.05 85)` |
| Graphite & Lime | technical, sharp | `oklch(0.18 0.01 250)` | `oklch(0.94 0.01 250)` | `oklch(0.86 0.19 125)` lime | dark-first; use lime only for state/CTA |
| Clay | warm, human, editorial | `oklch(0.96 0.015 60)` | `oklch(0.26 0.02 40)` | `oklch(0.58 0.13 35)` terracotta | pair with a serif display |
| Ink Mono | luxury, restraint | `oklch(0.985 0.002 90)` | `oklch(0.17 0.005 90)` | `oklch(0.17 0.005 90)` (ink as accent) | hierarchy via type & space only |

---

## 3. Typography

- Max 2 families (display + text), plus mono only if data needs it.
- Suggested non-default pairings (check licence; self-host via Fontsource or Fontshare):
  - Grotesk UI: **General Sans / Satoshi** + **Hanken Grotesk** or **Schibsted Grotesk**
  - Editorial: **Instrument Serif / Newsreader** (display) + **Instrument Sans / Onest** (text)
  - Technical: **Bricolage Grotesque** (display) + **IBM Plex Sans** (text) + **IBM Plex Mono** / **JetBrains Mono** (data)
  - Civic/signage: **Atkinson Hyperlegible** or **Public Sans** (text) + a condensed display (**Barlow Condensed**, **Archivo Narrow**)
- Scale: UI apps ratio 1.2–1.25 (e.g. 12, 14, 16, 20, 24, 30, 36); marketing/landing 1.333–1.5 with a dramatic display size (clamp-based fluid: `font-size: clamp(2.5rem, 1.5rem + 4vw, 5.5rem)`).
- Body ≥ 16 px on mobile (inputs exactly ≥ 16 px to avoid iOS zoom). Line-height: body 1.5–1.6, UI labels 1.3, headings 1.05–1.2.
- Large headings: letter-spacing −0.01 to −0.03em. All-caps labels: +0.04 to +0.08em, small size, medium weight.
- Measure: 60–75ch for prose, ≤ 45ch for hero subtitles.
- `text-wrap: balance` on headings/short titles; `text-wrap: pretty` on short–medium body, captions, list items; neither on long prose or code.
- `font-variant-numeric: tabular-nums` on counters, timers, prices, tables, scores, anything that updates.
- Root: `-webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;`.
- Use OpenType features where the font has them (`ss01`, `cv11`, `case`) for character, not default glyphs.
- Load with `font-display: swap`, preload the 1–2 critical weights, subset when possible.

---

## 4. Space, layout & surfaces

- 4 px base scale: 2, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128.
- Rhythm: tight inside groups (4–12), medium between related groups (16–32), generous between sections (64–128). Proximity is the main grouping tool, before borders or cards.
- Grid: 4 cols mobile, 8 tablet, 12 desktop; content max-width ~1200–1280 px; break the grid intentionally once per page (bleed image, offset heading) for character.
- Asymmetry beats perfect centering for marketing pages; dashboards favor strict alignment.
- **Concentric radius:** outer radius = inner radius + padding (card 16 px with 8 px padding → inner 8 px). Where padding is large, treat layers as separate surfaces.
- Radius scale: 4 / 8 / 12 / 16 / 24 / full. Pick a personality (sharp 2–4, soft 8–12, friendly 16+) and stay consistent.
- **Borders vs shadows:** borders for separation, tables and focus rings; layered, low-opacity shadows for elevation (cards on hover, dropdowns, popovers, modals). Example elevation-2: `0 1px 2px oklch(0.2 0.02 260 / 0.06), 0 4px 12px oklch(0.2 0.02 260 / 0.08)`.
- Images: subtle inset outline `outline: 1px solid oklch(0 0 0 / 0.08); outline-offset: -1px;` so edges don't bleed into surfaces.
- Optical alignment: icons in buttons often need 1–2 px nudge; play-triangles shift right; align text baselines, not boxes.
- Hit areas: ≥ 44×44 px on touch, ≥ 40×40 px dense desktop. Extend small visuals with a pseudo-element.
- Responsive: mobile-first; use container queries for components that live in different widths; `dvh` for full-height mobile layouts; respect safe-area insets.

---

## 5. Motion tokens

Define once, reuse everywhere (Transitions.dev style semantic tokens):

```css
:root {
  --dur-instant: 80ms;   /* press feedback */
  --dur-fast: 150ms;     /* hover, exits, icon swaps */
  --dur-base: 220ms;     /* dropdowns, toggles */
  --dur-slow: 320ms;     /* modals, panels, enters */
  --dur-page: 480ms;     /* route/page transitions */
  --ease-out: cubic-bezier(0.22, 1, 0.36, 1);      /* enters */
  --ease-in: cubic-bezier(0.55, 0, 1, 0.45);       /* exits */
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);   /* moves on screen */
  --ease-emph: cubic-bezier(0.2, 0, 0, 1);         /* emphasized decel */
}
@media (prefers-reduced-motion: reduce) {
  :root { --dur-fast: 0ms; --dur-base: 0ms; --dur-slow: 0ms; --dur-page: 0ms; }
}
```
- Springs (Motion/GSAP) for direct-manipulation and interruptible UI: e.g. `{ type: "spring", stiffness: 400, damping: 32 }` (no visible overshoot), never wobbly.

---

## 6. Structure & composition

- Every screen has one primary action and an obvious reading order. Squint test: the most important thing is the darkest/largest.
- Hierarchy via size, weight, color and space, not via boxes.
- Use real, specific content and data shapes (long names, zero states, 3-digit numbers, RTL if relevant).
- Landing pages: a point of view in the first viewport (specific headline, product shown, one CTA), then a narrative (problem → how it works → proof → CTA). Show the product, not abstract blobs.
- Dashboards: KPIs first, then the main visual (map/chart/table), then controls; align to a strict grid; density over decoration.

---

## 7. States & interaction

- Every interactive element: default, hover (pointer devices only, `@media (hover: hover)`), `:focus-visible` (2 px ring in accent with 2 px offset, never removed), active/pressed, disabled (reduced contrast + `cursor: not-allowed` + reason in tooltip), loading.
- Press feedback: `transform: scale(0.96)` on buttons (never below 0.95), `--dur-instant`.
- Loading: skeletons that match final layout for > 300 ms waits; spinners only inside buttons/small areas; optimistic UI where safe; never block the whole screen without a reason.
- Empty states: say what this is, why it's empty, and the next action.
- Errors: inline, next to the cause, say how to fix; shake input once (Transitions.dev "error shake") then return to neutral; never only red color.
- Success: brief confirmation (check draw-in), then get out of the way.
- Forms: labels always visible (no placeholder-as-label), correct `type`/`inputmode`/`autocomplete`, validate on blur, submit on Enter.
- Toasts for async events; dialogs only for decisions that need focus. Trap focus in modals, restore focus on close, Esc closes.
- Real-time UIs: animate changes gently (count transitions, flash a row once at low opacity), never reflow the layout under the user's finger; use tabular numbers; show connection status.

---

## 8. Micro-interaction & transition patterns

- **Prefer CSS transitions for interactive elements** (they are interruptible). Reserve keyframes for one-shot sequences (loaders, success check).
- Always list properties: `transition-property: transform, opacity, background-color, box-shadow;` never `all`. Animate only `transform` and `opacity` (and `filter` sparingly).
- **Enter:** opacity 0→1 + translateY 8→0 px (+ optional blur 4→0 px), `--dur-slow`, `--ease-out`. Split content and stagger children 30–60 ms (max ~6 items, cap total at ~300 ms).
- **Exit:** shorter and quieter: ~150 ms, opacity + 4 px move, `--ease-in`.
- **Icon swap:** cross-fade with scale 0.25→1, opacity 0→1, blur 4px→0.
- **Dropdown/menu:** origin-aware scale from 0.96 + opacity, `transform-origin` at the trigger.
- **Modal:** backdrop fade + panel scale 0.96→1 and opacity; exit faster.
- **Panel/sheet:** translate from its edge; mobile bottom sheets follow the finger (drag) with spring settle.
- **Number change:** digit pop-in (each digit translateY + blur, slight stagger) with tabular nums.
- **Text state swap** ("Send" → "Sent"): blur-crossfade, keep width stable.
- **Card resize/layout change:** animate with FLIP (Motion `layout`, GSAP Flip, or View Transitions API).
- **Page transitions:** View Transitions API (`document.startViewTransition`) with a fallback; directional slide for forward/back.
- In React with AnimatePresence, set `initial={false}` so nothing animates on first page load unless intended.
- `will-change: transform` only during animation, only on the animating element.
- Review motion at 10% speed in DevTools Animations panel; it should look intentional frame by frame.

---

## 9. Scroll animation (award-grade, but disciplined)

Use scroll motion to tell a story (progress, reveal, compare, transform), not to decorate.

**Toolkit choice**
- Simple reveals/progress: **native CSS scroll-driven animations** (`animation-timeline: view()` / `scroll()`), wrapped in `@supports (animation-timeline: view())` with a static fallback.
- Sequenced, pinned, scrubbed narratives: **GSAP + ScrollTrigger**.
- Smooth scrolling: **Lenis** only on marketing/storytelling pages, never in dense apps/dashboards or forms; sync it with ScrollTrigger (`lenis.on('scroll', ScrollTrigger.update)`, drive Lenis from `gsap.ticker`).

**GSAP rules (from the official GSAP skills)**
- Register plugins once: `gsap.registerPlugin(ScrollTrigger, useGSAP)`.
- Sequence with timelines, not chained delays; set shared values via `defaults`; use position offsets (`"<"`, `"-=0.2"`, labels).
- Prefer transform aliases (`x`, `y`, `scale`, `rotate`) and `autoAlpha` over raw `opacity`/`left/top`.
- Attach ScrollTrigger to a timeline or top-level tween, not to nested children.
- `ScrollTrigger.refresh()` after layout/content/image/font changes; `invalidateOnRefresh: true` for responsive values.
- React: `useGSAP(() => {...}, { scope: containerRef })`; never unscoped selectors; cleanup is automatic (else `gsap.context()` + `ctx.revert()`).
- Responsive & accessible: `gsap.matchMedia()` with `"(prefers-reduced-motion: no-preference)"` and breakpoints; reduced motion = no pin/scrub, content simply visible.
- Performance: animate transforms/opacity only, batch reveals with `ScrollTrigger.batch`, avoid animating `filter: blur` on large areas, test on a mid-range phone.

**Patterns that win (CSSDA/Awwwards-style)**
- Pinned section where a product/diagram transforms step by step as copy scrolls beside it (scrub 0.5–1).
- Horizontal scroll gallery inside a pinned section (desktop only; vertical list on mobile).
- Kinetic headline: SplitText words/lines rise with mask + stagger once, not on every scroll.
- Scroll progress driving a number, map route or timeline line drawing (`drawSVG`/stroke-dashoffset).
- Sticky stacked cards that scale down slightly as the next one arrives.
- Section color transitions (background tint shifts between chapters).

**Never:** hide essential content behind scroll animation, block scroll, or pin for more than ~2 viewport heights without clear progress feedback.

---

## 10. 3D & WebGL

- Use only when 3D explains (product, spatial data, network) or carries the brand moment. One hero 3D moment per page maximum.
- Stack: **React Three Fiber + drei** (React) or **Three.js**; GLTF/GLB models compressed (Draco/Meshopt), textures KTX2/WebP; **Spline** for quick designer-made scenes (export, lazy-load).
- Performance budget: clamp DPR `dpr={[1, 2]}`, `frameloop="demand"` when static, pause when offscreen (IntersectionObserver), limit lights/shadows, use baked lighting, `<PerformanceMonitor>` to degrade, keep JS for the scene lazy-loaded below the fold or after first paint.
- Scroll-linked 3D: drive camera/object via ScrollTrigger progress or drei `ScrollControls`; ease with damping (`maath/easing.damp`), never raw 1:1 jumps.
- Always ship a static poster image fallback (no WebGL, low-power mode, reduced motion) with the same composition.
- Materials: restrained, physically plausible (matte, subtle roughness), lit to match the palette; avoid chrome-and-neon "AI render" look.
- CSS 3D (perspective + rotateX/Y on cards, tilt on hover ≤ 6°) is enough for most "depth" needs.

---

## 11. React library guidance

| Need | Prefer | Notes |
|---|---|---|
| Accessible primitives | Radix UI / React Aria; shadcn/ui as a starting point | Re-theme fully to tokens; delete unused variants |
| Animation (UI) | Motion (`motion/react`) | `layout`, `AnimatePresence initial={false}`, springs for gestures |
| Animation (timelines/scroll) | GSAP + `@gsap/react` | Follow §9 rules |
| Smooth scroll | Lenis | Marketing pages only |
| 3D | @react-three/fiber, @react-three/drei | Follow §10 budget |
| Charts | visx or Recharts (re-themed), or Observable Plot | Tokens for series colors, tabular axis labels, no default palettes |
| Maps | react-leaflet / MapLibre with a muted custom tile style | Brand-tinted, low-chroma base map so data pops |
| Toasts / drawers / command | sonner, vaul, cmdk | Style to tokens |
| Icons | one set only (Lucide, Phosphor, or Tabler) | Stroke 1.5 px with 400-weight text, 2 px with 600; `currentColor`; same size grid (16/20/24) |
| Forms | react-hook-form + zod | Inline errors per §7 |

---

## 12. Context-specific guidance

**Mobile-first apps used under stress (transit, health, emergencies)**
- One decision per screen, thumb-reachable primary action (bottom), large status headline in plain words ("Your train is cancelled"), countdown timers with tabular nums and color + text at thresholds, haptic/vibration on critical changes where allowed.
- Status semantics: success = placed/confirmed, warning = held/waitlisted/delayed, danger = cancelled/expired/unresolved, info = neutral updates. Same mapping everywhere (pills, map, toasts).
- Explainability panels ("Why this?"): breakdown bars with points, one-sentence explanation, no jargon.

**Operational dashboards on projectors/large screens**
- Readable from 4 m: KPI numerals ≥ 32 px, labels ≥ 14 px, high contrast, avoid thin weights and low-chroma text on mid-tone backgrounds.
- Live data: animate value changes subtly (number roll, single row flash), never re-sort rows under the cursor without a visible cue; capacity bars must visually cap at 100%.
- Map layers with clear semantic styling (closed = thick danger line, re-routed = accent/success line, moving markers with eased interpolation).
- QR or join panels: high-contrast, quiet zone ≥ 4 modules, large enough to scan from the audience.

**Landing pages**
- Headline states the specific outcome; show the real product UI early; one CTA style; proof (numbers, demo) over adjectives; one scroll-driven narrative section max.

---

## 13. Polish checklist (run before delivering)

- [ ] Direction sentence written; every token traces back to it; design.md followed if present
- [ ] No §1 anti-pattern present (fonts, palette, cards-in-cards, gradient text, slop copy, default library look)
- [ ] OKLCH tokens; tinted neutrals; contrast verified (4.5:1 text, 3:1 UI)
- [ ] ≤ 2 type families, clear scale, `text-wrap` set, tabular nums on changing numbers, font smoothing at root
- [ ] Spacing rhythm varies by level; grid alignment consistent; concentric radii
- [ ] Shadows layered and subtle; borders only where separation is needed; image outlines
- [ ] All states designed: hover, focus-visible, active, disabled, loading, empty, error, success, offline
- [ ] Hit areas ≥ 44 px touch / 40 px desktop; keyboard path complete; focus trapped/restored in dialogs
- [ ] Motion uses tokens; no `transition: all`; enters staggered, exits quieter; press scale 0.96; `AnimatePresence initial={false}`
- [ ] Scroll/3D: purposeful, reduced-motion fallback, poster fallback, refresh on layout change, 60 fps on mid phone
- [ ] Responsive at 360, 768, 1366, 1920; safe areas; inputs ≥ 16 px on mobile
- [ ] Copy specific, verbs on buttons, no filler words
- [ ] Report: what changed (before → after, with file paths), what was verified, what was not verified

---

## 14. Review mode

When asked to review or "make it feel better":
1. Scope: list screens/components reviewed; never imply unchecked areas were reviewed.
2. Findings table: `Severity (HIGH/MEDIUM/LOW) | Location (file:line) | Before | After | Why`. HIGH = accessibility failure, broken state, slop tell on a primary screen, jank; MEDIUM = inconsistency, missing state, weak hierarchy; LOW = micro-polish.
3. Apply fixes in the existing styling system.
4. Verdict: Block (any HIGH), Needs changes (MEDIUM/LOW only), Approve (nothing actionable). Don't pad findings.