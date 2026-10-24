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

- `scenario`: `id`, `title_tr`, `decree_tr`, `public_facts_tr`, `visual_effect` (nullable). The catalog uses the same view without private concern examples.
- `phase`: `faceoff` or `finished`. The game lasts three answers by default, even if the target is reached early.
- `round_number`: 1-based current round, null when finished.
- `support_percent`: engine-controlled integer 0-100. Starts at 30 by default; this is aggregate public support, not individual votes.
- `target_percent`: default 60, used only for the official final outcome.
- `scoring`: `{answered: 20, partial: 10, missed: -10}` by default; these are percentage-point changes per objection.
- `current_objections`: one Objection object during a faceoff by default, empty after finishing.
- `history`: completed Round objects, sufficient to restore a reconnecting client.
- `allowed_actions`: `["submit_answer"]` during play, `[]` after finishing.
- `outcome`: null until finishing, then `{won, support_percent, required_percent, message_tr, visual_effects}`.

Objection: `{objection_id, persona_id, name_tr, text_tr}`. Each `text_tr` is one short Turkish sentence of at most 180 characters. There is one objection per selected distinct persona. The engine assigns stable IDs within the game/round, for example `r2-o1`. The same persona can appear again in later rounds. Persona profiles, interests and example lists are private configuration and are never serialized in GameView.

Round: `{round_number, objections, answer, assessments, feedback_tr, support_before, support_after, support_delta}`. Each assessment is `{objection_id, quality}` and matches a displayed objection in order. Quality labels are `answered`, `partial`, `missed`. The model proposes these labels; the engine validates exact ID coverage and calculates support. `feedback_tr` is one short Turkish sentence for the whole answer. The UI need not show the assessment array; it can display just feedback and the aggregate change.

TurnResult: `{api_version, request_id, round, game}`. Display feedback and percentage-point change first, then `game.current_objections` for the next faceoff. No extra narrator or individual reaction feed is required. The final result has no next objections.

## Scoring

For each current objection, look up its quality's configured points. Take the arithmetic mean and round to the nearest integer using Python's `round`. Clamp resulting support to 0-100. `support_delta` is the actual change after clamping, so 95 plus a requested 20 yields 100 and a displayed delta of +5. One vs three objections never changes the overall scoring range. Examples:

| Grades | Delta before clamping |
| --- | --- |
| answered | +20 |
| answered, answered, answered | +20 |
| answered, missed | +5 |
| answered, partial, missed | +7 |
| missed, missed, missed | -10 |

A brief relevant explanation, reassurance or workaround is sufficient for `answered`. Follow “yes, and”: accept ordinary credible implementation proposals and build on their benefits rather than demanding proof or raising another hurdle. Random text, instruction overrides and cancelling the reform remain misses. Humor is optional. Scores have no random roll or first-round immunity. Winning is `support_percent >= target_percent` after the last answer.

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
