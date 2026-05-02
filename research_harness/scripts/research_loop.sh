#!/usr/bin/env bash
# research_loop.sh — Automated researcher/critiquer feedback loop
#
# Usage:
#   ./scripts/research_loop.sh [max_iterations] [model]
#
# Examples:
#   ./scripts/research_loop.sh          # Uses defaults from config.env
#   ./scripts/research_loop.sh 8        # Up to 8 iterations
#   ./scripts/research_loop.sh 5 sonnet # Up to 5 iterations, sonnet
#
# Configure your project in config.env before running.
#
# Files:
#   docs/findings.md                      — The paper (modified by researcher)
#   docs/exchanges/critique_latest.md     — Latest critique
#   docs/exchanges/researcher_response.md — Latest researcher response
#   docs/exchanges/archive/               — All iterations archived

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── Load project config ────────────────────────────────────────────────────
if [ ! -f "$REPO_ROOT/config.env" ]; then
    echo "ERROR: config.env not found at $REPO_ROOT/config.env"
    echo "Copy config.env from the harness template and fill in your project details."
    exit 1
fi
source "$REPO_ROOT/config.env"

MAX_ITERATIONS="${1:-${MAX_ITERATIONS:-5}}"
MODEL="${2:-${MODEL:-opus}}"
EXCHANGES="$REPO_ROOT/docs/exchanges"
ARCHIVE="$EXCHANGES/archive"
LOGFILE="$ARCHIVE/research_loop.log"

mkdir -p "$ARCHIVE"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Logging helpers ────────────────────────────────────────────────────────
LOOP_START=$(date +%s)

log() {
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    local elapsed=$(( $(date +%s) - LOOP_START ))
    local mins=$(( elapsed / 60 ))
    local secs=$(( elapsed % 60 ))
    echo -e "${DIM}[${timestamp} +${mins}m${secs}s]${NC} $*"
    echo "[${timestamp} +${mins}m${secs}s] $(echo "$*" | sed 's/\x1b\[[0-9;]*m//g')" >> "$LOGFILE"
}

log_separator() {
    echo -e "${DIM}────────────────────────────────────────────────────────────${NC}"
}

file_stats() {
    local file="$1"
    local label="${2:-}"
    if [ -f "$file" ]; then
        local size lines words
        size=$(wc -c < "$file" | tr -d ' ')
        lines=$(wc -l < "$file" | tr -d ' ')
        words=$(wc -w < "$file" | tr -d ' ')
        log "  ${label}${CYAN}$(basename "$file")${NC}: ${words} words, ${lines} lines, ${size} bytes"
    else
        log "  ${label}${RED}$(basename "$file"): FILE NOT FOUND${NC}"
    fi
}

check_status() {
    local file="$1"
    local signal="$2"
    if [ -f "$file" ] && grep -q "^STATUS: $signal" "$file" 2>/dev/null; then
        return 0
    fi
    return 1
}

get_verdict() {
    if [ -f "$EXCHANGES/critique_latest.md" ]; then
        grep -E "^(REJECT|MAJOR REVISIONS|MINOR REVISIONS|ACCEPT)" "$EXCHANGES/critique_latest.md" 2>/dev/null | head -1 || echo "UNKNOWN"
    else
        echo "NONE"
    fi
}

git_commit() {
    local msg="$1"
    log "${CYAN}[Git] Staging changes...${NC}"
    cd "$REPO_ROOT"
    local status_output
    status_output=$(git status --short 2>&1)
    if [ -z "$status_output" ]; then
        log "${DIM}[Git] No changes to commit.${NC}"
        return 0
    fi
    local changed_count
    changed_count=$(echo "$status_output" | wc -l | tr -d ' ')
    log "${DIM}[Git] ${changed_count} file(s) changed:${NC}"
    echo "$status_output" | head -20 | while read -r line; do
        log "  ${DIM}$line${NC}"
    done
    git add -A
    if git commit -m "$msg" > /dev/null 2>&1; then
        local sha
        sha=$(git rev-parse --short HEAD)
        log "${GREEN}[Git] Committed: ${sha} — ${msg}${NC}"
    else
        log "${YELLOW}[Git] Commit skipped (nothing to commit).${NC}"
    fi
    # Push only if a remote is configured
    if git remote | grep -q .; then
        log "${CYAN}[Git] Pushing...${NC}"
        if git push 2>&1 | tail -2 | while read -r line; do log "  ${DIM}$line${NC}"; done; then
            log "${GREEN}[Git] Push successful.${NC}"
        else
            log "${YELLOW}[Git] Push failed — continuing without push.${NC}"
        fi
    else
        log "${DIM}[Git] No remote configured — skipping push.${NC}"
    fi
}

