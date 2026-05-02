# CLAUDE.md — Research Harness

This file provides guidance to Claude Code when working in this research project.

## Quick Start for a New Project

```bash
uv sync
python harness.py init     # setup wizard: fills config.env, scaffolds data client, reviews prompts
python harness.py          # start the research loop
```

## Commands

**Package manager:** `uv` (not pip). All commands use `uv run` for experiments.

```bash
# First-time setup
python harness.py init

# Run the research loop
python harness.py              # 5 iterations, model from config.env
python harness.py 8            # 8 iterations
python harness.py 8 sonnet     # 8 iterations, sonnet
python harness.py --resume     # resume an interrupted run

# Run an experiment directly
uv run python -m experiments.<name>.run
uv run python -m experiments.<name>.run --skip-fetch   # reuse cached data

# Run tests
uv run python -m pytest experiments/ -v
```

## Repository Structure

```
research_harness/
├── harness.py                    # Primary CLI — init, run loop, checkpoint, summarize
├── config.env                    # Project configuration (TOPIC, MODEL, etc.)
├── session.json                  # Loop state — auto-generated, gitignored
├── pyproject.toml                # Python dependencies (uv)
├── .python-version               # Python 3.13
├── CLAUDE.md                     # This file
├── docs/
│   ├── research_brief.md         # High-level project brief — written by init, edited by you
│   ├── taste.md                  # Summary style guide — written by you, read by summarizer
│   ├── findings.md               # The paper — owned by researcher agent
│   ├── researcher_prompt.md      # Researcher agent instructions
│   ├── critique_prompt.md        # Critiquer agent instructions (covers publishability + reward hacking)
│   ├── summarizer_prompt.md      # Summarizer agent instructions
│   └── exchanges/
│       ├── critique_latest.md    # Latest critique (overwritten each iteration)
│       ├── researcher_response.md # Latest researcher response (overwritten each iteration)
│       └── archive/              # Full iteration history (never overwritten)
│           ├── critique_N.md
│           ├── critique_N_log.txt
│           ├── researcher_response_N.md
│           ├── researcher_N_log.txt
│           ├── findings_before_N.md
│           └── findings_after_N.md
├── docs/summaries/
│   └── summary_N.md              # Human-facing run summary, written to taste.md style
├── scripts/
│   └── research_loop.sh          # Legacy shell loop (superseded by harness.py)
├── src/
│   └── data/
│       ├── base.py               # DataSource abstract base class
│       └── <your_source>.py      # Concrete data source — scaffolded by init
├── experiments/
│   └── <experiment_name>/
│       ├── run.py                # Entrypoint: uv run python -m experiments.<name>.run
│       └── tests/
│           └── test_unit.py      # Synthetic data tests (no network calls)
└── data/                         # Cached outputs (gitignored)
```

## How the Loop Works

Each iteration:
1. **Critiquer** reads `research_brief.md` + paper + prior exchanges → writes `critique_latest.md`. Covers data sufficiency, novelty, rigor, publishability, and reward hacking detection.
2. **Researcher** reads brief + critique + any steering note → writes code, updates `findings.md`, writes `researcher_response.md`.
3. Git commits each changed file individually.
4. **Checkpoint** displays scores table, verdict, top critique points, researcher actions.
5. **Interactive prompt**: Enter to continue, `s` to steer, `q` to quit.

After all iterations: a dedicated **summarizer** agent writes `docs/summaries/summary_N.md` in the style of `docs/taste.md`.

### Prompt injection order (researcher)
1. `docs/research_brief.md` — immutable north star
2. `docs/researcher_prompt.md` — harness instructions
3. `docs/exchanges/critique_latest.md` — what to fix
4. Steering note (if any) — third-party perspective, no special authority

### Prompt injection order (critiquer)
1. `docs/research_brief.md`
2. `docs/critique_prompt.md`
3. History context

## Data Layer (`src/data/`)

All data access goes through a `DataSource` subclass:

```python
from src.data.base import DataSource

class MySource(DataSource):
    def fetch(self, series: str) -> list[dict]:
        ...  # API call

    def cache_path(self, series: str) -> Path:
        return self.data_dir / f"{series}.json"
```

## Experiment Pattern

```python
# experiments/example/run.py
import argparse
from src.data.my_source import MySource

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    source = MySource(data_dir="data/example")
    data = source.load(series="main") if args.skip_fetch and source.is_cached(series="main") \
           else source.fetch(series="main")
    # ... analysis ...

if __name__ == "__main__":
    main()
```

Rules:
1. Accept `--skip-fetch` to reuse cached data
2. Load data via `DataSource.load()` — never raw API calls inline
3. Write results to `data/<name>/`
4. Runnable as `uv run python -m experiments.<name>.run`
5. Unit tests use synthetic data only — no network calls

## Credentials

Store in `.env` (gitignored). Load with python-dotenv:

```python
from dotenv import load_dotenv
import os
load_dotenv()
API_KEY = os.environ["MY_API_KEY"]
```

## Adding a New Experiment

1. Create `experiments/<name>/run.py` and `experiments/<name>/tests/test_unit.py`
2. Add its run command to this CLAUDE.md under Commands
3. Add a one-line description under the loop architecture section
4. Update `docs/findings.md` with initial results once it runs
