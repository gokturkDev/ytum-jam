# HTTP protocol v2: reforms

This replaces the ten-juror v1 contract. All game, turn and error envelopes contain `api_version: "2"`. Routes use `/v2`. The old jury, stances, fondness, speeches and finish command are removed. The former `marriage_v1` abolition scenario is removed. Use the reform IDs returned by the catalog.

Send UTF-8 JSON with `Content-Type: application/json`. Default base URL: `http://127.0.0.1:8000`. `/docs` and `/openapi.json` provide the authoritative generated schemas. Checked-in [examples](examples) contain a complete scripted game.

| Route | Request | Successful response |
| --- | --- | --- |
| `GET /health` | none | 200: status, backend, configured; no provider call |
| `GET /v2/scenarios` | none | 200: ordered ScenarioView array; no provider call |
| `POST /v2/games` | `{"scenario_id":"toothbrushing_v1"}` | 201: GameView with the first objection |
| `GET /v2/games/{game_id}` | none | 200: GameView, read-only |
| `POST /v2/games/{game_id}/answers` | AnswerCommand | 200: TurnResult including the next faceoff, or final outcome |

Creation generates the first faceoff before publishing a game. It can return a typed provider error. Unlike an answer command, creation has no replay ID; retrying a lost creation response can create a new game, but consumes no player round. Abandoned games disappear on server restart.

AnswerCommand:

```json
{
  "request_id": "aceb710b-f839-4ba1-b149-fb93c52bdad0",
  "expected_version": 0,
  "text": "Herkese fırça verelim ve kullanmayı birlikte öğrenelim!"
}
```

The client submits commands only, never round numbers, personas, objections, grades, support or outcomes. Unknown fields are rejected. `text` must have 1-6,000 Unicode code points after trimming; the engine preserves original accepted text. Whitespace-only input is invalid. `expected_version` is a nonnegative JSON integer, not a string or boolean. IDs are UUID strings. Creation is version zero; each successful answer increments once.

## GameView

Fields: `api_version`, `game_id`, `version`, `scenario`, `phase`, `rounds_completed`, `total_rounds`, `round_number`, `support_percent`, `target_percent`, `scoring`, `current_objections`, `history`, `allowed_actions`, `outcome`.

- `scenario`: `id`, `title_tr`, `decree_tr`, `public_facts_tr`, `visual_effect` (nullable), `starting_support`, `target_support`, `rounds`. The catalog uses the same view without private concern examples.
- `phase`: `faceoff` or `finished`. The game lasts its configured number of answers (four for toothbrushing, abolishing nobility and freedom of expression; three for the others), even if the target is reached early.
- `round_number`: 1-based current round, null when finished.
- `support_percent`: engine-controlled integer 0-100. Starts at 30 by default; this is aggregate public support, not individual votes.
- `target_percent`: selected reform's target, used only for the official final outcome.
- `scoring`: `{minimum: -30, maximum: 30}`; these bound the integer score per objection, not fixed grade buckets.
- `current_objections`: one Objection object during a faceoff by default, empty after finishing.
- `history`: completed Round objects, sufficient to restore a reconnecting client.
- `allowed_actions`: `["submit_answer"]` during play, `[]` after finishing.
- `outcome`: null until finishing, then `{won, support_percent, required_percent, message_tr, visual_effects}`.

Objection: `{objection_id, persona_id, name_tr, text_tr}`. Each `text_tr` is one short Turkish sentence of at most 180 characters. There is one objection per selected distinct persona. The engine assigns stable IDs within the game/round, for example `r2-o1`. The same persona can appear again in later rounds. Persona profiles, interests and example lists are private configuration and are never serialized in GameView.

Round: `{round_number, objections, answer, assessments, feedback_tr, support_before, support_after, support_delta}`. Each assessment is `{objection_id, score}` and matches a displayed objection in order. `score` is a strict integer from -30 to 30. The model proposes it; the engine validates bounds and exact ID coverage, then calculates support. Booleans, strings, floats and out-of-range values fail the operation. `feedback_tr` is one short Turkish sentence for the whole answer. The UI need not show the assessment array; it can display just feedback and the aggregate change.

TurnResult: `{api_version, request_id, round, game}`. Display feedback and percentage-point change first, then `game.current_objections` for the next faceoff. No extra narrator or individual reaction feed is required. The final result has no next objections.

## Scoring

Take the arithmetic mean of the current objections' integer scores and round to the nearest integer using Python's `round`. With the current single-objection setup this is exactly the proposed score. Clamp resulting support to 0-100. `support_delta` is the actual change after clamping: support 95 with score 30 yields support 100 and displayed delta +5. Score 0 leaves support unchanged but still consumes the completed round.

