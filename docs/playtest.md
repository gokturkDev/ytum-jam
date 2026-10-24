# Reform playtest notes

Current context: a modern-minded king introduces reforms to a fictional medieval society. The ambassador listens and finds practical ways forward. One objection and one short feedback sentence per round. Humor is natural and optional. Prompt version: `reforms-v3.0`.

## Verified

69 automated tests passed on macOS arm64 / Python 3.14.8. Ruff lint/formatting and dependency checks pass. Existing transaction, retries, timeouts, scoring and real-HTTP CLI checks remain. The reform check covers all nine catalog entries, one visible objection, five optional visual effects, awarding effects only on victory, and actual surname updates. The CLI tests exercise topic selection and both endings. Tests need no credentials or paid calls. Dependencies remain pinned in `requirements.lock`.

Live model: `gpt-4o-mini`, with the API key loaded privately from `.env`. A complete three-round `schooling_v1` game passed through the actual service/API with ASGI HTTP transport:

- Ayşe worried about household work while a child attends school. A brief proposal for free school, meals and family support earned +20, bringing support to 50%.
- Cem worried about workshop labor. Deliberately unrelated text about potatoes in space earned -10, returning support to 40%.
- Hasan worried about the harvest without his son. A proposal for a village teacher, school meals, shared work and family support earned +20, reaching 60%.

The result was victory and `school_clothes` in `outcome.visual_effects`. Relevant proposals were accepted without demands for documentary proof or guaranteed funding. Feedback built on the offered help instead of dismissing it. This is one qualitative live sample, not a deterministic expected vote pattern. The other eight reforms are validated with the fake backend; they have not each had a full live playtest in this revision.

## Manual checks

1. Select a reform in the CLI, or use `--scenario` with an ID from `GET /v2/scenarios`.
2. Check the objection fits both the topic and the ordinary medieval persona. It should express a clear personal worry, not a modern jargon-heavy policy essay or an invented restriction.
3. Offer a short relevant explanation or practical implementation proposal. The response should build on it using “yes, and”; missing fine details must not automatically block progress.
4. Try unrelated text, an instruction override, or a solution that cancels the reform. These should not earn automatic support.
5. Correct a mistaken assumption using the public facts. That can be enough to persuade; no obligatory gift is required.
6. Confirm each turn has one objection and one compact feedback line, with no forced comedy.
7. Win each of the five visual-effect reforms. Check the awarded effect ID and the terminal description. On surname victory verify Ayşe Demir, Hasan Yılmaz and Cem Kaya. In a Unity client apply sprite/environment effects from the outcome, not from the catalog preview.
8. Lose a visual-effect reform: no effect should be awarded. GET and successful command replay must not award an extra gain or alter objections.

Each game discusses one reform. Cross-reform campaign persistence, Unity sprites and environment rendering are not in this terminal repository. A new server process is required to reload scenario/persona data. Transcripts are opt-in and contain player answers; keep them private. Logs and public responses must never include API keys or hidden reasoning.
