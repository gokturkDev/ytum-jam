# Kralın Elçisi: Reformlar

A relaxed Turkish persuasion game in a fictional medieval kingdom. A modern-minded king wants to introduce beneficial reforms from above; ordinary people worry about disrupting familiar ways of life. The ambassador listens and helps find workable solutions. The king's good intentions do not make every implementation perfect, and the people are not fools for having concerns.

Each round shows **one short objection**. A relevant explanation, reassurance or practical proposal can persuade the speaker. The evaluation follows “yes, and”: build on a reasonable suggestion without demanding proof, assuming nobody believes the player, or inventing another obstacle. Random text, empty requests for agreement and cancelling the reform still fail. Humor is restrained and optional; the short feedback after an answer remains.

## Setup and play

Python 3.11+; tested locally on Python 3.14.8. Keep your existing `.env` and its `OPENAI_API_KEY` private.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m pip install --no-deps -e .
```

Server:

```sh
LLM_BACKEND=openai OPENAI_MODEL=gpt-4o-mini .venv/bin/python -m ambassador.server
```

Client in another terminal:

```sh
.venv/bin/python -m ambassador.cli
```

Choose a reform from the menu, answer its current objection, and submit with a line containing only `/gonder`. `/cik` exits. For direct topic selection:

```sh
.venv/bin/python -m ambassador.cli --scenario schooling_v1
```

For a no-key integration demo, start the server with `LLM_BACKEND=fake`. Its grades are scripted: partial, answered, missed. It ignores answer content and does not test AI quality. The CLI always uses real HTTP.

## Reforms and visible changes

The nine selected topics come from `konular-draft.md`. Their public facts, prompt context, example concerns and visual effects live in [reforms.json](src/ambassador/scenarios/reforms.json).

| Reform ID | Topic | Visible effect on victory |
| --- | --- | --- |
| `toothbrushing_v1` | Diş fırçalama | White smiling mouths |
| `abolish_nobility_v1` | Soyluluğun kaldırılması | Remove noble crowns |
| `schooling_v1` | Çocuklar için zorunlu eğitim | School clothes on children |
| `clean_streets_v1` | Sokaklara çöp atılmaması | Remove street litter |
| `surnames_v1` | Soyadı düzeni | Show surnames |
| `free_expression_v1` | İfade özgürlüğü | None specified |
| `marriage_consent_v1` | Evlilikte karşılıklı rıza | None specified |
| `choose_profession_v1` | Meslek seçme özgürlüğü | None specified |
| `weekend_rest_v1` | Hafta sonu izni | None specified |

A game addresses one selected reform over three rounds. Support starts at 30%; final support of at least 60% wins. Answered adds 20 percentage points, partial adds 10, missed loses 10, with support clamped to 0-100. There is no early ending or first-round immunity. Short useful answers and imperfect implementation proposals are welcome. These defaults already allow two good answers and one miss to win.

Victory returns visual effect IDs through the API. The terminal describes the change and displays new names for the surname reform. This repository has no Unity/sprite frontend: it supplies the authoritative effect data for that frontend to render. Effects are not awarded before the final outcome or on defeat. Separate games have separate state; a persistent multi-reform campaign is not implemented.

## Personas and tuning

[personas.json](src/ambassador/scenarios/personas.json) defines ordinary medieval people: Ayşe the weaver, Hasan the farmer, and Cem the carpenter. Their habits, livelihoods and family responsibilities shape their concerns. Replace this data or set `PERSONAS_FILE` to your own array; no character is hardcoded in the game rules. `surname_tr` supports the surname effect. Restart the server after changing the catalog, personas or settings. Prompts are read on each model request.

The current defaults keep `OBJECTIONS_MIN=1` and `OBJECTIONS_MAX=1`. Scoring, initial/target support, rounds, provider deadlines and output budget are configurable in `.env.example`. Implementation promises stay proposals; accepting a credible solution does not let the player rewrite the reform's central right.

## API, checks and limitations

Use `GET /v2/scenarios`, `POST /v2/games`, `GET /v2/games/{id}` and `POST /v2/games/{id}/answers`. The old `marriage_v1` abolition scenario is removed. The original handoff is historical; this README describes the current product. See [protocol](docs/protocol.md), [complete examples](docs/examples), `/docs` and `/openapi.json`.

```sh
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python -m pip check
```

One server process/worker, localhost by default. Games and successful response caches are in memory; restarting loses them. Evaluation plus next-round generation commits atomically. Retry the exact answer body and request ID after a timeout; replay cannot award a second gain. GET shows the last committed state during evaluation. One application retry per failed provider operation, no SDK retries, 30-second per-attempt and 75-second whole-operation deadlines by default. No database, accounts, hosting, Unity implementation or mobile packaging is included.

The official async OpenAI SDK uses Responses Structured Outputs without temperature/reasoning options. Logs contain model, prompt version, latency, token usage and support changes, never keys. `TRANSCRIPT_DIR` opts into private local player transcripts; `--debug` writes public client responses to stderr. See [playtest notes](docs/playtest.md) for actual verification and quality limits.
