# Eval candidate: L-79 metadata truncation

Status: drafted, ungraded. Promote to a golden case when a Figma-input build next runs.

## Smallest reproduction prompt

> Build the design inventory for this Figma section. File key `C32w4zprKG9FooBGPhbp9Q`,
> canvas `1:2`, section `132:2148` (Homepage Loan Types, 1440x898).
> Report the photo count and the element checklist for the section.

## Pass criterion

The run PASSES only if all of the following hold:

1. It calls `get_design_context` on `132:2148` or on its child card frames. A run that calls only
   `get_metadata` fails regardless of what it reports.
2. It reports **four** card frames (`132:2174`, `132:2176`, `132:2182`, `132:2189`), not zero and
   not three.
3. Its element checklist names the per-card elements that metadata cannot see: the card heading,
   the card body, the 48px masked SVG icon, the backdrop-blur layer and the gradient overlay.
4. Its photo count is greater than zero. Metadata alone yields zero image fills for this section.
5. It states that metadata was insufficient, or cites L-79 by name.

## Why this case

Metadata reports these four cards as childless leaves. A childless frame is indistinguishable from a
genuinely empty one, so the failure is silent and passes any gate whose denominator came from the
same source. This section is the smallest known reproduction.

## Trap to watch

A run may report three cards from the rendered screenshot rather than four from the node tree. That
is a different defect (screenshot-sourced inventory) and also fails criterion 2.
