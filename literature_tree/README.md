# Literature Tree Exploration Agent

Maps paper-connection networks from a Zetaris-served corpus, keeps bounded
rolling checkpoints, and writes an interactive graph where every edge carries
cited evidence.

## Layout

| File | Role |
|---|---|
| `config.py` | Load `.env.local` only; never print secrets |
| `llm.py` | Meterless Runtime and existing Nemotron chat routing |
| `providers/` | Provider registry, Meterless discovery/status, and credential storage |
| `tools_zetaris.py` | REST SQL tools (`Bearer`, `X-Org-ID`, UUID `X-Request-ID`) |
| `memory.py` | Markovian hop checkpoints + H-Mem under `tmp/literature_tree/` |
| `workers.py` | 3-agent sliding window (discover → infer → synthesize) |
| `graph.py` | Nodes, edges, evidence schema |
| `main.py` | CLI |
| `verify.py` | REST + pool harness |
| `viewer/index.html` | Local network graph |

## Environment

Put values in gitignored `.env.local` (quoted, no `<angle>` placeholders):

```
ZETARIS_REST_URL=http://localhost:8888/api/v1.0
ZETARIS_ORG_ID=1
ZETARIS_API_KEY=...
# Optional legacy Nemotron-compatible endpoint:
MODEL_BASE_URL=
MODEL_API_KEY=
NEMOTRON_MODEL=
# Meterless Runtime credentials may instead be pasted in the provider UI/API.
METERLESS_BASE_URL=http://127.0.0.1:8088/v1
METERLESS_RUNTIME_TOKEN=
METERLESS_MODEL=meterless/auto
LITERATURE_PAPERS_TABLE=   # optional qualified Lightning name
LITERATURE_CITATIONS_TABLE=
```

This instance currently has `NY_TAXI`, `POKEAPI_REST`, and `TPCDS_DB` — no paper
tables. Leave the literature table unset and use `--fixture` until you onboard a
corpus (a CREATE step; not done by this app).

## Run

From the repository root:

```sh
python3 -m literature_tree.verify
python3 -m literature_tree.main --query "attention is all you need" --dry-run
python3 -m literature_tree.main --query "attention is all you need" --hops 3 --fixture
```

Then open `literature_tree/viewer/index.html` and load `tmp/literature_tree/<tree>/graph.json`.

Meterless Runtime defaults to `http://127.0.0.1:8088/v1`, reads the token from
provider settings or `<stateDir>/proxy-token`, and routes to `meterless/auto`
unless `METERLESS_MODEL` is set. Provider settings are stored in
`tmp/literature_tree/provider-settings.json` with restrictive permissions.

Install `openai` only when using the Nemotron-compatible endpoint:

```sh
python3 -m pip install -r literature_tree/requirements.txt
```

Without those keys, Agent 2 falls back to extractive quotes from abstracts.