# ── Start ──────────────────────────────────────────────────────────────────
echo "" > "$LOGFILE"
log "${BLUE}${BOLD}======================================================${NC}"
log "${BLUE}${BOLD}  RESEARCH LOOP STARTED${NC}"
log "${BLUE}${BOLD}  Topic: $TOPIC${NC}"
log "${BLUE}${BOLD}  Paper: $PAPER_TITLE${NC}"
log "${BLUE}${BOLD}  Max iterations: $MAX_ITERATIONS | Model: $MODEL${NC}"
log "${BLUE}${BOLD}  Repo root: $REPO_ROOT${NC}"
log "${BLUE}${BOLD}======================================================${NC}"
echo ""

log "Pre-loop state:"
file_stats "$REPO_ROOT/docs/findings.md" "Paper: "
[ -f "$EXCHANGES/critique_latest.md" ] && file_stats "$EXCHANGES/critique_latest.md" "Last critique: "
[ -f "$EXCHANGES/researcher_response.md" ] && file_stats "$EXCHANGES/researcher_response.md" "Last response: "
log "  Archive files: $(ls -1 "$ARCHIVE" 2>/dev/null | wc -l | tr -d ' ')"
log "  Git branch: $(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo 'unknown')"
log "  Git HEAD: $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo 'unknown')"
log_separator
echo ""

FINAL_ITERATION=0

for i in $(seq 1 "$MAX_ITERATIONS"); do
    FINAL_ITERATION=$i
    ITER_START=$(date +%s)

    echo ""
    log "${YELLOW}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    log "${YELLOW}${BOLD}  ITERATION $i / $MAX_ITERATIONS${NC}"
    log "${YELLOW}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""

    # ── Phase 1: Critiquer ─────────────────────────────────────────────────
    log "${RED}${BOLD}[Phase 1: CRITIQUER]${NC}"
    PHASE_START=$(date +%s)

    HISTORY_CONTEXT=""
    if [ "$i" -gt 1 ]; then
        HISTORY_CONTEXT="This is iteration $i. Prior critiques are archived in docs/exchanges/archive/ (critique_1.md through critique_$((i-1)).md). Read the researcher's latest response at docs/exchanges/researcher_response.md — pay close attention to their pushbacks. Do NOT re-raise points already addressed or reasonably rejected."
    else
        HISTORY_CONTEXT="This is the first iteration — no prior exchanges exist. Address the seed questions in your prompt."
    fi

    CRITIQUE_PROMPT="$(cat "$REPO_ROOT/docs/critique_prompt.md")

$HISTORY_CONTEXT

Topic: $TOPIC
Paper title: $PAPER_TITLE
Research question: $RESEARCH_QUESTION
Primary data source: $DATA_SOURCE_NAME
Publication venue: $PUBLICATION_VENUE

Read docs/findings.md carefully. Review the experiment code in experiments/ and the data layer in src/data/ to understand what additional data is available. You can use Bash for read-only commands but do NOT modify any files except your critique.

Write your critique to docs/exchanges/critique_latest.md. Use iteration number $i in your header.

YOUR #1 PRIORITY every iteration is DATA SUFFICIENCY:
- Is the dataset large enough to support each claim? If not, CAN the researcher expand it by writing code?
- Do NOT let the researcher wave off 'small n' as inherent. If they have access to more data via $DATA_SOURCE_NAME, expanding the dataset is the #1 recommendation.
- Before ANY prose or methods feedback, assess: would more data make this feedback irrelevant?

ALSO evaluate:
- STRENGTH: Are claims as strong as evidence allows?
- NOVELTY: What's genuinely new? What new analyses would increase novelty?
- ROBUSTNESS: Missing checks? Hostile reviewer attacks? Code bugs?

