#!/usr/bin/env python3
"""
Research Harness — CLI orchestrator for the researcher ↔ critiquer loop.

Usage:
    python harness.py init          # first-time setup wizard
    python harness.py               # start/resume loop
    python harness.py 8             # 8 iterations
    python harness.py 8 sonnet      # 8 iterations, sonnet model
    python harness.py --resume      # explicitly resume
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── ANSI colors ───────────────────────────────────────────────────────────────
RED    = '\033[0;31m'
GREEN  = '\033[0;32m'
BLUE   = '\033[0;34m'
YELLOW = '\033[1;33m'
CYAN   = '\033[0;36m'
BOLD   = '\033[1m'
DIM    = '\033[2m'
NC     = '\033[0m'

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
DOCS          = BASE / "docs"
EXCHANGES     = DOCS / "exchanges"
ARCHIVE       = EXCHANGES / "archive"
SUMMARIES     = DOCS / "summaries"
SESSION_FILE  = BASE / "session.json"
CONFIG_FILE   = BASE / "config.env"


# ── Helpers ───────────────────────────────────────────────────────────────────

def c(color: str, text: str) -> str:
    """Wrap text in an ANSI color code."""
    return f"{color}{text}{NC}"


def print_banner(title: str, subtitle: str = "") -> None:
    width = 56
    print()
    print(c(CYAN, "═" * width))
    print(c(CYAN, "  ") + c(BOLD, title))
    if subtitle:
        print(c(CYAN, "  ") + c(DIM, subtitle))
    print(c(CYAN, "═" * width))
    print()


def read_file(path: Path) -> str:
    """Return file contents or empty string if missing."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_file(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def parse_config(path: Path) -> dict[str, str]:
    """Parse a key=value env file; skip comments and blanks; strip quotes."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        result[key] = value
    return result


def update_config(path: Path, updates: dict[str, str]) -> None:
    """Update or append keys in a key=value env file, preserving comments."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f'{key}="{updates[key]}"')
                updated_keys.add(key)
                continue
        new_lines.append(line)
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f'{key}="{value}"')
    write_file(path, "\n".join(new_lines) + "\n")


def read_multiline(prompt: str) -> str:
    """Prompt user for multiline input; blank line submits."""
    print(prompt)
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def ask(prompt: str) -> str:
    """Ask a single-line question."""
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def open_in_editor(path: Path) -> None:
    """Open a file in $EDITOR; fallback: print path and wait for Enter."""
    editor = os.environ.get("EDITOR", "")
    if editor:
        subprocess.run([editor, str(path)])
    else:
        print(c(YELLOW, f"  No $EDITOR set. Please edit the file manually:"))
        print(c(BOLD, f"    {path}"))
        ask("  Press Enter when done...")


def git_commit(message: str, files: list[str] | None = None) -> None:
    """Stage given files (or all) and commit. Silently skip if nothing to commit."""
    if files:
        for f in files:
            subprocess.run(
                ["git", "add", f], cwd=BASE, capture_output=True
            )
    else:
        subprocess.run(["git", "add", "-A"], cwd=BASE, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=BASE, capture_output=True, text=True
    )
    if result.returncode not in (0, 1):  # 1 = nothing to commit
        print(c(DIM, f"  git commit: {result.stderr.strip()}"))


def git_push() -> None:
    """Push to remote only if a remote is configured."""
    result = subprocess.run(
        ["git", "remote"], cwd=BASE, capture_output=True, text=True
    )
    if not result.stdout.strip():
        return
    push = subprocess.run(
        ["git", "push"], cwd=BASE, capture_output=True, text=True
    )
    if push.returncode != 0:
        print(c(DIM, f"  git push failed (non-fatal): {push.stderr.strip()}"))


