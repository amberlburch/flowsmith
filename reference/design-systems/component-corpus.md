# Component corpus (21st.dev bookmark lists)

Whole-site references (full pages, local captures, principle extraction for from-scratch builds) live in `site-corpus/`; this file stays component-level.

The curated, judgement-bearing layer on top of raw catalog search. Taste lives in references, not rules: the corpus is where a vetted reference stops being a search result and becomes an asset.

## Where it lives

21st.dev bookmark lists on the account (read via `mcp__21st__list_bookmark_lists` / `get_bookmark_list`):

| List | id | Scope |
|---|---|---|
| Corient approved: pricing sections | `ba461366-b5fe-480b-abe4-f59826796123` | Pricing surfaces |
| Corient approved: hero sections | `20c826f3-20f0-4fc4-963c-2585412f2a4f` | Hero surfaces |

New surfaces get a new list, named `Corient approved: <surface>`. Client-specific curation stays OFF this account (remote third-party service, confidentiality rule in both agents' SYSTEM.md); the corpus holds surface patterns, never client work.

## Entry criteria

A component enters a list only when it has survived a graded rep: cited in a passed golden eval, kept through a real build's critique pass, or explicitly approved by the operator. A bookmark is a judgement record, not a to-read pile. When adding, note WHY in the run record or eval that graded it (the list itself cannot hold notes; the graded artifact is the provenance).

Seeded 2026-08-17 from the two passed evals: Growth Plans (18932), Pricing Table (9115), Boxly Pricing-1 (11612) from wright's reference-capture-002; Financial Hero Section (19056) from flowsmith's critique-grounding-001.

## Usage rule (both agents)

Reference capture for a surface checks the corpus list FIRST, then falls back to fresh catalog search; fresh finds that survive the build's critique pass get added back. Everything borrowed still re-tokenises to `brand/[client]/DESIGN.md`; the corpus curates structure and composition, never client styling.
