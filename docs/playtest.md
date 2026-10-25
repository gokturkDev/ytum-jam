# Reform playtest notes

Current behavior: one short objection per turn, selected from a previously unused concern focus, and one short feedback sentence. Scores are integers from -30 to +30 based on coverage of that exact objection. Even a tentative helpful hint earns positive partial credit. Prompt version: `reforms-v3.5`.

## Verification

99 automated tests pass on macOS arm64 / Python 3.14.8. Ruff lint/formatting checks pass. Existing transaction, retries, timeouts, cancellation, strict score bounds/types, intermediate/zero score preservation, clamping, topic selection, both endings and real-HTTP CLI checks remain. Checks also cover non-repeating concern IDs, speaker rotation, rejection of verbatim repeated objections without committing a turn, valid -30/+30 extremes and session-only reform generation. All nine configured targets remain reachable.

Toothbrushing, abolishing nobility and freedom of expression remain four rounds; the other six remain three. Initial and target support percentages are unchanged. Each bundled topic now contains five distinct concern focuses. Configuration must provide at least one focus per round.

## Helpful-hint scoring check: v3.5

This is a small prompt calibration: relevant hints receive positive partial credit even
when the player leaves implementation details open. The engine still applies the model's
validated integer directly; score bounds, targets, round counts and full-coverage requirements
are unchanged. Length alone earns no bonus. Feedback should welcome the useful direction
before identifying a gap in the original concern.

Model: `gpt-4o-mini`, key loaded privately from `.env`. The issue was reproduced through a real
local HTTP server, creating games and submitting answers through the public endpoints. The
test selected one existing concern per scenario and one round to isolate grading. The original
displayed objections, answers and initial game states were then replayed through the same HTTP
answer endpoint after the prompt change.

| Displayed concern | Player answer | Before | After |
| --- | --- | --- | --- |
| Cannot afford a toothbrush | Sarayın kasası da halk için var. | -20 | +10 |
| School is far from the village | Köyün arabalarını bir düşünelim. | -15 | +10 |
| Distinguishing household brushes | Renkler bu işte işimize yarayabilir. | +8 | +5 |

The funding and transport hints previously lost support because they lacked a complete plan.
They now receive small positive scores without pretending that free brushes or a complete
transport system were offered. The color hint is a check outside the new calibration examples.
An additional care/rest check gave +12 to a longer answer suggesting help from neighbors,
+30 to explicit rotating animal care, and -30 each to an unrelated crown and withholding feed.
A supportive restatement with no helpful hint received 0 after clarifying that mere
incompleteness is not evasion. The color hint received +8 on an earlier run and +5 on the
final run; these live observations are qualitative checks, not deterministic model guarantees.

## Earlier diversity playtest: v3.4

Model: `gpt-4o-mini`, key loaded privately from `.env`. Both runs used the real local HTTP server and the same routes as the terminal client.

Before the change, a four-round toothbrushing game returned four variations of the same time/workload concern: finding time before field work, finding time among chores, fitting it around workshop work, and looking after children while brushing. Different wording and speakers had not created different questions.

After the change, the four-round live game produced:

| Round | Actual concern | Score |
| --- | --- | --- |
| 1 | Identifying one's own brush when household brushes get mixed up | +16 |
| 2 | Fitting brushing into the morning routine | +15 |
| 3 | Learning how to brush correctly | +25 |
| 4 | Understanding why to brush before teeth hurt | +24 |

The answer proposed personal marked brushes, free supplies, demonstrations, a short daily routine and preventive care. Support went from 10% to 90%, with victory awarding the white-smile effect. The objections had different underlying problems, and intermediate scores above the former +20 ceiling were returned. No provider retry was needed in this run. These are qualitative observations, not deterministic model guarantees.

## Diversity mechanism and limits

The engine chooses an unused concern ID before generation and includes its specific focus plus prior accepted dialogue. The model must echo that ID; mismatches and verbatim repeated lines are invalid outputs. Speaker rotation is used when possible. Focus history commits atomically with the turn, so failure and successful replay cannot consume an extra focus. The fake backend uses each selected concern's own example.

This prevents selecting the same configured focus twice. It does not constitute a perfect semantic proof that model wording stayed on topic: manual review should still look for drift, paraphrased repetition, or a new question that secretly reopens an already resolved concern. The examples and focus descriptions are editable scenario data. Separate games can revisit the same reform and its topics.

## Manual checks

- Answer a question with a concrete proposal that solves a different problem: it should not receive positive credit merely for mentioning the reform.
- Try a tentative helpful hint with implementation details missing: expect small positive credit and feedback acknowledging the useful direction.
- Compare a partial idea, a substantial but incomplete solution and full coverage. Expect intermediate integers; +30 remains reserved for full coverage without invented missing steps.
- Confirm the next objection raises a different concern, not a new person's version of the same cost/time/family-work question.
- Make an unrelated or harmful suggestion and check for a clear negative score and appropriate feedback.
- Verify that 0 consumes a round without changing support, and exact successful request replay never awards a second gain.
- Check five visual-effect reforms award effects only on victory. Unity renders those effects; this repository supplies the HTTP engine and terminal presentation.

The public assessment remains `{objection_id, score}`; score bounds are now -30/+30 and `scoring.minimum`/`maximum` reflect them. Concern IDs are internal generation metadata; public objection DTOs are unchanged. Restart loses in-memory games. Optional transcripts contain player answers and should remain private; keys and hidden reasoning must never be logged.