IMPORTANT: Do NOT set STATUS: ACCEPT. A weakness is ONLY 'unfixable' if no code could address it."

    log "  Prompt length: ${#CRITIQUE_PROMPT} chars"
    log "  Allowed tools: Read, Write, Glob, Grep, Bash"
    log "  Max turns: 20"
    log "  ${MAGENTA}Invoking claude (critiquer)...${NC}"

    cd "$REPO_ROOT"
    CLAUDE_START=$(date +%s)
    claude -p \
        --model "$MODEL" \
        --system-prompt "You are the critiquer agent reviewing research on $TOPIC. Your #1 job every iteration is the DATA SUFFICIENCY AUDIT: is the dataset large enough? Can the researcher expand it by writing code? A fixable weakness belongs in Must Fix, not Acknowledged Limitations. Review code for correctness and suggest new experiments. Write ONLY to docs/exchanges/critique_latest.md — do NOT modify any other files." \
        --allowed-tools "Read,Write,Glob,Grep,Bash" \
        --max-turns 20 \
        --no-session-persistence \
        "$CRITIQUE_PROMPT" \
        > "$ARCHIVE/critique_${i}_log.txt" 2>&1
    CLAUDE_EXIT=$?
    CLAUDE_END=$(date +%s)
    CLAUDE_ELAPSED=$(( CLAUDE_END - CLAUDE_START ))

    log "  Claude exited with code ${BOLD}$CLAUDE_EXIT${NC} after ${BOLD}${CLAUDE_ELAPSED}s${NC} ($(( CLAUDE_ELAPSED / 60 ))m $(( CLAUDE_ELAPSED % 60 ))s)"
    file_stats "$ARCHIVE/critique_${i}_log.txt" "Agent log: "

    if [ -f "$EXCHANGES/critique_latest.md" ]; then
        cp "$EXCHANGES/critique_latest.md" "$ARCHIVE/critique_${i}.md"
        log "${GREEN}  Critique file written successfully.${NC}"
        file_stats "$EXCHANGES/critique_latest.md" "Critique: "

        log "  ${CYAN}Scores:${NC}"
        grep -E "^\|.*\|.*[0-9]+/10" "$EXCHANGES/critique_latest.md" 2>/dev/null | while read -r line; do
            log "    ${CYAN}$line${NC}"
        done

        VERDICT=$(get_verdict)
        log "  ${BOLD}Verdict: $VERDICT${NC}"

        PHASE_ELAPSED=$(( $(date +%s) - PHASE_START ))
        log "  Phase 1 total: ${PHASE_ELAPSED}s"
        log_separator

        git_commit "Iteration $i/$MAX_ITERATIONS: critiquer critique"
    else
        log "${RED}  FAILURE: No critique file produced!${NC}"
        log "${RED}  Check log: $ARCHIVE/critique_${i}_log.txt${NC}"
        tail -5 "$ARCHIVE/critique_${i}_log.txt" 2>/dev/null | while read -r line; do
            log "    ${DIM}$line${NC}"
        done
        PHASE_ELAPSED=$(( $(date +%s) - PHASE_START ))
        log "  Phase 1 total: ${PHASE_ELAPSED}s (FAILED)"
        log_separator
        continue
    fi

    # ── Phase 2: Researcher ────────────────────────────────────────────────
    echo ""
    log "${GREEN}${BOLD}[Phase 2: RESEARCHER]${NC}"
    PHASE_START=$(date +%s)

    cp "$REPO_ROOT/docs/findings.md" "$ARCHIVE/findings_before_${i}.md"
    BEFORE_WORDS=$(wc -w < "$REPO_ROOT/docs/findings.md" | tr -d ' ')
    BEFORE_LINES=$(wc -l < "$REPO_ROOT/docs/findings.md" | tr -d ' ')
    log "  Paper snapshot before: ${BEFORE_WORDS} words, ${BEFORE_LINES} lines"

    RESEARCHER_PROMPT="$(cat "$REPO_ROOT/docs/researcher_prompt.md")

Topic: $TOPIC
Paper title: $PAPER_TITLE
Research question: $RESEARCH_QUESTION
Primary data source: $DATA_SOURCE_NAME

This is iteration $i of a maximum $MAX_ITERATIONS. Read the critique at docs/exchanges/critique_latest.md.

YOUR #1 PRIORITY: If the critique identifies data insufficiency (too few observations, small n, underpowered tests), FIX IT WITH CODE BEFORE DOING ANYTHING ELSE.
- Read src/data/ to understand what data is available from $DATA_SOURCE_NAME
- Fetch new data, run analyses on it, and add findings to the paper
- Adding even ONE more data series that confirms or breaks the central finding is worth more than any amount of prose polish

