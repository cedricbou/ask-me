# ask-me

An agent skill for framing development tasks through structured questioning before implementing —
all in a single conversation turn.

The idea: rushing into code when the spec is fuzzy produces rework. This skill slows you down
just enough to surface what's missing, then accelerates through implementation with full context.

## Install

```bash
npx skills add cedricbou/ask-me
```

Or for a specific agent:

```bash
npx skills add cedricbou/ask-me -a opencode
npx skills add cedricbou/ask-me -a claude-code
npx skills add cedricbou/ask-me -a cursor
npx skills add cedricbou/ask-me -a codex
```

### Verify installation

Start a new session and describe something you want to build:

> "I want to add a request-a-quote button to the homepage."

The agent should immediately start asking clarifying questions using the `question` tool —
**not** start writing code. That's the skill working correctly.

## What it does

1. **Asks clarifying questions** using the `question` tool — covering functional intent, edge
   cases, technical context, and blind spots you haven't thought of yet
2. **Proposes a path forward** once it has enough context: implement now, review the technical
   plan, keep clarifying, or stop and write the plan
3. **Shares a technical plan** if you want to review before any code is written
4. **Implements or documents** based on your choice — still in the same session

Everything happens in one turn. No context loss between framing and coding.

## When the skill triggers

The skill activates when you describe a development goal without a detailed spec. Examples:

```
I want to add a 'request a quote' CTA to this application.
```
```
Build me a notification system for order status updates.
```
```
We need to migrate auth from JWT to HttpOnly cookies.
```
```
Refactor the product catalog to support multiple currencies.
```
```
Je veux ajouter un système de commentaires sur les articles de blog.
```

It works in any language — the agent adapts to yours.

## Usage flow

```
User describes goal
    ↓
Agent asks clarifying questions (question tool)
    ↓
Agent feels ready → Offers choice (question tool):
    ├── Implement now
    ├── Review the technical plan first
    ├── Keep clarifying
    └── Stop and document the plan
         ↓
    [Review path] Agent shares plan → more question tool rounds → implement or stop
    [Implement path] Agent builds the feature
    [Document path] Agent writes the plan inline
```

## Repository structure

```
ask-me/
├── SKILL.md              # The skill — loaded by your agent
├── AGENTS.md             # Context for AI agents working on this repo
├── CONTRIBUTING.md       # How to contribute
├── CHANGELOG.md          # Version history
├── evals/
│   └── evals.json        # Eval scenarios with behavioral and qualitative assertions
├── scripts/
│   └── run_evals.py      # Eval runner (uv, Python 3.11+)
├── docs/
│   ├── skill-design.md   # Design decisions and intent
│   ├── contributing.md   # Detailed contribution guide
│   └── evals-guide.md    # How the eval system works
├── .github/
│   └── workflows/
│       └── release.yml   # Semantic release automation
├── LICENSE               # MIT
└── README.md
```

## Running evals

Requires [uv](https://docs.astral.sh/uv/) and an API key for your preferred provider.

```bash
# Anthropic (direct)
export ANTHROPIC_API_KEY=sk-ant-...
uv run scripts/run_evals.py

# OpenRouter
export OPENROUTER_API_KEY=sk-or-...
uv run scripts/run_evals.py

# ZenCode
export ZENCODE_API_KEY=...
uv run scripts/run_evals.py

# Custom OpenAI-compatible provider
export LLM_API_KEY=... LLM_BASE_URL=https://your-provider.com/v1 LLM_MODEL=your-model
uv run scripts/run_evals.py --provider custom

# Dry run — validate structure without any API call
uv run scripts/run_evals.py --dry-run
```

Other useful flags:

```bash
uv run scripts/run_evals.py --eval basic-feature-request-questioning  # one eval by name
uv run scripts/run_evals.py --eval 0                                   # one eval by ID
uv run scripts/run_evals.py --category questioning                     # by category
uv run scripts/run_evals.py --model anthropic/claude-opus-4-5          # override model
uv run scripts/run_evals.py --verbose                                  # show agent rounds
uv run scripts/run_evals.py --output results.json                      # save results to JSON
uv run scripts/run_evals.py --transcript transcripts/run.md            # write full Markdown transcript
```

See [docs/evals-guide.md](docs/evals-guide.md) for a full explanation of the eval system.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the short version, or
[docs/contributing.md](docs/contributing.md) for the detailed guide.

Commits follow [Conventional Commits](https://www.conventionalcommits.org/) — releases and
the CHANGELOG are automated via semantic-release on every push to `main`.

## Design decisions

See [docs/skill-design.md](docs/skill-design.md) for the reasoning behind key decisions:
why the skill uses the `question` tool exclusively, why there are no rigid MUST rules, and
what shouldn't change when contributing.

## License

MIT — see [LICENSE](LICENSE).
