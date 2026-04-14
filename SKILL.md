---
name: ask-me
description: >
  Use this skill when the user wants to develop a new feature, fix a bug, refactor code,
  or tackle any non-trivial development task — especially when the request is vague, ambitious,
  or touches multiple parts of the codebase. The skill runs an interactive clarification session
  using the question tool before writing a single line of code, ensuring nothing important is
  missed. Trigger this skill whenever the user says things like "I want to add...", "build me...",
  "implement...", "create a feature for...", "I need a...", or describes a goal without a clear spec.
  The goal is to frame the feature, surface blind spots, clarify functional needs, and only then
  implement — all within a single conversation turn.
---

# ask-me

A skill for framing a development task through structured questioning before implementing.

The core idea: rushing into code when the spec is fuzzy produces rework. Using question tool
in order to use a single model query, this skill slows you down just enough to surface what's
missing — then accelerates through implementation with full context.

## How to use this skill

When the user invokes this skill (or when you recognize a vague feature request), begin
a questioning session using the `question` tool. Your goal is to understand the feature
well enough to write a confident implementation plan. Then implement — or hand off the plan —
based on what the user chooses.

Follow the workflow defined in the phases below.

Communicate in the same language as the user throughout the session.

---

## Phase 1: Questioning

Use the `question` tool to ask the user what you need to know. You are not interrogating —
you are collaborating. Think about:

- What is the feature actually trying to accomplish? (user goal, not technical spec)
- Who uses it, and in what context?
- What are the edge cases or failure modes that aren't mentioned?
- Are there functional requirements implied but not stated?
- Are there existing patterns in the codebase this should follow?
- What does "done" look like for the user?

Ask multiple questions per round when they're related — the `question` tool supports batching
them. You decide when you have enough context to propose an implementation plan. There's no fixed
number of rounds; stop when you feel confident, not when you've asked a minimum number of questions.

When asking questions, always offer concrete options so the user can answer quickly — but include
a free-text option so they can express nuance. Frame options thoughtfully: they should reflect
real trade-offs, not just yes/no.

---

## Phase 2: Confirmation

Once you feel ready to implement, don't just start coding. Use the `question` tool to present
your intent and let the user choose the next step:

```
Options to offer (always use the question tool for this):
1. Implement — go ahead and build it
2. Review the technical plan first — share your plan, get feedback before coding
3. Keep clarifying — more questions needed
4. Stop and document the plan — write it down but don't implement
```

This confirmation step is important: the user may want to validate your approach before you
spend tokens on implementation. Always offer this choice.

---

## Phase 3: Review (if requested)

If the user chooses "Review the technical plan", present your implementation plan clearly:

- What files will be changed or created
- What the core logic looks like
- Any significant design decisions and why you made them
- What you're unsure about

Then use the `question` tool to ask for feedback. You can offer specific angles to explore
(e.g., "Does the data model make sense?", "Any concerns about the approach to X?") or let
them respond freely. Always offer:

- Continue reviewing (more questions/discussion)
- Implement now (proceed with the current plan)

Stay in review mode until the user explicitly moves to implementation.

---

## Phase 4: Implementation or Documentation

**If the user chooses to implement:** Build it. Use everything you've learned during the
questioning phase. Don't ask redundant questions you already answered.

**If the user chooses to stop and document:** Write a clear plan document covering the feature
intent, functional requirements surfaced, the proposed technical approach, and any open questions.
Present it inline in the conversation.

---

## A note on tone and efficiency

The questioning phase should feel like talking to a thoughtful senior engineer — not a checklist.
Ask questions that would genuinely change your implementation. Skip questions whose answers
don't affect the code. The user's time is valuable; every question should earn its place.

Resist the urge to start with a long monologue about what you're going to do. Jump into the
first question round quickly. The user already knows you're here to help.