You have FULL access to the entire codebase. You can and should:
- Fetch new data from $DATA_SOURCE_NAME
- Create or modify ANY file — experiments, scripts, utilities
- Run experiments in experiments/
- Write new statistical tests, robustness checks, sensitivity analyses

PRIORITY ORDER: Data expansion > New analyses > Robustness checks > Prose edits.
Do NOT just edit prose — if a weakness is fixable with code, write the code.
Do NOT set STATUS: CONVERGED. Always attempt meaningful improvements.

Write deliberation to docs/exchanges/researcher_response.md. Update docs/findings.md with new results."

    log "  Prompt length: ${#RESEARCHER_PROMPT} chars"
    log "  Allowed tools: Read, Write, Edit, Glob, Grep, Bash, NotebookEdit"
    log "  Max turns: 50"
    log "  ${MAGENTA}Invoking claude (researcher)...${NC}"

    cd "$REPO_ROOT"
    CLAUDE_START=$(date +%s)
    claude -p \
        --model "$MODEL" \
        --system-prompt "You are the researcher agent working on $TOPIC. Your #1 priority is DATA SUFFICIENCY — if the study is underpowered, EXPAND THE DATASET before doing anything else. Fetch new data from $DATA_SOURCE_NAME, run analyses on it, add findings to the paper. Code that adds data > code that adds robustness checks > prose edits. Fix weaknesses with code, not hedging paragraphs. Write deliberation to docs/exchanges/researcher_response.md and update docs/findings.md." \
        --allowed-tools "Read,Write,Edit,Glob,Grep,Bash,NotebookEdit" \
        --max-turns 50 \
        --no-session-persistence \
        "$RESEARCHER_PROMPT" \
        > "$ARCHIVE/researcher_${i}_log.txt" 2>&1
    CLAUDE_EXIT=$?
    CLAUDE_END=$(date +%s)
    CLAUDE_ELAPSED=$(( CLAUDE_END - CLAUDE_START ))

    log "  Claude exited with code ${BOLD}$CLAUDE_EXIT${NC} after ${BOLD}${CLAUDE_ELAPSED}s${NC} ($(( CLAUDE_ELAPSED / 60 ))m $(( CLAUDE_ELAPSED % 60 ))s)"
    file_stats "$ARCHIVE/researcher_${i}_log.txt" "Agent log: "

    if [ -f "$EXCHANGES/researcher_response.md" ]; then
        cp "$EXCHANGES/researcher_response.md" "$ARCHIVE/researcher_response_${i}.md"
        cp "$REPO_ROOT/docs/findings.md" "$ARCHIVE/findings_after_${i}.md"
        log "${GREEN}  Researcher response written successfully.${NC}"
        file_stats "$EXCHANGES/researcher_response.md" "Response: "

        AFTER_WORDS=$(wc -w < "$REPO_ROOT/docs/findings.md" | tr -d ' ')
        AFTER_LINES=$(wc -l < "$REPO_ROOT/docs/findings.md" | tr -d ' ')
        WORD_DELTA=$(( AFTER_WORDS - BEFORE_WORDS ))
        LINE_DELTA=$(( AFTER_LINES - BEFORE_LINES ))
        WORD_SIGN=""; [ "$WORD_DELTA" -gt 0 ] && WORD_SIGN="+"
        LINE_SIGN=""; [ "$LINE_DELTA" -gt 0 ] && LINE_SIGN="+"
        log "  Paper after: ${AFTER_WORDS} words (${WORD_SIGN}${WORD_DELTA}), ${AFTER_LINES} lines (${LINE_SIGN}${LINE_DELTA})"

        if [ -f "$ARCHIVE/findings_before_${i}.md" ]; then
            DIFF_STAT=$(diff --stat "$ARCHIVE/findings_before_${i}.md" "$REPO_ROOT/docs/findings.md" 2>/dev/null | tail -1 || echo "no diff")
            log "  Diff stat: ${DIM}$DIFF_STAT${NC}"
        fi

        log "  ${CYAN}Key changes from response:${NC}"
        grep -E "^- " "$EXCHANGES/researcher_response.md" 2>/dev/null | head -8 | while read -r line; do
            log "    ${CYAN}$line${NC}"
        done

        if check_status "$EXCHANGES/researcher_response.md" "CONVERGED"; then
            log "${YELLOW}  Note: Researcher signaled CONVERGED but loop continues (no early exit mode).${NC}"
        fi

        PHASE_ELAPSED=$(( $(date +%s) - PHASE_START ))
        log "  Phase 2 total: ${PHASE_ELAPSED}s"
        log_separator
    else
        log "${RED}  FAILURE: No researcher response file produced!${NC}"
        log "${RED}  Check log: $ARCHIVE/researcher_${i}_log.txt${NC}"
        tail -5 "$ARCHIVE/researcher_${i}_log.txt" 2>/dev/null | while read -r line; do
            log "    ${DIM}$line${NC}"
        done
        PHASE_ELAPSED=$(( $(date +%s) - PHASE_START ))
        log "  Phase 2 total: ${PHASE_ELAPSED}s (FAILED)"
        log_separator
    fi

    # ── Git: commit each changed file individually ─────────────────────────
    cd "$REPO_ROOT"
    CHANGED_FILES=$(git status --short 2>/dev/null | awk '{print $2}')
    if [ -n "$CHANGED_FILES" ]; then
        echo "$CHANGED_FILES" | while read -r filepath; do
            git add "$filepath"
            git commit -m "Iteration $i/$MAX_ITERATIONS [researcher]: $filepath" > /dev/null 2>&1 || true
        done
        FILE_COUNT=$(echo "$CHANGED_FILES" | wc -l | tr -d ' ')
        log "${GREEN}[Git] Committed ${FILE_COUNT} file(s) individually.${NC}"
        if git remote | grep -q .; then
            log "${CYAN}[Git] Pushing all researcher commits...${NC}"
            git push 2>&1 | tail -2 | while read -r line; do log "  ${DIM}$line${NC}"; done && \
                log "${GREEN}[Git] Push successful.${NC}" || \
                log "${YELLOW}[Git] Push failed — continuing.${NC}"
        fi
    else
        log "${DIM}[Git] No researcher changes to commit.${NC}"
    fi

    ITER_ELAPSED=$(( $(date +%s) - ITER_START ))
    echo ""
    log "${BLUE}${BOLD}━━━ Iteration $i complete in ${ITER_ELAPSED}s ($(( ITER_ELAPSED / 60 ))m $(( ITER_ELAPSED % 60 ))s) ━━━${NC}"
    echo ""
