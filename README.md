# ask-me

An agent skill for framing development tasks through structured questioning before implementing.

The idea: rushing into code when the spec is fuzzy produces rework. This skill slows you down
just enough to surface what's missing — then accelerates through implementation with full context.
All in a single conversation turn.

## What it does

When you describe a feature or task, the skill:

1. **Asks clarifying questions** using the `question` tool — covering functional intent, edge cases, technical context, and blind spots
2. **Proposes next steps** once it feels ready: implement, review the plan, keep clarifying, or document the plan
3. **Shares a technical plan** if you want to review before any code is written
4. **Implements or documents** based on your choice

Everything happens in one session — no context switching, no lost information.

## Install

```bash
npx skills add cedricbou/ask-me
```

Or for a specific agent:

```bash
npx skills add cedricbou/ask-me -a opencode
npx skills add cedricbou/ask-me -a claude-code
npx skills add cedricbou/ask-me -a cursor
```

## Usage

Just describe what you want to build:

```
I want to add a 'request a quote' CTA to this application.
```

```
Build me a notification system for order status updates.
```

```
We need to migrate auth from JWT to HttpOnly cookies.
```

The skill will take it from there.

## Running evals

Requires [uv](https://docs.astral.sh/uv/) and an `ANTHROPIC_API_KEY`.

```bash
# Run all evals
uv run scripts/run_evals.py

# Run a specific eval
uv run scripts/run_evals.py --eval 0
uv run scripts/run_evals.py --eval basic-feature-request-questioning

# Run a category
uv run scripts/run_evals.py --category questioning

# Dry run (validate structure without API calls)
uv run scripts/run_evals.py --dry-run

# Save results to file
uv run scripts/run_evals.py --output results.json
```

## Structure

```
ask-me/
├── SKILL.md              # The skill — loaded by your agent
├── evals/
│   └── evals.json        # Eval scenarios with assertions
├── scripts/
│   └── run_evals.py      # Eval runner (uv, Python 3.11+)
├── LICENSE               # MIT
└── README.md
```

## License

MIT
