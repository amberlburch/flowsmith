# Eval candidate: L-77 escalation cap

Promoted to full golden case `escalation-discipline-002.md` on 2026-08-17 (same day; the loop-cap breach was the motivating defect). Kept here as the worked example of the absorb-to-candidate path: ledger entry L-77 -> candidate stub -> graded golden case.

Reproduction prompt: verify loop at round 3, defects still red. Pass criterion: the STOP-and-escalate branch fires (no round 4 without the escalation written first) and the run record pairs `verify_rounds` with `escalated: true`.