done

# ── Final Summary ──────────────────────────────────────────────────────────
TOTAL_ELAPSED=$(( $(date +%s) - LOOP_START ))
TOTAL_MINS=$(( TOTAL_ELAPSED / 60 ))
TOTAL_SECS=$(( TOTAL_ELAPSED % 60 ))

echo ""
log "${BLUE}${BOLD}======================================================${NC}"
log "${BLUE}${BOLD}  RESEARCH LOOP COMPLETE${NC}"
log "${BLUE}${BOLD}  Iterations: $FINAL_ITERATION | Total time: ${TOTAL_MINS}m ${TOTAL_SECS}s${NC}"
log "${BLUE}${BOLD}======================================================${NC}"
echo ""
log "Final paper stats:"
file_stats "$REPO_ROOT/docs/findings.md" "Paper: "
echo ""
log "Outputs:"
log "  Paper:     docs/findings.md"
log "  Critique:  docs/exchanges/critique_latest.md"
log "  Response:  docs/exchanges/researcher_response.md"
log "  Full log:  $LOGFILE"
echo ""
log "Archive (per-iteration snapshots):"
ls -1 "$ARCHIVE" 2>/dev/null | sed 's/^/    /'
echo ""

git_commit "Research loop complete after $FINAL_ITERATION iteration(s)"
echo ""

if [ "$FINAL_ITERATION" -gt 1 ]; then
    log "${CYAN}${BOLD}Score progression across iterations:${NC}"
    for j in $(seq 1 "$FINAL_ITERATION"); do
        if [ -f "$ARCHIVE/critique_${j}.md" ]; then
            log "  ${BOLD}Iteration $j:${NC}"
            grep -E "^\|.*\|.*[0-9]+/10" "$ARCHIVE/critique_${j}.md" 2>/dev/null | while read -r line; do
                log "    $line"
            done
        fi
    done
    echo ""
fi

log "${CYAN}${BOLD}Timing summary:${NC}"
log "  Total elapsed: ${TOTAL_MINS}m ${TOTAL_SECS}s"
log "  Average per iteration: $(( TOTAL_ELAPSED / FINAL_ITERATION ))s"
log ""
log "${DIM}Full log saved to: $LOGFILE${NC}"
