# Evals Guide

This document explains how the `ask-me` eval system works, how to interpret results,
and how to write good assertions.

---

## Overview

The eval system validates that the skill produces the correct agent *behavior* — specifically,
that the agent uses the `question` tool at the right moments and in the right sequence.

Evals are not LLM-graded rubrics. They're structured behavioral tests with programmatic
assertion checks, supplemented by qualitative text scans.

---

## Running evals

The runner auto-detects your provider from environment variables (first match wins):

| Provider | Env var | Notes |
|---|---|---|
| Anthropic direct | `ANTHROPIC_API_KEY` | Direct API |
| OpenRouter | `OPENROUTER_API_KEY` | Access any model via OpenRouter |
| ZenCode | `ZENCODE_API_KEY` | ZenCode API |
| Custom | `LLM_API_KEY` + `LLM_BASE_URL` + `LLM_MODEL` | Any OpenAI-compatible endpoint |

```bash
# OpenRouter
export OPENROUTER_API_KEY=sk-or-...
uv run scripts/run_evals.py

# Anthropic direct
export ANTHROPIC_API_KEY=sk-ant-...
uv run scripts/run_evals.py

# Force a specific provider
uv run scripts/run_evals.py --provider openrouter

# Override the model
uv run scripts/run_evals.py --model anthropic/claude-opus-4-5

# One eval by name or ID
uv run scripts/run_evals.py --eval basic-feature-request-questioning
uv run scripts/run_evals.py --eval 0

# By category
uv run scripts/run_evals.py --category questioning
uv run scripts/run_evals.py --category confirmation
uv run scripts/run_evals.py --category review
uv run scripts/run_evals.py --category implementation
uv run scripts/run_evals.py --category documentation
uv run scripts/run_evals.py --category ux

# Dry run — validate evals.json structure without API calls
uv run scripts/run_evals.py --dry-run

# Verbose — see each round of agent interaction
uv run scripts/run_evals.py --verbose

# Save results to JSON
uv run scripts/run_evals.py --output results.json

# Write a human-readable Markdown transcript of every session
uv run scripts/run_evals.py --transcript transcripts/run.md
```

Exit code: `0` if all evals pass, `1` if any fail.

### GitHub Actions secret setup

Add your API key as a repository secret:
**Settings → Secrets and variables → Actions → New repository secret**

| Secret name | For provider |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic direct |
| `OPENROUTER_API_KEY` | OpenRouter |
| `ZENCODE_API_KEY` | ZenCode |
| `LLM_API_KEY` | Custom (also set `LLM_BASE_URL` and `LLM_MODEL` in the workflow) |

The CI workflow auto-detects which secret is set and runs evals accordingly. If no secret
is configured, it falls back to dry-run mode.

---

## How an eval runs

For each scenario in `evals/evals.json`:

1. The skill is loaded from `SKILL.md` and injected into a system prompt
2. The agent is given the eval `prompt` as the first user message
3. The agent responds — possibly calling tools (question, Write, Edit, Bash, Read)
4. If the agent calls the `question` tool, a simulated user response is fed back
   (from `SIMULATED_USER_RESPONSES` in `run_evals.py`)
5. This continues for up to `MAX_AGENTIC_ROUNDS` rounds
6. All tool calls and text output are collected
7. Each assertion in the eval is checked against that evidence

The model used is `claude-opus-4-5`. This matters — the description field should be
calibrated to the model that will actually run the skill.

---

## evals.json schema

```json
{
  "skill_name": "ask-me",
  "version": "1.0.0",
  "description": "...",
  "evals": [
    {
      "id": 0,
      "name": "descriptive-kebab-case-name",
      "category": "questioning|confirmation|review|implementation|documentation|ux",
      "prompt": "The user message that triggers the skill",
      "setup": "(optional) Context to inject — simulates a mid-session state",
      "assertions": [
        {
          "id": "unique-assertion-id",
          "description": "Human-readable description of what this checks",
          "type": "behavioral|qualitative",
          "check": "Natural language description of the check logic"
        }
      ]
    }
  ]
}
```

### The `setup` field

`setup` is injected into the system prompt before the eval runs. Use it to simulate
a mid-session state — e.g., "The agent has already asked one round of questions and received
answers: [...]". This lets you test later-phase behavior (confirmation, review, implementation)
without running the full questioning flow each time.

---

## Assertion types

### `behavioral` assertions

Check the sequence of tool calls. The runner tracks which tools were called (question, Write,
Edit, Bash, Read) and in what order.

Current behavioral assertion IDs and what they check:

| Assertion ID | Checks |
|---|---|
| `uses-question-tool` | `question` was called before any Write/Edit/Bash |
| `no-premature-implementation` | No Write/Edit/Bash before the first `question` call |
| `confirmation-uses-question-tool` | A `question` call has ≥3 options (confirmation step) |
| `offers-all-four-paths` | A `question` call includes options for: implement, review, clarify, stop |
| `no-implementation-before-confirmation` | No Write/Edit/Bash before the second `question` call |
| `review-uses-question-tool` | At least 2 `question` calls total (clarification + review) |
| `review-offers-implement-path` | Review-phase `question` calls include an "implement" option |
| `no-implementation-during-review` | No Write/Edit between second and last `question` calls |
| `no-redundant-questions` | No `question` calls after implementation has started |
| `implementation-is-targeted` | At least one Write or Edit call was made |
| `no-implementation-on-stop` | No Write/Edit/Bash calls when user chooses stop+document |
| `still-uses-question-tool` | `question` was called at least once |

