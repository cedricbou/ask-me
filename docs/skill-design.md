# Skill Design

This document explains the key design decisions behind `ask-me` — why the skill is structured
the way it is, what trade-offs were made, and what should not change when contributing.

---

## The core problem this skill solves

When a user describes a feature to an agent, the agent typically has two failure modes:

1. **Underfitting the spec**: the agent asks no questions, assumes what the user meant, and
   produces something that misses the mark — requiring rework.
2. **Overfitting the conversation**: the agent asks so many questions that the user gives up
   or loses the context, then starts over.

`ask-me` addresses both: it runs a focused questioning phase to surface the most important
unknowns, then transitions directly into implementation — all within the same session.

The key constraint is **one premium request**. Agents like OpenCode or Claude Code bill per
session (conversation turn). If the agent ends the session to "think" or ask the user to
start a new request, the context is lost. The `question` tool solves this: it lets the
agent collect structured input from the user without ending the current request.

---

## Why the `question` tool is mandatory

The skill requires all user interaction to go through the `question` tool. This is intentional
and important.

**What happens without it:** The agent writes a question as plain text, then waits. The user
responds. But this counts as a new message exchange — and depending on the agent platform,
it may start a new billing cycle or lose context. More importantly, it's unstructured: the
user can answer in any order, misread questions, or give ambiguous input that the agent
has to interpret.

**What the `question` tool provides:**
- Structured options that the user picks from (fast, unambiguous)
- An optional free-text field for nuance
- Multiple questions batched in one call (efficient)
- The entire exchange stays within the current session (one premium request)

The skill could work without the `question` tool — but it would lose the "single request"
property that makes it useful in premium agent environments.

---

## Why there are no rigid MUST/NEVER rules {#why-no-must-rules}

The first version of the skill used heavy-handed rules like:

> "NEVER write any code before the confirmation step. MUST use the question tool for all interactions."

This was changed. Here's why.

LLMs are smart. When given good context and clear *reasons* for constraints, they follow them
reliably. Heavy-handed rules create two problems:

1. **They make the skill brittle.** If the agent encounters a situation the rules don't
   anticipate, it has no framework for reasoning about what to do. Rules are a floor, not a
   ceiling.
2. **They create adversarial patterns.** Agents have been observed "working around" MUST rules
   when they seem to conflict with completing a task. An agent that understands *why* it should
   ask questions before coding is more robust than one that follows a rule it doesn't understand.

The current approach: explain the principle and its purpose, then trust the agent. This is
the pattern used by `anthropics/skills/skill-creator`, which documented the same finding.

If a new constraint is truly necessary (observed failure mode, not hypothetical), document the
specific failure it addresses, then phrase it as principle + reasoning rather than bare imperative.

---

## The four-phase structure

The skill has four named phases:

1. **Questioning** — collect context via the `question` tool
2. **Confirmation** — offer the user a choice of next step (implement / review / clarify / stop)
3. **Review** (optional) — share the plan, iterate on it via the `question` tool
4. **Action** — implement or document

This structure is fixed. It represents the minimum viable workflow for framing a feature
correctly. Removing any phase breaks a user scenario:

- Without Questioning: the agent codes blind
- Without Confirmation: the agent codes without consent
- Without Review: the user can't validate the approach before commits are made
- Without Action: the skill never delivers anything

The phases can have different weights (more questioning rounds, deeper review) — but all four
must exist.

---

## The description field: trigger, not summary

The YAML `description` in the frontmatter is the only thing the agent sees about a skill on
every request. It determines whether the skill activates.

The description is a **trigger**, not a summary. It answers: *when should this skill be used?*

This is counterintuitive but empirically important. `obra/superpowers` documented a failure
mode where a description that summarized the skill workflow (e.g., "runs a two-phase review")
caused the agent to follow the *description* instead of reading the skill body — because the
description appeared to already contain the instructions.

The current description:
```yaml
description: >
  Use this skill when the user wants to develop a new feature, fix a bug, refactor code,
  or tackle any non-trivial development task — especially when the request is vague, ambitious,
  or touches multiple parts of the codebase. The skill runs an interactive clarification session
  using the question tool before writing a single line of code, ensuring nothing important is
  missed. Trigger this skill whenever the user says things like "I want to add...", "build me...",
  "implement...", "create a feature for...", "I need a...", or describes a goal without a clear spec.
  The goal is to frame the feature, surface blind spots, clarify functional needs, and only then
  implement — all within a single conversation turn.
```

This description focuses on *when* to trigger (vague feature requests, unclear specs) and
includes literal trigger phrases. It mentions that a `question` tool session is run, but
does not describe the phases — that's the skill body's job.

When improving the description, prioritize:
1. Adding more specific trigger phrases if under-triggering is observed
2. Removing workflow summaries if over-triggering or description-following is observed
3. Keeping it under ~1024 characters (the agentskills.io spec limit)

---

## Language adaptation

The skill instructs the agent to communicate in the user's language. This is a deliberate
UX choice — users who write in French should get French questions and plans without any
configuration.

This is low-risk because the agent's core behavior (question tool usage, phase sequence)
doesn't depend on the language. The only impact is the language of text in `question` tool
labels and descriptions.

The evals include a French-language scenario (`language-adaptation`) to catch regressions.

---

## What the evals cover

The 6 eval scenarios map to the four phases:

| Scenario | Phase tested |
|---|---|
| `basic-feature-request-questioning` | Phase 1 — questioning starts immediately |
| `confirmation-step-offered` | Phase 2 — confirmation uses `question` with 4 options |
| `technical-review-flow` | Phase 3 — review uses `question`, no premature implementation |
| `implement-path` | Phase 4 — implementation without redundant questions |
| `stop-and-document-path` | Phase 4 — plan written, no implementation |
| `language-adaptation` | Cross-cutting — language inheritance |

Gaps not currently covered:
- Multiple rounds of questioning (agent asks follow-up questions)
- The agent choosing to stop questioning early (confident after one round)
- Edge cases where the `question` tool is unavailable

---

## Known limitations and open questions

**The simulation is imperfect.** The eval runner simulates user responses with pre-written
strings. Real users give messier, more varied answers. Evals catch structural regressions
(wrong tool call sequence) but can't test whether the *questions asked* are actually good.

**The model matters.** Evals run against `claude-opus-4-5`. A different model may trigger the
skill differently or follow instructions differently. If you switch the target model, re-run
all evals.

**No trigger calibration yet.** The agentskills.io best-practices recommend running a
description optimization loop (20 trigger/non-trigger eval queries, 5 iterations) to calibrate
the description field. This hasn't been done for `ask-me`. It's a valuable next improvement.
See `anthropics/skills/skill-creator` for the methodology.
