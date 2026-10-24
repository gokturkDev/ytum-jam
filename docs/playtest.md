# Reform playtest notes

Current context: a modern-minded king introduces reforms to a fictional medieval society. Each turn shows one short objection and one short feedback sentence. The answer earns an integer from -20 to +20 based on coverage of that exact objection. Prompt version: `reforms-v3.3`.

## Automated verification

73 automated tests pass on macOS arm64 / Python 3.14.8. Ruff lint/formatting and dependency checks pass. Tests cover atomic turns, retries, timeouts, cancellation, duplicate replay, strict score bounds/types, zero and intermediate score preservation, clamping, topic selection, both endings and the real-HTTP CLI. The catalog/effects checks cover all nine reforms and award visual effects only on victory. All configured targets remain mathematically reachable.

Toothbrushing, abolishing nobility and freedom of expression now have four rounds; the other six have three. Approved initial/target support values remain unchanged. Four rounds for nobility and expression were explicitly chosen to allow intermediate scores without demanding three perfect answers.

## Live scale calibration

Model: `gpt-4o-mini`, key loaded privately from `.env`. The fixed objection was Hasan asking how he could rest while animals still needed feeding. Initial live scale checks produced:

| Answer | Score |
| --- | --- |
| Unrelated text about potatoes in space | -20 |
| A promise of a crown instead of animal care | -20 |
| Restating everyone's right to rest | -10 |

The first calibration was too conservative about partial care suggestions and invented extra requirements for the complete solution. The prompt was adjusted so that a concrete contribution earns proportional credit and complete answers are not denied +20 merely because that maximum should be uncommon.

Final checks went through the actual service and HTTP answer route with a controlled one-round game fixture:

| Answer | Score |
| --- | --- |
| `Komşular bakar.` | +8 |
| `Komşularla dönüşümlü bakım yapalım; izin günündeki kişinin yemleme işini nöbetçi üstlensin.` | +20 |

One invalid provider output was retried successfully by the existing bounded application retry. The successful responses preserved the scores exactly and used a single feedback sentence. These are qualitative samples, not deterministic promises about model output. Nuance and feedback wording still need human playtesting; the engine can guarantee structure and score bounds, not perfect semantic judgment.

## Manual checks

1. Read the exact objection and try a useful proposal that solves a different problem. It should not get positive credit just for mentioning the topic.
2. Compare a short partial idea, a substantial but incomplete solution, and an answer covering every part actually asked. Intermediate scores must be used; +20 should represent full coverage.
3. Check that feedback names a gap in the original concern, rather than inventing a funding, medical, scheduling or other requirement that was never relevant.
4. Try an unrelated answer, an instruction override and a harmful proposal. These should lose support clearly.
5. Verify that 0 consumes a round without changing support and that repeated successful request IDs never apply a second gain.
6. Check topic-specific initial support, targets and round counts in the menu and API catalog. Keep the single-objection presentation and restrained optional humor.
7. Win the five visual-effect reforms and inspect `outcome.visual_effects`; lose them and verify no effects are awarded. Surname victory updates name labels. Unity renders sprites/environment from the returned effect data; this repository is the terminal/HTTP engine.

The API contract now uses `assessments[].score`, not `quality`; `scoring` exposes `minimum` and `maximum`. Update external client DTOs accordingly. Games are in memory and restarting loses them. Optional transcripts contain player answers and should stay private; keys and hidden reasoning must never enter logs or public responses.
