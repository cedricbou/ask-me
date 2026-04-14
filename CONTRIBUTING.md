# Contributing

Thanks for your interest in improving `ask-me`.

## Quick start

1. Fork the repo and create a branch
2. Read [AGENTS.md](AGENTS.md) for project context
3. Read [docs/contributing.md](docs/contributing.md) for the detailed workflow
4. Make your change and run the evals:
   ```bash
   uv run scripts/run_evals.py
   ```
5. Commit using [Conventional Commits](https://www.conventionalcommits.org/) — releases are automated
6. Open a pull request

## Commit format

```
feat: add gotchas section to SKILL.md
fix: confirmation question now always offers all four paths
docs: improve evals guide with assertion examples
test: add eval for multilingual confirmation step
refactor: reorganize Phase 3 instructions for clarity
```

Releases are automated via semantic-release:
- `feat:` → minor version bump
- `fix:` → patch version bump
- `feat!:` or `BREAKING CHANGE:` → major version bump

## What's in scope

- Improving the SKILL.md phrasing or structure
- Adding new eval scenarios to `evals/evals.json`
- Improving the eval runner (`scripts/run_evals.py`)
- Fixing documentation

## What needs a discussion first

- Changing the four-phase structure of the skill
- Removing the `question` tool requirement
- Renaming the skill
- Adding a `references/` or `scripts/` dependency to the skill

Open an issue before working on these.
