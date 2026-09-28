# Design anti-patterns

Cross-system catalogue of visual anti-patterns. Cited by `/page-qa` and `/agent-review`. Mirrors and extends the impeccable `frontend-design` skill's reference layer.

When generating any visual output, an agent must avoid every item below by default. Exceptions require an explicit Do's-and-Don'ts override in the active DESIGN.md.

## Authored effect versus decorative default

Every ban below is a ban on a **default treatment**: a surface reached for because it fills space, because it is fashionable, or because nothing else was decided. It is not a ban on the technique existing.

An **authored effect** is a different object, and it is allowed. It qualifies only when all four hold:

1. It traces to a stated purpose in the approved design direction, written before the build.
2. It is applied to specific, named content, never as a page-wide surface treatment.
3. It carries a named experience tier and meets that tier's budget (`agents/flowsmith/dod.md` §5).
4. It degrades to a complete, designed state when it cannot run.

A fluted-glass shader panel behind a single portrait, chosen at design direction, is an authored effect. Frosted blur on every card is glassmorphism and stays banned. A dithered treatment of one hero photograph is an authored effect. A grain overlay dropped on the whole page is the film-grain ban, unchanged.

The test is whether a reader could state the reason. If the only answer is "it looked better", it is decorative, and the ban applies.

## Type

- **Inter as default body font.** Inter is the AI default. Use Geist, GT America, Söhne, or a brand-specified family. Inter Display is a permitted accent face in restrained quantities.
- **System default sans-serif.** Specify a family. Never ship `font-family: sans-serif` to production.
- **Three or more font families on one surface.** Two is the ceiling. One is preferred.
- **Light font weights below 400 at body sizes.** Light weights work only at display sizes 48px+.
- **Centred body copy beyond two lines.** Left-align prose. Centre is for headlines or short calls.
- **All-caps body text.** Caps work for caption-style labels, eyebrows, and short button labels only.

## Colour

- **Pure black (#000) backgrounds.** Use a warm or cool near-black with hex like #0E0D0B, #0B0E14, or #14110D.
- **Pure white (#FFF) text on dark surfaces.** Use a warm off-white. Pure white over-fatigues the eye.
- **Purple-to-pink gradients.** The AI signature gradient. Banned.
- **Teal-to-pink, orange-to-magenta, any neon gradient.** Same family of anti-pattern.
- **Gradient as primary surface treatment.** Surfaces are flat. Gradients appear, if at all, as 1-2% texture overlays.
- **Grey text on coloured backgrounds.** Text and background must share a colour family. Use a desaturated version of the background hue.
- **Bright neon status colours.** Success-green-on-green, danger-red, warning-yellow. Use desaturated, cinematic equivalents.
- **More than one accent colour.** A brand has one accent. Multiple accents read as "designed by a committee."

## Layout

- **Three-column feature grid.** The most reliable signal of AI-generated marketing copy.
- **Bento grid.** Specific exception only. Default is no.
- **Card-on-card stacking.** A card inside a card is a smell. Use spacing or surface shift.
- **Hero with three CTAs.** One primary action per surface. Maximum.
- **Above-the-fold density.** A hero with logo + headline + subhead + 3 CTAs + video + social proof is a panic attack, not a layout.
- **Filling the screen.** Vertical breathing room is part of the voice. Empty space is intentional.
- **Identical card row repeated as "features."** Three identical rectangles with an icon, a heading, and a paragraph. The visual signature of AI marketing slop.
- **Centred column with no anchor.** Long-form content centred in a wide viewport reads as drift. Anchor to a measurable column (56-68ch).

## Motion

- **Bounce, elastic, back-easing.** Reads as 2014. Use standard or cinematic ease curves.
- **Scroll-jacking.** Scroll-bound animation that prevents the user from scrolling at their own pace.
- **Auto-playing video with sound.** Always muted by default. Always pauseable.
- **Decorative motion.** Motion fills silence; silence is not a problem.
- **Animations without `prefers-reduced-motion` fallback.** Mandatory, not optional.
- **Spring physics on small interactive elements.** Buttons do not bounce.

## Imagery

- **Stock photography with people pretending to laugh.** Disqualifying.
- **Generic abstract illustration.** Blob shapes, isometric people, the SaaS hero style.
- **Film grain overlay as a default treatment.** Specifically banned per `feedback_no_film_grain_overlay.md`.
- **Photo grid as primary visual treatment.** Single hero crops dominate over grid walls.
- **AI-rendered humans without a stated reason.** Soul ID is for identity work; generic AI humans on landing pages are a smell.

## Components

- **Glassmorphism.** Frosted blur on overlays. Visual fashion that aged poorly.
- **Neumorphism.** Same family.
- **Drop shadows on buttons.** Buttons are flat or border-only.
- **Heavy borders on cards.** Use 1px subtle borders or no border. Borders should not separate content; spacing should.
- **Large rounded corners on primary surfaces.** Most brands want 2-4px. Pills are for chips only.
- **Skeumorphic icons.** Outline icons at 1.5-2px stroke width. No 3D, no gradient fills, no isometric.

## Voice

- **"I hope this helps."** Removed from all output.
- **"Let me know if you have any questions."** Removed.
- **Em-dashes.** Per user voice rules. Use commas, sentences, or full stops.
- **"Just"**, **"simply"**, **"actually"**, **"basically"**. Crutch words. Remove.
- **Marketing intensifiers without proof.** "Revolutionary," "game-changing," "best-in-class," "world-class." Proof or silence.
- **Empty-state apology copy.** "Oops! Nothing here yet 🎉" Empty states are quiet and editorial.
- **Emoji as decoration.** Emoji is content (the meeting recap uses ✅) or it does not appear.

## Surface

- **Light mode default for a brand that has stated dark cinematic.** Dark is the rule; light is the documented exception.
- **SaaS template feel.** Three columns, big headline, big CTA, social proof bar, three feature cards, FAQ. The shape of generic.

## When to override

An anti-pattern can be intentionally used if the active DESIGN.md explicitly permits it in its Do's section, OR if a brief documents a specific stylistic decision with a one-line rationale. The default is the anti-pattern is banned.
