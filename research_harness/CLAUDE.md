# CLAUDE.md — Research Harness

This file provides guidance to Claude Code when working in this research project.

## Quick Start for a New Project

1. **Fill in `config.env`** — set TOPIC, PAPER_TITLE, RESEARCH_QUESTION, DATA_SOURCE_NAME, PUBLICATION_VENUE
2. **Write your data layer** — create `src/data/<your_source>.py` implementing `DataSource`
3. **Write your first experiment** — create `experiments/<name>/run.py`
4. **Draft the paper skeleton** — fill in `docs/findings.md` with your initial findings
5. **Run the loop** — `./scripts/research_loop.sh [max_iterations] [model]`

## Commands

**Package manager:** `uv` (not pip). All commands use `uv run`.

```bash
# Install dependencies
uv sync

# Run an experiment (replace <name> with your experiment folder)
uv run python -m experiments.<name>.run
uv run python -m experiments.<name>.run --skip-fetch   # reuse cached data

# Run tests
uv run python -m pytest experiments/ -v

# Run the research loop (researcher ↔ critiquer feedback)
chmod +x scripts/research_loop.sh
./scripts/research_loop.sh              # defaults from config.env
./scripts/research_loop.sh 8           # 8 iterations
./scripts/research_loop.sh 5 sonnet    # 5 iterations, sonnet model
```

## Repository Structure

```
research_harness/
├── config.env                    # Project configuration (TOPIC, DATA_SOURCE, etc.)
├── pyproject.toml                # Python dependencies (uv)
├── .python-version               # Python version
├── CLAUDE.md                     # This file
├── docs/
│   ├── findings.md               # The paper — modified by researcher agent each iteration
│   ├── researcher_prompt.md      # Researcher agent instructions
│   ├── critique_prompt.md        # Critiquer agent instructions
│   ├── evaluation_prompt.md      # External evaluation prompt (paste into fresh session)
│   └── exchanges/
│       ├── critique_latest.md    # Latest critique (overwritten each iteration)
│       ├── researcher_response.md # Latest researcher response (overwritten each iteration)
│       └── archive/              # Full iteration history (never overwritten)
│           ├── critique_N.md
│           ├── researcher_response_N.md
│           ├── findings_before_N.md
│           ├── findings_after_N.md
│           └── research_loop.log
├── scripts/
│   └── research_loop.sh          # Automated loop orchestrator
├── src/
│   └── data/
│       ├── base.py               # DataSource abstract base class
│       └── <your_source>.py      # Your concrete data source implementation
├── experiments/
│   └── <experiment_name>/        # One folder per experiment
│       ├── run.py                # Entrypoint: python -m experiments.<name>.run
│       └── tests/
│           └── test_unit.py      # Synthetic data tests (no network calls)
└── data/                         # Cached outputs (gitignored)
    └── <experiment_name>/
```

## Architecture

### Data Layer (`src/data/`)

All data access goes through a `DataSource` subclass. This enforces caching and makes experiments reproducible.

```python
from src.data.base import DataSource

class MySource(DataSource):
    def fetch(self, series: str) -> list[dict]:
        # make API calls here
        ...

    def cache_path(self, series: str) -> Path:
        return self.data_dir / f"{series}.json"
```

### Experiment Pattern

Each experiment in `experiments/<name>/run.py` should:
1. Accept `--skip-fetch` flag to reuse cached data
2. Load data via `DataSource.load()` (never raw API calls)
3. Write results to `data/<name>/`
4. Be runnable as `uv run python -m experiments.<name>.run`

```python
# experiments/example/run.py
import argparse
from src.data.my_source import MySource

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()

    source = MySource(data_dir="data/example")
    if not args.skip_fetch or not source.is_cached(series="main"):
        data = source.fetch(series="main")
    else:
        data = source.load(series="main")

    # ... analysis ...

if __name__ == "__main__":
    main()
```

### Research Loop

The loop in `scripts/research_loop.sh`:
1. Reads `config.env` for project context
2. Runs a **critiquer** agent (reads paper + code, writes critique)
3. Runs a **researcher** agent (reads critique, writes code, updates paper)
4. Archives each iteration to `docs/exchanges/archive/`
5. Git-commits each phase

The prompts in `docs/researcher_prompt.md` and `docs/critique_prompt.md` use `{{TOPIC}}`, `{{DATA_SOURCE_NAME}}`, etc. as placeholders — the loop fills these in from `config.env` at runtime.

## Common Patterns

- **Phase-based pipelines**: Each experiment phase is independent. Cache expensive steps and skip with `--skip-*` flags.
- **Synthetic test data**: Unit tests use synthetic data only — no API calls, no downloads.
- **Data as the priority**: The loop is explicitly configured to prioritize expanding datasets over prose edits. Don't fight this — it's the right order.

## Credentials

Store API keys and credentials in `.env` (gitignored). Load with `python-dotenv`:

```python
from dotenv import load_dotenv
import os
load_dotenv()
API_KEY = os.environ["MY_API_KEY"]
```

## Adding a New Experiment

1. Create `experiments/<name>/` with `run.py` and `tests/test_unit.py`
2. Add its run command to this CLAUDE.md under Commands
3. Add a description under Architecture
4. Update `docs/findings.md` with any initial results
