# FreePi2API

OpenAI-compatible local proxy for the **free-pi** backend (`api.freepi.ai`) — the
same shape as [ADCode2API](https://github.com/ErfanBagheri404/ADCode2API) / WorkBuddy2API.

Pure Python 3 stdlib, no dependencies, binds loopback only.

## How it works

free-pi's own CLI (`free-pi-cli`) talks to `POST /v1/chat/completions` on
`api.freepi.ai` with a JWT from a GitHub device-flow login plus two required
headers. This proxy is a thin relay with the same contract:

| piece | value |
|---|---|
| upstream | `https://api.freepi.ai` |
| chat route | `POST /v1/chat/completions` (OpenAI-compatible, stream + buffered) |
| models route | `GET /client-version` → catalog |
| auth | GitHub device flow (`/auth/github/device` → `/auth/consent` → `/auth/token`) |
| required headers | `authorization: Bearer <jwt>`, `x-session-id`, `x-client-version: 0.4.10` |

Notes found while reading the CLI source (`src/vendor/shared/api.ts`,
`src/provider.ts`, `src/auth-flow.ts`):

- The server answers `403 {"code":"consent_required"}` on token polling until
  consent is recorded for that session — consent is submitted **before** polling.
- `/client-version` carries `min` (forced-update gate) and the model catalog;
  the CLI pins `x-client-version` to its own version on every completion.
- Model ids are routing/display ids (e.g. `deepseek-v4-flash`,
  `claude-sonnet-5.5`) resolved server-side against an `openrouter` name.
- Requests are passed through verbatim (tools, temperature, etc. all allowed
  — unlike ADCode's strict gateway).

## Usage

```bash
py main.py --login        # GitHub device flow, stores %APPDATA%\FreePi2API\auth.json
py main.py --no-menu      # start server directly (default port 61040)
py main.py                # interactive menu
```

Then point any OpenAI-compatible client at `http://127.0.0.1:61040/v1`:

```bash
curl http://127.0.0.1:61040/v1/models
curl http://127.0.0.1:61040/v1/chat/completions \
  -H "content-type: application/json" \
  -d '{"model":"deepseek-v4-flash","messages":[{"role":"user","content":"hi"}]}'
```

### Endpoints

- `GET /health` / `GET /healthz` — liveness
- `GET /v1/models` — model catalog (19 models, from `GET /client-version`)
- `POST /v1/chat/completions` — buffered or `stream: true` SSE relay

Model ids are accepted bare (`deepseek-v4-flash`) or prefixed
(`freepi/deepseek-v4-flash`); a missing `model` defaults to `deepseek-v4-flash`.
Pass `--api-key <key>` to require `Authorization: Bearer <key>` on `/v1/`.

Environment: `FREEPI2API_UPSTREAM`, `FREEPI2API_PORT`, `FREEPI2API_SESSION_ID`,
`FREEPI2API_CLIENT_VERSION`.

## Tests

```bash
py main.py --no-menu      # in another terminal
py tests/selfcheck.py     # hits http://127.0.0.1:61040 (override with FREEPI2API_URL)
```