### `qualitative` assertions

Scan the agent's text output for domain-specific keywords. These are inherently less precise
than behavioral checks — they catch obvious misses (e.g., a plan that never mentions the
technology in question) but won't catch subtle quality issues.

Current qualitative assertion IDs:

| Assertion ID | Checks for |
|---|---|
| `questions-are-relevant` | Both functional AND technical keywords in output |
| `options-are-concrete` | At least one domain term in options text |
| `plan-is-structured` | Plan references files, approach, design decisions |
| `plan-document-is-complete` | Intent, technical approach, and open questions present |
| `plan-is-actionable` | Auth-specific technical terms (for the JWT→cookies eval) |
| `uses-gathered-context` | React Query, isFetching, Spinner keywords (for the implement eval) |
| `communicates-in-user-language` | French language markers (for the language-adaptation eval) |

---

## Writing good assertions

### Behavioral assertions are the most reliable

When you want to test "the agent should do X before Y", write a behavioral assertion.
The tool call sequence is a fact — it doesn't depend on phrasing or model variance.

Good candidates for behavioral assertions:
- Order of operations (question before code)
- Presence of a specific tool call type
- Count of tool calls meeting a condition (≥3 options, ≥2 rounds)
- Absence of tool calls (no writes during review)

### Qualitative assertions fill the gaps

Use qualitative assertions when you need to check something about the *content* of the agent's
output that behavioral checks can't capture — like whether the questions asked are actually
relevant to the domain, or whether the plan mentions the right technical concepts.

Tips for writing qualitative assertions:
- Use keywords that would appear in any reasonable output for this domain
- Don't check for exact strings — check for semantic concepts via multiple synonyms
- Accept partial evidence: `any(kw in output for kw in ["approach", "implement", "technical", "how"])`
- If an assertion fails too often on valid outputs, it's too strict — widen the keyword set
- If it always passes even on bad outputs, it's too loose — add more specific terms

### A note on variance

LLM outputs are non-deterministic. An eval that passes 90% of the time is not a good eval —
it means the behavior is borderline. Good evals should pass or fail consistently.

If an eval is flaky:
1. Run it with `--verbose` to inspect what the agent is doing
2. Check whether the assertion captures the right signal
3. Consider whether the behavior itself is underspecified in SKILL.md

---

## Adding a new eval scenario

1. Choose a scenario that tests a path not yet covered (or a known regression)
2. Add it to `evals/evals.json` with a unique `id` (increment from last), a descriptive
   kebab-case `name`, and the appropriate `category`
3. Write `assertions` — prefer behavioral assertions, supplement with qualitative
4. Add simulated user responses to `SIMULATED_USER_RESPONSES` in `scripts/run_evals.py`:
   ```python
   "your-eval-name": [
       "First user response (after agent's first question round)",
       "Second user response (if needed)",
   ],
   ```
5. Run `uv run scripts/run_evals.py --dry-run` to validate structure
6. Run `uv run scripts/run_evals.py --eval your-eval-name --verbose` to inspect behavior
7. Iterate until the assertions correctly capture the expected behavior

---

## Reviewing transcripts manually

Automated assertions check structure and keywords — they can't tell you whether the *questions
the agent asked* were actually insightful, or whether the *plan* was well-reasoned. For that,
you need to read the conversation yourself.

Use `--transcript` to write a full Markdown transcript of every simulated session:

```bash
uv run scripts/run_evals.py --transcript transcripts/run.md

# Or for a single eval
uv run scripts/run_evals.py --eval 0 --transcript transcripts/eval-0.md
```

The transcript file is structured as one `##` section per eval. Each turn is rendered as:

- **`[USER]`** — the initial prompt and each simulated user response
- **`[TOOL: question]`** — the agent's question tool calls, with options expanded inline
- **`[TOOL: Write]` / `[TOOL: Edit]` etc.** — other tool calls with their arguments as JSON
- **`[AGENT]`** — any free-text the agent emitted outside of tool calls

Transcripts are gitignored (`transcripts/` and `*.transcript.md`) — they are for local
review only and should not be committed.

---

## Interpreting results

The eval report shows:

```
✓ PASS [0] basic-feature-request-questioning (questioning)
┌─────────────────────────────────────┬────┬──────────────────────────────────────┐
│ Assertion                           │    │ Evidence                             │
├─────────────────────────────────────┼────┼──────────────────────────────────────┤
│ Agent uses question tool before...  │ ✓  │ question tool called at indices [0]  │
│ No writes before questioning phase  │ ✓  │ No writes before questioning phase   │
│ Questions are relevant to domain    │ ✓  │ Found both functional and technical  │
└─────────────────────────────────────┴────┴──────────────────────────────────────┘
```

When an assertion fails, the `Evidence` column tells you what was found vs. expected:

```
│ Agent uses question tool before... │ ✗ │ Write/Edit appeared at index 0      │
│                                    │   │ before question at 3                │
```

This means the agent wrote a file before asking any questions — a regression in Phase 1.