Scores measure coverage of the actual objection: -30 is completely unrelated or harmful; negative intermediate scores reflect evasion or a merely topical answer; 0 reflects no clear progress; +1 to +15 reflects partial coverage; +16 to +29 reflects substantial to near-complete coverage. +30 is reserved for explicit complete resolution. A gift or proposal that addresses another problem may fail. The evaluator must not invent crucial missing solution details to give full credit, or invent unrelated obstacles to deny it. Feedback explains the same coverage judgment in one sentence.

The catalog exposes each reform's starting support, target and round count. Clients must use those returned values instead of hardcoded defaults. Toothbrushing, nobility and expression have four rounds; the rest have three. Winning is `support_percent >= target_percent` after the last answer.

Contract migration within v2: `assessments[].quality` is removed and replaced by `assessments[].score`; the four named `scoring` fields are replaced by `minimum` and `maximum`. Update Unity/client DTOs before using this revision. No client-supplied score is accepted in AnswerCommand.

## Errors and retries

Errors use this envelope, including FastAPI validation errors:

```json
{
  "api_version": "2",
  "error": {
    "code": "GAME_BUSY",
    "message_tr": "Halk hâlâ düşünüyor; tekrar deneyin.",
    "retryable": true
  }
}
```

| HTTP | Codes |
| --- | --- |
| 404 | `GAME_NOT_FOUND` |
| 422 | `INVALID_INPUT`, `INVALID_SCENARIO` |
| 409 | `WRONG_PHASE`, `STALE_VERSION`, `REQUEST_ID_CONFLICT`, `GAME_BUSY` |
| 502 | `INVALID_FACEOFF_OUTPUT`, `PROVIDER_INCOMPLETE`, `PROVIDER_REFUSAL`, `PROVIDER_FAILURE` |
| 503 | `PROVIDER_CONFIGURATION`, `PROVIDER_UNAVAILABLE` |
| 504 | `PROVIDER_TIMEOUT`, `TURN_TIMEOUT` |

Respect `retryable`. Keep one client action in flight. For network/time-out/busy retry, reuse the exact body and request UUID; never turn a retry into another answer. The engine checks successful replay results before stale-version validation, so exact replay returns the original TurnResult even if later rounds have completed. Different text or version with a used ID returns `REQUEST_ID_CONFLICT`. Concurrent in-progress mutations return `GAME_BUSY`. Failed commands are not stored as successes and may retry against unchanged state.

Evaluation and generation of the next faceoff form one atomic command. Failure of either leaves support, current objections, history and version unchanged. GET can read the prior committed game while a command is running. On `STALE_VERSION`, GET and reconcile the client before a new intentional answer. A provider configuration error requires fixing the engine environment. Errors and logs contain no key or raw provider credential details.

## Unity integration

Run `python -m ambassador.server` manually beside the editor and send the same requests with UnityWebRequest. Use JSON DTOs supporting arrays, nullable values and the exact enum strings. Check HTTP status before parsing a success DTO; parse ErrorEnvelope on failures. `round_number` and `outcome` can be null. Arrays may be empty when finished. Objection IDs bind UI faceoff bubbles to personas; crowd rendering uses `support_percent`, not a count of displayed speakers.

The client owns loading, animations and reveal timing. It must not send private profiles or calculate authoritative gains. Rebuild the display from GameView on reconnect. Only the Python engine needs the API key. Desktop/editor use is supported; hosted/mobile/WebGL deployment remains separate work. Games and response replay caches are in memory in one server process, so restart loses them.

## Reform effects

`visual_effect` is null for topics with no drafted visual change, or `{id, description_tr, name_updates}`. The catalog advertises a possible effect; it is not permission to apply it. Only `outcome.visual_effects` awards effects, and only after victory. Losing and unfinished games award none. Replaying a command returns the same snapshot; render effects idempotently from game state.

Stable effect IDs are `white_smiles`, `remove_crowns`, `school_clothes`, `clean_streets`, and `show_surnames`. For the surname effect, `name_updates` contains `{persona_id, name_tr}` entries such as Ayşe Demir. It is empty in the catalog and for effects that do not rename characters. Use persona IDs to update name labels. Other effects drive sprite/environment changes in the Unity client; this Python prototype returns data and does not contain sprite assets.

Each game has one selected topic and independent support. There is no persistent kingdom-wide campaign across games. The current list is the nine reforms from `konular-draft.md`; public fact descriptions specify scope and avoid hidden implementation traps. Start a new game to discuss another reform.

## Concern diversity

The server tracks an internal concern ID for each committed objection and selects a previously unused topic focus for the next round. Focus selection is part of the atomic turn, so failures and replay do not consume extra concerns. It also changes the speaker when another persona is available. The generation adapter must echo the assigned concern ID, and exact repeated objection text is rejected. These IDs are internal generation metadata, not a client command field; public Objection DTOs remain unchanged. The UI still displays one objection by default.

The score range is now -30 through +30; clients must read `scoring.minimum` and `scoring.maximum` rather than hardcode the previous bounds. Intermediate integer scores, existing target percentages and configured round counts are preserved.
