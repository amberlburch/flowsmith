# FLOWSMITH error taxonomy

Every ledger entry carries exactly one category and at least one gate. The category makes failure patterns countable. The gate decides which entries the ritual pulls for a given task, so the ledger stays readable as it grows past 100 rules.

Recurrence within a category is the trigger to strengthen the process, not to add a parallel rule. Two entries in the same category means the existing guardrail was too weak: rewrite it harder and move its gate earlier.

## Categories

| Tag | Covers | Default gate | Standard source |
|---|---|---|---|
| `STRUCT` | Structure, nesting, semantics, wrong tag, heading order, unjustified wrappers, coupled references across code surfaces | BUILD | `dod.md` §2 |
| `NAME` | Naming-system violations, duplicate classes, leftover auto-generated names, combo-class soup, style-name collisions | BUILD | `dod.md` §2, `webflow-design-system/references/naming.md` |
| `RESP` | Responsive and breakpoint failures, units, overflow, cascade direction, full-range gaps between breakpoints | CRITIQUE | `dod.md` §9 |
| `FID` | Design-fidelity gaps: spacing, type, colour, radius, shadow, wrong token, orphan and widow lines, brief defeated by a technically-passing choice | CRITIQUE | `dod.md` §2, §4b |
| `STATE` | Missing or wrong interactive states: default, hover, focus, active, disabled, loading, empty | CRITIQUE | `dod.md` §2 |
| `MOTION` | Easing, duration, trigger, jank, reduced-motion, lifecycle leaks, editor guard, clipped glyphs at rest | BUILD, CRITIQUE | `dod.md` §5 |
| `A11Y` | Contrast, alt text, keyboard operability, focus visibility, landmarks, labels, tap targets | CRITIQUE | `dod.md` §8 |
| `PERF` | Asset weight and resolution, DOM weight, unused code, Lighthouse budget | CRITIQUE | `dod.md` §6 |
| `SEO` | Meta contract, schema, canonicals, indexability, internal linking, leftover schema from a prior stack | CRITIQUE | `dod.md` §7 |
| `CMS` | Collection and field structure, bindings, template resolution, empty-state handling, editor safety | BUILD, RITUAL | `dod.md` §3 |
| `API` | Silent Data-API write failures: a call returns success and writes nothing, or writes to the wrong object | BUILD | `SYSTEM.md` golden rule |
| `LIVE` | Staged-not-live, publish discipline, cooldown handling, publish-lock contention, site-wide publish blast radius | CRITIQUE | `SYSTEM.md` publishing section, `dod.md` §11 |
| `PROC` | Skipped a check, did not confirm scope, did not read the ledger, silent decision, guessed instead of asking | RITUAL | `SYSTEM.md` operator moments |
| `COMM` | Unclear handoff, undocumented decision, unflagged assumption, a claim without evidence | RITUAL | this skill's handoff format |
| `OMIT` | Designed content with no build counterpart: a missing section, frame, photo, breakpoint variant or state. The failure mode where the thing you would check does not exist to be checked | BUILD, CRITIQUE | dod.md §2 completeness gate, §3 |

`API` and `LIVE` are FLOWSMITH-specific and carry most of the existing ledger. They are the two dominant real-world failure classes: a Webflow write that reports success while doing nothing, and work reported done while it is still staged. A generic web-development taxonomy has no bucket for either, which is why they are here.

## Gates

| Gate | When it fires | Pulls categories |
|---|---|---|
| `RITUAL` | Start of task, before any element or class is created | `PROC`, `COMM`, `CMS` |
| `BUILD` | During the build, at the moment the trap can be hit | `STRUCT`, `NAME`, `API`, `MOTION`, `CMS` |
| `CRITIQUE` | Pre-handoff red-team, against the published page | `RESP`, `FID`, `STATE`, `A11Y`, `PERF`, `SEO`, `MOTION`, `LIVE` |

An entry may name more than one gate (`fires:BUILD,CRITIQUE`) when the trap is created during the build but only detectable against published output.

## Ledger tag format

Existing rules keep their original generic category. The taxonomy tag is added immediately after it, in pipe form:

```
27. [TOOL] [API|BUILD] whtml_builder silently drops class-to-element attachment ... [promote] (2026-07-17)
```

New entries use the five-field L-format defined in `SKILL.md`, with the taxonomy tag in the heading:

```
### L-041: Measure spacing against the token, never by eye   [FID|CRITIQUE]
```

## Choosing a category

Ask what would have caught it, not what it looked like. A blurry image is `PERF` if the cause was a low-resolution source, `FID` if the cause was the wrong asset. A broken animation is `MOTION` if the easing was wrong, `STRUCT` if a copy edit broke a hardcoded selector. When two categories fit equally, pick the one whose gate fires earliest: catching it sooner is worth more than filing it neatly.

`OMIT` is deliberately its own category rather than a flavour of `STRUCT` or `FID`: every other category is a property test on an artifact that exists, while `OMIT`'s check is a set difference against a design-side inventory. If the honest answer to "what would have caught it" is "nothing existed to catch it", it is `OMIT`, and the recurrence counter for the class must fire under that name.