def elapsed_str(started_at: str) -> str:
    """Human-readable elapsed time since ISO timestamp."""
    try:
        start = datetime.fromisoformat(started_at)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - start
        total = int(delta.total_seconds())
        h, rem = divmod(total, 3600)
        m, s   = divmod(rem, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"
    except Exception:
        return "?"


# ── Session ───────────────────────────────────────────────────────────────────

def load_session() -> dict:
    if SESSION_FILE.exists():
        with open(SESSION_FILE) as f:
            return json.load(f)
    return {}


def save_session(session: dict) -> None:
    with open(SESSION_FILE, "w") as f:
        json.dump(session, f, indent=2)


def new_session(run_idx: int, max_iterations: int, model: str) -> dict:
    return {
        "run_idx": run_idx,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "current_iteration": 0,
        "max_iterations": max_iterations,
        "model": model,
        "pending_steering": None,
        "steering_history": [],
        "scores": [],
        "verdicts": [],
        "word_counts": [],
    }


# ── Agent subprocess ──────────────────────────────────────────────────────────

def run_agent(
    prompt: str,
    system_prompt: str,
    model: str,
    allowed_tools: str,
    max_turns: int,
    log_path: Path,
) -> int:
    """
    Run a claude -p subprocess, stream stdout to terminal (DIM) and log file.
    Prompt is passed via stdin to avoid ARG_MAX limits on large prompts.
    Returns the exit code.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Pass prompt via stdin (no positional arg) to avoid OS argument length limits.
    # claude -p with no positional prompt reads from stdin.
    cmd = [
        "claude", "-p",
        "--model", model,
        "--system-prompt", system_prompt,
        "--allowed-tools", allowed_tools,
        "--max-turns", str(max_turns),
        "--no-session-persistence",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=BASE,
        )
    except FileNotFoundError:
        print(c(RED, "  ERROR: 'claude' CLI not found. Is Claude Code installed?"))
        return 1

    assert proc.stdin is not None
    proc.stdin.write(prompt)
    proc.stdin.close()

    with open(log_path, "w", encoding="utf-8") as log_f:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(c(DIM, line))
            sys.stdout.flush()
            log_f.write(line)

    proc.wait()
    return proc.returncode


# ── Score / verdict parsing ───────────────────────────────────────────────────

SCORE_CRITERIA = [
    "Data Sufficiency",
    "Novelty",
    "Methodological Rigor",
    "Practical Significance",
    "Publication Readiness",
]

# Short display labels (≤20 chars)
SCORE_LABELS = [
    "Data Sufficiency",
    "Novelty",
    "Methodological Rigor",
    "Practical Signif.",
    "Publication Ready",
]


def parse_scores(text: str) -> dict[str, int | None]:
    """Extract scores from a markdown table like: | Data Sufficiency | 7/10 | ... |"""
    scores: dict[str, int | None] = {c: None for c in SCORE_CRITERIA}
    for criterion in SCORE_CRITERIA:
        # Match: | Criterion | N/10 | ... |
        pattern = rf"\|\s*{re.escape(criterion)}\s*\|\s*(\d+)/10"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            scores[criterion] = int(m.group(1))
    return scores


def parse_verdict(text: str) -> str:
    """Extract REJECT / MAJOR REVISIONS / MINOR REVISIONS / ACCEPT from text."""
    for line in text.splitlines():
        m = re.match(
            r"^(REJECT|MAJOR REVISIONS|MINOR REVISIONS|ACCEPT)\b",
            line.strip(),
            re.IGNORECASE,
        )
        if m:
            return m.group(1).upper()
    return "—"


def word_count(path: Path) -> int:
    text = read_file(path)
    return len(text.split())


def extract_section_bullets(text: str, section_names: list[str], n: int = 5) -> list[str]:
    """
    Extract the first `n` bullet/numbered items from named sections.
    Tries each section name in order; stops at the first non-empty match.
    """
    for name in section_names:
        pattern = rf"##\s+{re.escape(name)}.*?\n(.*?)(?=\n##|\Z)"
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not m:
            continue
        body = m.group(1)
        bullets = [
            ln.strip()
            for ln in body.splitlines()
            if ln.strip() and (
                ln.strip().startswith("-")
                or ln.strip().startswith("*")
                or re.match(r"^\d+\.", ln.strip())
            )
        ]
        if bullets:
            return bullets[:n]
    return []


# ── Checkpoint display ────────────────────────────────────────────────────────

def render_checkpoint(session: dict, i: int, cfg: dict) -> None:
    model        = session["model"]
    max_iters    = session["max_iterations"]
    elapsed      = elapsed_str(session["started_at"])
    scores_hist  = session["scores"]        # list of dicts
    verdicts     = session["verdicts"]
    wc_list      = session["word_counts"]

    current_scores = scores_hist[-1] if scores_hist else {}
    prev_scores    = scores_hist[-2] if len(scores_hist) >= 2 else {}
    current_wc     = wc_list[-1] if wc_list else 0
    prev_wc        = wc_list[-2] if len(wc_list) >= 2 else 0
    verdict        = verdicts[-1] if verdicts else "—"

    print()
    print(c(CYAN, "═" * 56))
    print(c(BOLD, f"  ITERATION {i} / {max_iters}  ·  {elapsed}  ·  {model}"))
    print(c(CYAN, "═" * 56))
    print()

    # Scores table
    print(c(BOLD, "  SCORES"))
    print("  ┌──────────────────────┬───────┬───────┐")
    print("  │ Criterion            │ Now   │ Delta │")
    print("  ├──────────────────────┼───────┼───────┤")
    for criterion, label in zip(SCORE_CRITERIA, SCORE_LABELS):
        now_val  = current_scores.get(criterion)
        prev_val = prev_scores.get(criterion)
        now_str  = f"{now_val}/10" if now_val is not None else "  —  "
        if now_val is not None and prev_val is not None:
            delta = now_val - prev_val
            delta_str = f"{delta:+d}"
            delta_color = GREEN if delta > 0 else (RED if delta < 0 else DIM)
            delta_disp = c(delta_color, f"{delta_str:>5}")
        else:
            delta_disp = c(DIM, "   — ")
        label_padded = f"{label:<20}"
        now_padded   = f"{now_str:^5}"
        print(f"  │ {label_padded} │ {now_padded} │{delta_disp} │")
    print("  └──────────────────────┴───────┴───────┘")

    wc_delta = current_wc - prev_wc
    wc_color = GREEN if wc_delta > 0 else (RED if wc_delta < 0 else DIM)
    verdict_color = (
        GREEN if verdict == "ACCEPT"
        else RED if verdict == "REJECT"
        else YELLOW
    )
    print(
        f"  Verdict: {c(verdict_color, verdict)}   "
        f"Paper: {current_wc} words ({c(wc_color, f'{wc_delta:+d}')})"
    )
    print()

    # Critiquer top points
    critique_text = read_file(EXCHANGES / "critique_latest.md")
    crit_bullets = extract_section_bullets(
        critique_text,
        ["Must Fix", "Should Fix", "Other Issues"],
        n=5,
    )
    print(c(BOLD, "  CRITIQUER — Top Points"))
    if crit_bullets:
        for b in crit_bullets:
            print(f"    {b}")
    else:
        print(c(DIM, "    (no bullet points found)"))
    print()

    # Researcher what changed
    researcher_text = read_file(EXCHANGES / "researcher_response.md")
    res_bullets = extract_section_bullets(
        researcher_text,
        ["Paper Changes", "Code Changes"],
        n=5,
    )
    print(c(BOLD, "  RESEARCHER — What Changed"))
    if res_bullets:
        for b in res_bullets:
            print(f"    {b}")
    else:
        print(c(DIM, "    (no bullet points found)"))
    print()

    print(c(DIM, "─" * 56))
    if i < max_iters:
        print(c(BOLD, "  [Enter] next iteration   [s] steer   [q] quit"))
    else:
        print(c(BOLD, "  [Enter] generate summary   [s] steer   [q] quit"))
    print()


# ── Steering ──────────────────────────────────────────────────────────────────

def handle_steering(session: dict) -> dict:
    print()
    print(c(YELLOW, "  Steer next iteration (blank line to submit):"))
    note = read_multiline("> ")
    if not note.strip():
        print(c(DIM, "  No steering note entered."))
        return session

    changes_direction = ask("  Does this change the research direction? [y/n] ").lower()
    if changes_direction == "y":
        brief_path = DOCS / "research_brief.md"
        print(c(YELLOW, f"  Opening research_brief.md for editing..."))
        open_in_editor(brief_path)
        # Preview
        lines = read_file(brief_path).splitlines()
        print()
        print(c(BOLD, "  Preview (first 3 lines):"))
        for ln in lines[:3]:
            print(f"    {ln}")
        confirm = ask("  Looks good? [Enter] to continue, 'edit' to revise: ").lower()
        while confirm == "edit":
            open_in_editor(brief_path)
            lines = read_file(brief_path).splitlines()
            print()
            for ln in lines[:3]:
                print(f"    {ln}")
            confirm = ask("  Looks good? [Enter] to continue, 'edit' to revise: ").lower()

    session["pending_steering"] = note.strip()
    if "steering_history" not in session:
        session["steering_history"] = []
    session["steering_history"].append({
        "iteration": session["current_iteration"],
        "note": note.strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    save_session(session)
    print(c(GREEN, "  Steering note saved."))
    return session


# ── Build score progression table ─────────────────────────────────────────────

def build_score_table(scores_list: list[dict]) -> str:
    if not scores_list:
        return "(no scores recorded)"
    header = "| Criterion | " + " | ".join(f"Iter {i+1}" for i in range(len(scores_list))) + " |"
    sep    = "|" + "---|" * (len(scores_list) + 1)
    rows = []
    for criterion in SCORE_CRITERIA:
        cells = [criterion]
        for s in scores_list:
            val = s.get(criterion)
            cells.append(f"{val}/10" if val is not None else "—")
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, sep] + rows)


# ── Init command ──────────────────────────────────────────────────────────────

def cmd_init() -> None:
    print_banner("Research Harness: Quick Setup", "Answer each question to configure your project.")

    # Step 1: Interview
    print(c(BOLD, "Step 1 of 5: Research Interview"))
    print()

    research_question = ask("Central research question this paper answers?\n> ")
    topic             = ask("\nDomain / topic (one phrase)?\n> ")
    venue             = ask("\nWhere will this be published?\n> ")
    background        = read_multiline("\nBackground — why does this matter? (blank line to submit)")
    hypotheses        = read_multiline("\nWhat do you expect to find? (blank line to submit)")
    definition_of_done = read_multiline("\nWhat would make this paper 'done'? (blank line to submit)")
    uses_apis         = ask("\nDoes this project access any external APIs? [y/n] ").lower()

    # Write research_brief.md
    brief = f"""# Research Brief

## Central Question
{research_question}

## Domain
{topic}

## Publication Target
{venue}

## Background & Motivation
{background}

## Hypotheses
{hypotheses}

## Definition of Done
{definition_of_done}
"""
    write_file(DOCS / "research_brief.md", brief)
    print(c(GREEN, f"\n  Wrote docs/research_brief.md"))

    # Update config.env
    update_config(CONFIG_FILE, {
        "TOPIC": topic,
        "RESEARCH_QUESTION": research_question,
        "PUBLICATION_VENUE": venue,
    })
    print(c(GREEN, f"  Updated config.env"))

    # Step 2: API setup
    if uses_apis == "y":
        print()
        print(c(BOLD, "Step 2 of 5: API Setup"))
        print()

        api_name    = ask("API name:\n> ")
        base_url    = ask("Base URL:\n> ")
        print("Authentication method:")
        print("  [1] API key in header")
        print("  [2] Bearer token")
        print("  [3] RSA-signed requests")
        print("  [4] OAuth")
        print("  [5] Other (describe)")
        auth_choice = ask("Choice [1-5]: ").strip()

        auth_descriptions = {
            "1": "API key in header",
            "2": "Bearer token",
            "3": "RSA-signed requests",
            "4": "OAuth",
        }
        if auth_choice in auth_descriptions:
            auth_description = auth_descriptions[auth_choice]
        else:
            auth_description = ask("Describe authentication: ")

        cred_vars_raw = ask("Which environment variables hold credentials? (comma-separated):\n> ")
        credential_vars = [v.strip() for v in cred_vars_raw.split(",") if v.strip()]

        # Write .env template
        env_path = BASE / ".env"
        env_lines = [f"# {api_name} credentials"] + [f'{v}=""' for v in credential_vars]
        env_content = "\n".join(env_lines) + "\n"
        write_file(env_path, env_content)
        print(c(GREEN, f"\n  Wrote .env template:"))
        print(c(DIM, env_content))
        ask("  Add your credentials to .env then press Enter to continue...")

        snake_name = re.sub(r"[^a-z0-9]+", "_", api_name.lower()).strip("_")

        client_prompt = (
            f"Write a minimal API client for {api_name} in src/data/{snake_name}.py "
            f"implementing the DataSource ABC from src/data/base.py. "
            f"Auth: {auth_description}. "
            f"Credentials from .env: {', '.join(credential_vars)}. "
            f"Base URL: {base_url}. "
            f"Then write a minimal first experiment in experiments/{snake_name}_first/run.py "
            f"that uses this client to fetch one small dataset and print its shape/size. "
            f"Run the experiment to verify it works end to end. "
            f"Report clearly: SUCCESS or FAILURE and why."
        )
        client_system = f"You are setting up a data client for {api_name}."

        cfg = parse_config(CONFIG_FILE)
        model = cfg.get("MODEL", "opus")

        print()
        print(c(BOLD, "  Running API setup agent..."))
        log_path = ARCHIVE / "api_setup_log.txt"

        run_agent(
            prompt=client_prompt,
            system_prompt=client_system,
            model=model,
            allowed_tools="Read,Write,Edit,Bash,Glob,Grep",
            max_turns=15,
            log_path=log_path,
        )

        while True:
            resp = ask("\nConnection successful? [Enter] to continue, 'retry' to try again, 'skip' to continue anyway: ").lower()
            if resp == "retry":
                run_agent(
                    prompt=client_prompt,
                    system_prompt=client_system,
                    model=model,
                    allowed_tools="Read,Write,Edit,Bash,Glob,Grep",
                    max_turns=15,
                    log_path=log_path,
                )
            else:
                break
    else:
        print()
        print(c(DIM, "  Skipping API setup."))

    # Step 3: Taste review
    print()
    print(c(BOLD, "Step 3 of 5: Style Guide (taste.md)"))
    print(c(DIM, "  taste.md controls how summaries are written."))
    taste_path = DOCS / "taste.md"
    if not taste_path.exists():
        write_file(taste_path, "<!-- Describe your preferred tone, format, audience, and what to emphasize in summaries. This file is read by the summarizer agent when writing docs/summaries/summary_N.md. -->\n")
    open_in_editor(taste_path)
    lines = read_file(taste_path).splitlines()
    print(c(BOLD, "  Preview (first 3 lines):"))
    for ln in lines[:3]:
        print(f"    {ln}")
    confirm = ask("  Looks good? [Enter] to continue, 'edit' to revise: ").lower()
    while confirm == "edit":
        open_in_editor(taste_path)
        lines = read_file(taste_path).splitlines()
        for ln in lines[:3]:
            print(f"    {ln}")
        confirm = ask("  Looks good? [Enter] to continue, 'edit' to revise: ").lower()

    # Step 4: Prompt review
    print()
    print(c(BOLD, "Step 4 of 5: Prompt Review"))
    print()
    for prompt_path, label in [
        (DOCS / "researcher_prompt.md", "researcher_prompt.md"),
        (DOCS / "critique_prompt.md",   "critique_prompt.md"),
    ]:
        print(c(DIM, f"  Reviewing {label}..."))
        open_in_editor(prompt_path)
        lines = read_file(prompt_path).splitlines()
        print(c(BOLD, f"  Preview of {label} (first 3 lines):"))
        for ln in lines[:3]:
            print(f"    {ln}")
        confirm = ask("  Looks good? [Enter] to continue, 'edit' to revise: ").lower()
        while confirm == "edit":
            open_in_editor(prompt_path)
            lines = read_file(prompt_path).splitlines()
            for ln in lines[:3]:
                print(f"    {ln}")
            confirm = ask("  Looks good? [Enter] to continue, 'edit' to revise: ").lower()
        print()

    # Step 5: Instructions
    print(c(BOLD, "Step 5 of 5: Done"))
    print()
    print(c(GREEN, "  Setup complete. Start the loop:"))
    print(c(BOLD,  "    python harness.py"))
    print(c(BOLD,  "    python harness.py 8"))
    print(c(BOLD,  "    python harness.py 8 sonnet"))
    print()


# ── Main loop ─────────────────────────────────────────────────────────────────

def cmd_run(max_iterations: int | None, model: str | None, resume: bool) -> None:
    cfg = parse_config(CONFIG_FILE)

    topic   = cfg.get("TOPIC", "your research topic")
    venue   = cfg.get("PUBLICATION_VENUE", "your research blog or journal")
    title   = cfg.get("PAPER_TITLE", "Untitled")
    default_model = cfg.get("MODEL", "opus")
    default_iters = int(cfg.get("MAX_ITERATIONS", "5"))

    # Resolve model and max_iterations
    effective_model = model or default_model
    effective_iters = max_iterations or default_iters

    # Load or create session
    session = load_session()

    if resume or (session and session.get("current_iteration", 0) < session.get("max_iterations", 0)):
        # Resume existing session
        if session:
            if session["current_iteration"] >= session["max_iterations"]:
                # Already complete — start new run
                session = new_session(
                    run_idx=session.get("run_idx", 0) + 1,
                    max_iterations=effective_iters,
                    model=effective_model,
                )
            else:
                # Override model/iters only if explicitly provided
                if model:
                    session["model"] = model
                if max_iterations:
                    session["max_iterations"] = max_iterations
        else:
            session = new_session(run_idx=1, max_iterations=effective_iters, model=effective_model)
    else:
        # Start fresh
        run_idx = session.get("run_idx", 0) + 1 if session else 1
        session = new_session(run_idx=run_idx, max_iterations=effective_iters, model=effective_model)

    save_session(session)
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    SUMMARIES.mkdir(parents=True, exist_ok=True)

    run_idx    = session["run_idx"]
    max_iters  = session["max_iterations"]
    agent_model = session["model"]
    start_iter = session["current_iteration"]

    print_banner(
        f"Research Harness — Run {run_idx}",
        f"{topic} · {title} · {agent_model} · {max_iters} iterations",
    )

    # ── Main iteration loop ────────────────────────────────────────────────────

    for i in range(start_iter + 1, max_iters + 1):
        print()
        print(c(BOLD + BLUE, f"  ── Iteration {i} / {max_iters} ──"))
        print()

        brief_text   = read_file(DOCS / "research_brief.md")
        critiquer_pm = read_file(DOCS / "critique_prompt.md")
        researcher_pm = read_file(DOCS / "researcher_prompt.md")

        # ── Phase 1: Critiquer ────────────────────────────────────────────────
        print(c(YELLOW, f"  [Phase 1] Critiquer..."))

        if i == 1:
            history_ctx = "This is the first iteration — no prior exchanges exist."
        else:
            history_ctx = (
                f"This is iteration {i}. Prior critiques are archived in "
                f"docs/exchanges/archive/ (critique_1.md through critique_{i-1}.md). "
                f"Read the researcher's latest response at docs/exchanges/researcher_response.md. "
                f"Do NOT re-raise points already addressed."
            )

        critique_prompt = "\n\n".join([
            brief_text,
            critiquer_pm,
            history_ctx,
            f"Write your critique to docs/exchanges/critique_latest.md. Use iteration number {i} in your header.",
        ])

        critique_system = (
            f"You are the critiquer agent reviewing research on {topic} for {venue}. "
            f"Cover: data sufficiency, novelty, methodological rigor, publishability at {venue}, "
            f"and reward hacking detection (did the researcher genuinely address prior feedback, "
            f"or just make it look addressed?). "
            f"Write ONLY to docs/exchanges/critique_latest.md — do NOT modify other files."
        )

        critique_log = ARCHIVE / f"critique_{i}_log.txt"
        rc = run_agent(
            prompt=critique_prompt,
            system_prompt=critique_system,
            model=agent_model,
            allowed_tools="Read,Write,Edit,Bash,Glob,Grep",
            max_turns=20,
            log_path=critique_log,
        )
        if rc != 0:
            print(c(RED, f"  WARNING: critiquer agent exited with code {rc}"))

        # Archive critique
        copy_file(EXCHANGES / "critique_latest.md", ARCHIVE / f"critique_{i}.md")

        git_commit(f"Iteration {i}/{max_iters}: critiquer")

        # ── Phase 2: Researcher ───────────────────────────────────────────────
        print()
        print(c(GREEN, f"  [Phase 2] Researcher..."))

        critique_text = read_file(EXCHANGES / "critique_latest.md")

        # Snapshot findings before
        copy_file(DOCS / "findings.md", ARCHIVE / f"findings_before_{i}.md")

        researcher_parts = [
            brief_text,
            researcher_pm,
        ]
        if critique_text:
            researcher_parts.append(critique_text)

        if session.get("pending_steering"):
            steering_section = (
                f"## Third-Party Steering Note (Before Iteration {i})\n"
                f"{session['pending_steering']}\n\n"
                f"This is an external perspective from the project author. "
                f"Weigh it alongside the critique above — it carries no special authority."
            )
            researcher_parts.append(steering_section)

        researcher_parts.append(
            f"This is iteration {i} of {max_iters}. "
            f"Write deliberation to docs/exchanges/researcher_response.md. "
            f"Update docs/findings.md with new results."
        )

        researcher_prompt_text = "\n\n".join(researcher_parts)

        researcher_system = (
            f"You are the researcher agent working on {topic}. "
            f"Data > methods > prose. Fix weaknesses with code, not hedging paragraphs. "
            f"Write deliberation to docs/exchanges/researcher_response.md and update docs/findings.md."
        )

        researcher_log = ARCHIVE / f"researcher_{i}_log.txt"
        rc = run_agent(
            prompt=researcher_prompt_text,
            system_prompt=researcher_system,
            model=agent_model,
            allowed_tools="Read,Write,Edit,Bash,Glob,Grep,NotebookEdit",
            max_turns=50,
            log_path=researcher_log,
        )
        if rc != 0:
            print(c(RED, f"  WARNING: researcher agent exited with code {rc}"))

        # Archive researcher outputs
        copy_file(EXCHANGES / "researcher_response.md", ARCHIVE / f"researcher_response_{i}.md")
        copy_file(DOCS / "findings.md", ARCHIVE / f"findings_after_{i}.md")

        # Clear pending steering
        session["pending_steering"] = None

        # Git commit each changed file individually
        changed_files = [
            str(EXCHANGES / "researcher_response.md"),
            str(DOCS / "findings.md"),
            str(ARCHIVE / f"researcher_response_{i}.md"),
            str(ARCHIVE / f"findings_after_{i}.md"),
            str(ARCHIVE / f"findings_before_{i}.md"),
        ]
        for fpath in changed_files:
            p = Path(fpath)
            if p.exists():
                rel = str(p.relative_to(BASE))
                subprocess.run(["git", "add", rel], cwd=BASE, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-m", f"Iteration {i}/{max_iters} [researcher]: {rel}"],
                    cwd=BASE, capture_output=True
                )

        # ── Parse scores, verdict, word count ─────────────────────────────────
        critique_latest = read_file(EXCHANGES / "critique_latest.md")
        scores  = parse_scores(critique_latest)
        verdict = parse_verdict(critique_latest)
        wc      = word_count(DOCS / "findings.md")

        if "scores" not in session:
            session["scores"] = []
        if "verdicts" not in session:
            session["verdicts"] = []
        if "word_counts" not in session:
            session["word_counts"] = []

        session["scores"].append(scores)
        session["verdicts"].append(verdict)
        session["word_counts"].append(wc)
        session["current_iteration"] = i
        save_session(session)

        # ── Checkpoint display ─────────────────────────────────────────────────
        render_checkpoint(session, i, cfg)

        # ── Interactive prompt ─────────────────────────────────────────────────
        while True:
            try:
                resp = sys.stdin.readline().strip().lower()
            except (EOFError, KeyboardInterrupt):
                resp = "q"

            if resp in ("q", "quit"):
                print(c(YELLOW, "\n  Exiting. Resume with: python harness.py --resume"))
                sys.exit(0)
            elif resp in ("s", "steer"):
                session = handle_steering(session)
                # Re-render prompt after steering
                if i < max_iters:
                    print(c(BOLD, "  [Enter] next iteration   [s] steer   [q] quit"))
                else:
                    print(c(BOLD, "  [Enter] generate summary   [s] steer   [q] quit"))
            else:
                break  # Enter or anything else → continue

    # ── Summarizer ────────────────────────────────────────────────────────────
    print()
    print(c(BOLD, "  Generating run summary..."))
    print()

    brief_text          = read_file(DOCS / "research_brief.md")
    summarizer_pm       = read_file(DOCS / "summarizer_prompt.md")
    taste_text          = read_file(DOCS / "taste.md")
    findings_text       = read_file(DOCS / "findings.md")
    critique_text       = read_file(EXCHANGES / "critique_latest.md")
    researcher_text     = read_file(EXCHANGES / "researcher_response.md")
    score_table         = build_score_table(session["scores"])

    if not taste_text.strip() or taste_text.strip().startswith("<!--"):
        taste_text = "No style guide provided — use clear, direct prose."

    summary_path = SUMMARIES / f"summary_{run_idx}.md"

    summarizer_parts = [
        brief_text,
        summarizer_pm,
        f"## Style Guide\n{taste_text}",
        f"## Current Findings\n{findings_text}",
        f"## Latest Critique\n{critique_text}",
        f"## Latest Researcher Response\n{researcher_text}",
        f"## Score Progression\n{score_table}",
        f"Write the summary to docs/summaries/summary_{run_idx}.md",
    ]

    summary_prompt = "\n\n".join(summarizer_parts)
    summary_system = f"You are summarizing a research run on {topic} for the project author."

    summary_log = ARCHIVE / f"summary_{run_idx}_log.txt"
    run_agent(
        prompt=summary_prompt,
        system_prompt=summary_system,
        model=agent_model,
        allowed_tools="Read,Write",
        max_turns=5,
        log_path=summary_log,
    )

    print()
    print(c(GREEN, f"  Summary written to docs/summaries/summary_{run_idx}.md"))

    git_commit(f"Run {run_idx} complete: {max_iters} iterations")
    git_push()

    print()
    print(c(BOLD + GREEN, f"  Run {run_idx} complete. {max_iters} iterations done."))
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]

    if args and args[0] == "init":
        cmd_init()
        return

    resume = False
    max_iterations: int | None = None
    model: str | None = None

    for arg in args:
        if arg == "--resume":
            resume = True
        elif arg.isdigit():
            max_iterations = int(arg)
        elif arg in ("opus", "sonnet", "haiku") or arg.startswith("claude-"):
            model = arg

    cmd_run(max_iterations=max_iterations, model=model, resume=resume)


if __name__ == "__main__":
    main()
