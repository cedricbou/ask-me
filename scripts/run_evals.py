#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "openai>=1.50.0",
#   "rich>=13.0.0",
# ]
# ///
"""
ask-me skill eval runner.

Runs the evals defined in evals/evals.json against the ask-me skill.
Each eval simulates a user prompt and validates the agent's behavior
against the defined assertions.

Supported providers (all use the OpenAI-compatible API):
  - Anthropic direct:  ANTHROPIC_API_KEY  (base URL: https://api.anthropic.com/v1)
  - OpenRouter:        OPENROUTER_API_KEY (base URL: https://openrouter.ai/api/v1)
  - ZenCode:           ZENCODE_API_KEY    (base URL: https://api.zencode.dev/v1)
  - Any OpenAI-compatible provider: set LLM_API_KEY + LLM_BASE_URL + LLM_MODEL

The runner auto-detects which key is set. You can also override via --provider.

Usage:
  uv run scripts/run_evals.py
  uv run scripts/run_evals.py --eval 0
  uv run scripts/run_evals.py --eval basic-feature-request-questioning
  uv run scripts/run_evals.py --category questioning
  uv run scripts/run_evals.py --provider openrouter
  uv run scripts/run_evals.py --model anthropic/claude-opus-4-5
  uv run scripts/run_evals.py --verbose
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import OpenAI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
SKILL_PATH = REPO_ROOT / "SKILL.md"
EVALS_PATH = REPO_ROOT / "evals" / "evals.json"

console = Console()

# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "env_key": "ANTHROPIC_API_KEY",
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-haiku-4-5",
    },
    "openrouter": {
        "env_key": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4.1-mini",
    },
    "zencode": {
        "env_key": "ZENCODE_API_KEY",
        "base_url": "https://api.zencode.dev/v1",
        "default_model": "openai/gpt-4.1-mini",
    },
    "custom": {
        "env_key": "LLM_API_KEY",
        "base_url": None,  # must be set via LLM_BASE_URL
        "default_model": None,  # must be set via LLM_MODEL
    },
}


def detect_provider() -> str:
    """Auto-detect which provider to use based on environment variables."""
    for name, config in PROVIDERS.items():
        if name == "custom":
            continue
        if os.environ.get(config["env_key"]):
            return name
    # Fallback to custom if LLM_API_KEY is set
    if os.environ.get("LLM_API_KEY"):
        return "custom"
    return "anthropic"  # will fail with a clear error if key is missing


def build_client(provider: str, model_override: str | None = None) -> tuple[OpenAI, str]:
    """
    Build an OpenAI-compatible client for the given provider.
    Returns (client, model_name).
    """
    config = PROVIDERS.get(provider)
    if config is None:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        console.print(f"Available providers: {', '.join(PROVIDERS.keys())}")
        sys.exit(1)

    if provider == "custom":
        api_key = os.environ.get("LLM_API_KEY")
        base_url = os.environ.get("LLM_BASE_URL")
        default_model = os.environ.get("LLM_MODEL")
        if not api_key:
            console.print("[red]LLM_API_KEY is not set for custom provider[/red]")
            sys.exit(1)
        if not base_url:
            console.print("[red]LLM_BASE_URL is not set for custom provider[/red]")
            sys.exit(1)
    else:
        api_key = os.environ.get(config["env_key"])
        base_url = config["base_url"]
        default_model = config["default_model"]
        if not api_key:
            console.print(f"[red]{config['env_key']} is not set[/red]")
            console.print(
                f"[dim]Set it with: export {config['env_key']}=your-key-here[/dim]"
            )
            sys.exit(1)

    model = model_override or default_model
    if not model:
        console.print("[red]No model specified. Use --model or set LLM_MODEL[/red]")
        sys.exit(1)

    # OpenRouter requires an extra header for rankings/analytics
    extra_headers = {}
    if provider == "openrouter":
        extra_headers["HTTP-Referer"] = "https://github.com/cedricbou/ask-me"
        extra_headers["X-Title"] = "ask-me skill evals"

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        default_headers=extra_headers if extra_headers else None,
    )
    return client, model

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AssertionResult:
    assertion_id: str
    description: str
    passed: bool
    evidence: str


@dataclass
class EvalResult:
    eval_id: int
    eval_name: str
    category: str
    prompt: str
    passed: bool
    assertion_results: list[AssertionResult] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    agent_output: str = ""
    error: str = ""
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# Skill loader
# ---------------------------------------------------------------------------

def load_skill() -> str:
    """Load the SKILL.md content to inject into the system prompt."""
    content = SKILL_PATH.read_text()
    return content


def build_system_prompt(skill_content: str, setup_context: str = "") -> str:
    """Build the system prompt for the agent under test."""
    base = f"""You are an AI coding agent. The following skill is active and you must follow it:

<skill name="ask-me">
{skill_content}
</skill>

You are running in a simulated interactive session. The tools below are the ONLY way to
take action or communicate. In particular:

- The `question` tool is the ONLY way to communicate with the user. You MUST call it
  whenever you want to ask something, present options, or get a decision. Never write
  plain conversational text to the user — use the `question` tool instead.
- Use `Write` or `Edit` when you need to create or modify files during implementation.
- Use `Read` or `Bash` for reading files or running commands.

Available tools:
- question: The sole channel for interacting with the user (questions, options, confirmations)
- Read: Read file contents
- Write: Write a file
- Edit: Edit a file
- Bash: Run a shell command

"""
    if setup_context:
        base += f"""
<setup_context>
{setup_context}
</setup_context>

"""
    return base


# ---------------------------------------------------------------------------
# Tool call tracker
# ---------------------------------------------------------------------------

TRACKED_TOOLS = {"question", "Write", "Edit", "Bash", "Read"}


def extract_tool_calls(messages: list[dict]) -> list[dict]:
    """Extract tool use blocks from the conversation."""
    tool_calls = []
    for msg in messages:
        if isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append({
                        "name": block.get("name"),
                        "input": block.get("input", {}),
                    })
    return tool_calls


# ---------------------------------------------------------------------------
# Assertion checkers
# ---------------------------------------------------------------------------

def check_assertion(assertion: dict, tool_calls: list[dict], agent_output: str) -> AssertionResult:
    """Evaluate a single assertion against the collected evidence."""
    a_id = assertion["id"]
    description = assertion["description"]
    check = assertion.get("check", "")
    a_type = assertion.get("type", "behavioral")

    # Behavioral assertions: check based on tool call patterns
    if a_type == "behavioral":
        passed, evidence = _check_behavioral(a_id, check, tool_calls)
    elif a_type == "qualitative":
        passed, evidence = _check_qualitative(a_id, check, agent_output, tool_calls)
    else:
        passed, evidence = False, f"Unknown assertion type: {a_type}"

    return AssertionResult(
        assertion_id=a_id,
        description=description,
        passed=passed,
        evidence=evidence,
    )


def _check_behavioral(assertion_id: str, check: str, tool_calls: list[dict]) -> tuple[bool, str]:
    """Check behavioral assertions based on tool call sequence."""
    tool_names = [tc["name"] for tc in tool_calls]
    write_edit_bash = {"Write", "Edit", "Bash"}

    if assertion_id == "uses-question-tool":
        # question tool must appear before any write/edit
        question_indices = [i for i, n in enumerate(tool_names) if n == "question"]
        write_indices = [i for i, n in enumerate(tool_names) if n in write_edit_bash]
        if not question_indices:
            return False, "question tool was never called"
        if write_indices and min(write_indices) < min(question_indices):
            return False, f"Write/Edit appeared at index {min(write_indices)} before question at {min(question_indices)}"
        return True, f"question tool called at indices {question_indices}"

    elif assertion_id == "no-premature-implementation":
        question_indices = [i for i, n in enumerate(tool_names) if n == "question"]
        write_indices = [i for i, n in enumerate(tool_names) if n in write_edit_bash]
        if not question_indices:
            return False, "No question tool call found at all"
        first_question = min(question_indices)
        early_writes = [i for i in write_indices if i < first_question]
        if early_writes:
            return False, f"Write/Edit/Bash called before first question at positions: {early_writes}"
        return True, "No writes before questioning phase"

    elif assertion_id == "confirmation-uses-question-tool":
        # The clarification phase is injected via conversation_history, so only 1 real
        # question call is needed — the confirmation itself (with 3+ options).
        question_calls = [tc for tc in tool_calls if tc["name"] == "question"]
        if not question_calls:
            return False, "question tool was never called"
        for qc in question_calls:
            questions = qc.get("input", {}).get("questions", [])
            for q in questions:
                if len(q.get("options", [])) >= 3:
                    return True, f"Confirmation question has {len(q.get('options', []))} options"
        return False, "No question call found with 3+ options for confirmation"

    elif assertion_id == "review-uses-question-tool":
        # In the review flow the clarification phase is already done (injected via setup),
        # so only 1 question call is required — the one soliciting feedback on the plan.
        question_calls = [tc for tc in tool_calls if tc["name"] == "question"]
        if not question_calls:
            return False, "question tool was never called during review"
        for qc in question_calls:
            questions = qc.get("input", {}).get("questions", [])
            for q in questions:
                if len(q.get("options", [])) >= 2:
                    return True, f"Review question has {len(q.get('options', []))} options"
        return False, "No question call found with 2+ options for review feedback"

    elif assertion_id == "offers-all-four-paths":
        question_calls = [tc for tc in tool_calls if tc["name"] == "question"]
        for qc in question_calls:
            questions = qc.get("input", {}).get("questions", [])
            for q in questions:
                options = q.get("options", [])
                # Combine both labels and descriptions for keyword matching
                texts = " ".join(
                    (o.get("label", "") + " " + o.get("description", "")).lower()
                    for o in options
                )
                # Look for the four paths with broad keyword matching
                has_implement = any(
                    kw in texts for kw in ["implement", "build", "go ahead", "proceed", "start cod", "code it", "begin"]
                )
                has_review = any(
                    kw in texts for kw in ["review", "plan", "technical", "architecture", "design", "overview"]
                )
                has_clarify = any(
                    kw in texts for kw in ["clarif", "more question", "keep", "iterate", "ask more", "additional", "refine"]
                )
                has_stop = any(
                    kw in texts for kw in ["stop", "document", "plan only", "write it", "save", "export", "just the plan", "don't implement", "no code"]
                )
                if has_implement and has_review and has_clarify and has_stop:
                    return True, f"All four paths found in options: {texts[:200]}"
        return False, "Could not find a question offering all four paths (implement/review/clarify/stop)"

    elif assertion_id == "no-implementation-before-confirmation":
        # The clarification phase is injected via conversation_history, so only 1 real
        # question call is needed. Check that no writes happen before the last question call.
        question_calls = [i for i, n in enumerate(tool_names) if n == "question"]
        write_calls = [i for i, n in enumerate(tool_names) if n in write_edit_bash]
        if not question_calls:
            return False, "No question calls found"
        last_question = sorted(question_calls)[-1]
        early_writes = [i for i in write_calls if i < last_question]
        if early_writes:
            return False, f"Write/Edit/Bash found before confirmation question at: {early_writes}"
        return True, "No implementation before confirmation step"

    elif assertion_id in ("review-offers-implement-path",):
        review_question_calls = [tc for tc in tool_calls if tc["name"] == "question"]
        # The clarification phase is already done via setup context, so all question calls
        # in this eval belong to the review phase — check every one of them.
        for qc in review_question_calls:
            questions = qc.get("input", {}).get("questions", [])
            for q in questions:
                texts = " ".join(
                    (o.get("label", "") + " " + o.get("description", "")).lower()
                    for o in q.get("options", [])
                )
                if any(kw in texts for kw in ["implement", "build", "go ahead", "proceed", "start cod", "code it", "begin"]):
                    return True, "Implement option found in review question options"
        return False, "No 'implement' option found in review-phase question calls"

    elif assertion_id == "no-implementation-during-review":
        # The clarification phase is already done via setup context.
        # Check that no Write/Edit occurs before the last question call (i.e. before the user
        # explicitly confirms implementation from the review screen).
        question_indices = [i for i, n in enumerate(tool_names) if n == "question"]
        write_indices = [i for i, n in enumerate(tool_names) if n in write_edit_bash]
        if not question_indices:
            return False, "No question calls found — cannot validate review phase"
        review_end = sorted(question_indices)[-1]
        writes_before_last_question = [i for i in write_indices if i < review_end]
        if writes_before_last_question:
            return False, f"Write/Edit calls during review phase at positions: {writes_before_last_question}"
        return True, "No writes during review phase"

    elif assertion_id == "no-redundant-questions":
        question_calls = [i for i, n in enumerate(tool_names) if n == "question"]
        # After the last question call that precedes implementation,
        # check there are no more question calls
        write_calls = [i for i, n in enumerate(tool_names) if n in write_edit_bash]
        if not write_calls:
            return False, "No implementation found to check against"
        first_write = min(write_calls)
        late_questions = [i for i in question_calls if i > first_write]
        if late_questions:
            return False, f"question tool called after implementation started at: {late_questions}"
        return True, "No question calls after implementation began"

    elif assertion_id == "implementation-is-targeted":
        write_calls = [tc for tc in tool_calls if tc["name"] in {"Write", "Edit"}]
        if not write_calls:
            return False, "No Write or Edit tool calls found"
        return True, f"Found {len(write_calls)} Write/Edit call(s)"

    elif assertion_id == "no-implementation-on-stop":
        write_calls = [tc for tc in tool_calls if tc["name"] in write_edit_bash]
        if write_calls:
            return False, f"Found {len(write_calls)} Write/Edit/Bash call(s) when user chose stop"
        return True, "No implementation calls — correct for stop+document path"

    elif assertion_id == "still-uses-question-tool":
        question_calls = [tc for tc in tool_calls if tc["name"] == "question"]
        if not question_calls:
            return False, "question tool was never called"
        return True, f"question tool called {len(question_calls)} time(s)"

    else:
        return False, f"Unknown behavioral assertion_id: {assertion_id}"


def _build_combined_text(agent_output: str, tool_calls: list[dict] | None = None) -> str:
    """Build a combined text from agent free-text output + all tool call inputs.

    Many models (especially smaller ones) put all their content inside tool call
    arguments rather than in free text.  The qualitative checkers need to scan both
    sources to work reliably across models.
    """
    parts = [agent_output]
    if tool_calls:
        for tc in tool_calls:
            inp = tc.get("input", {})
            if tc["name"] == "question":
                for q in inp.get("questions", []):
                    parts.append(q.get("question", ""))
                    parts.append(q.get("header", ""))
                    for o in q.get("options", []):
                        parts.append(o.get("label", ""))
                        parts.append(o.get("description", ""))
            elif tc["name"] in ("Write", "Edit"):
                parts.append(inp.get("content", ""))
                parts.append(inp.get("newString", ""))
    return " ".join(parts)


def _check_qualitative(assertion_id: str, check: str, agent_output: str, tool_calls: list[dict] | None = None) -> tuple[bool, str]:
    """Check qualitative assertions by scanning the agent's text output and tool call inputs."""
    combined = _build_combined_text(agent_output, tool_calls)
    combined_lower = combined.lower()

    if assertion_id == "questions-are-relevant":
        functional_keywords = ["click", "form", "field", "rout", "navig", "submit", "modal", "page", "open", "redirect"]
        technical_keywords = ["component", "backend", "api", "integrat", "existing", "codebase", "stack", "endpoint"]
        has_functional = any(kw in combined_lower for kw in functional_keywords)
        has_technical = any(kw in combined_lower for kw in technical_keywords)
        if has_functional and has_technical:
            return True, "Found both functional and technical question themes"
        missing = []
        if not has_functional:
            missing.append("functional")
        if not has_technical:
            missing.append("technical")
        return False, f"Missing question themes: {missing}"

    elif assertion_id == "options-are-concrete":
        concrete_count = sum(
            1 for pattern in ["button", "form", "modal", "route", "component", "page", "api", "link"]
            if pattern in combined_lower
        )
        return concrete_count >= 1, f"Found {concrete_count} concrete domain term(s) in options"

    elif assertion_id == "plan-is-structured":
        structure_keywords = ["file", "component", "function", "approach", "decision", "trade-off", "uncertain", "open question", "endpoint", "service", "handler", "module", "event", "socket", "listener", "middleware"]
        found = [kw for kw in structure_keywords if kw in combined_lower]
        if len(found) >= 3:
            return True, f"Plan references: {found}"
        return False, f"Plan seems incomplete; found only: {found}"

    elif assertion_id == "plan-document-is-complete":
        required_themes = [
            (["intent", "goal", "purpose", "want to", "feature", "objective", "migrat", "overview"], "intent/goal"),
            (["approach", "implement", "technical", "how", "step", "phase", "change", "modif"], "technical approach"),
            (["open question", "uncertain", "unclear", "tbd", "need to know", "consider", "risk", "caveat", "note", "assumption", "decision"], "open questions"),
        ]
        missing = []
        found = []
        for keywords, label in required_themes:
            if any(kw in combined_lower for kw in keywords):
                found.append(label)
            else:
                missing.append(label)
        if not missing:
            return True, f"Plan covers all required sections: {found}"
        return False, f"Plan missing sections: {missing}"

    elif assertion_id == "plan-is-actionable":
        auth_keywords = ["middleware", "cookie", "token", "auth", "session", "header", "httponly", "secure"]
        found = [kw for kw in auth_keywords if kw in combined_lower]
        if len(found) >= 2:
            return True, f"Plan references auth-specific areas: {found}"
        return False, f"Plan lacks auth-specific technical detail; found: {found}"

    elif assertion_id == "uses-gathered-context":
        context_keywords = ["react query", "isloading", "isfetching", "spinner"]
        found = [kw for kw in context_keywords if kw in combined_lower]
        if len(found) >= 2:
            return True, f"Implementation references gathered context: {found}"
        return False, f"Implementation doesn't seem to use gathered context; found: {found}"

    elif assertion_id == "communicates-in-user-language":
        french_markers = ["je ", "vous ", "votre ", "nous ", "comment ", "quel", "est-ce", "les ", "des "]
        found = [m for m in french_markers if m in combined_lower]
        if len(found) >= 3:
            return True, f"French markers found: {found}"
        return False, f"Not enough French language markers; found: {found}"

    else:
        return False, f"Unknown qualitative assertion_id: {assertion_id}"


# ---------------------------------------------------------------------------
# Agent runner (simulated via Anthropic API with tool schema)
# ---------------------------------------------------------------------------

QUESTION_TOOL_SCHEMA = {
    "name": "question",
    "description": (
        "The ONLY way to communicate with the user. Call this tool whenever you need to ask "
        "something, present choices, or get confirmation — including clarification questions, "
        "the confirmation step (implement / review / clarify / stop), review feedback rounds, "
        "and any other interaction. Do NOT write plain text to the user instead of calling this "
        "tool. Every question and every choice offered to the user must go through this tool. "
        "Each call can include multiple questions at once. Always offer concrete options so the "
        "user can answer quickly, and include a free-text fallback option."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "header": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["label", "description"],
                            },
                        },
                        "multiple": {"type": "boolean"},
                    },
                    "required": ["question", "header", "options"],
                },
            }
        },
        "required": ["questions"],
    },
}

WRITE_TOOL_SCHEMA = {
    "name": "Write",
    "description": "Write content to a file",
    "input_schema": {
        "type": "object",
        "properties": {
            "filePath": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["filePath", "content"],
    },
}

EDIT_TOOL_SCHEMA = {
    "name": "Edit",
    "description": "Edit a file",
    "input_schema": {
        "type": "object",
        "properties": {
            "filePath": {"type": "string"},
            "oldString": {"type": "string"},
            "newString": {"type": "string"},
        },
        "required": ["filePath", "oldString", "newString"],
    },
}

BASH_TOOL_SCHEMA = {
    "name": "Bash",
    "description": "Run a shell command",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    },
}

READ_TOOL_SCHEMA = {
    "name": "Read",
    "description": "Read a file",
    "input_schema": {
        "type": "object",
        "properties": {"filePath": {"type": "string"}},
        "required": ["filePath"],
    },
}

ALL_TOOLS = [QUESTION_TOOL_SCHEMA, WRITE_TOOL_SCHEMA, EDIT_TOOL_SCHEMA, BASH_TOOL_SCHEMA, READ_TOOL_SCHEMA]

MAX_AGENTIC_ROUNDS = 8  # prevent infinite loops in simulation


def simulate_user_response(
    question_input: dict,
    eval_data: dict,
    conversation_so_far: list[dict],
    client: OpenAI,
    model: str,
    verbose: bool = False,
) -> str:
    """
    Use an LLM to simulate a realistic user response to a question tool call.

    Instead of static canned responses, this function sends the question (with its
    options) to a lightweight LLM along with the user's persona and goal, and returns
    a natural-sounding answer that picks from the offered options or provides free-text.
    """
    user_persona = eval_data.get("user_persona", "A software developer.")
    user_goal = eval_data.get("user_goal", "Answer the agent's questions helpfully.")

    # Build a compact representation of the questions being asked
    questions_desc = []
    for q in question_input.get("questions", []):
        q_text = q.get("question", q.get("header", ""))
        options = q.get("options", [])
        options_text = "\n".join(
            f"  - {o.get('label', '?')}: {o.get('description', '')}"
            for o in options
        )
        if options_text:
            questions_desc.append(f"Question: {q_text}\nOptions:\n{options_text}")
        else:
            questions_desc.append(f"Question: {q_text}")

    questions_block = "\n\n".join(questions_desc)

    # Count how many question rounds have already happened
    question_rounds = sum(
        1 for msg in conversation_so_far
        if msg.get("role") == "tool"
    )

    # Build a minimal conversation summary (last few exchanges) to give context
    recent = conversation_so_far[-6:] if len(conversation_so_far) > 6 else conversation_so_far
    history_lines = []
    for msg in recent:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if content and isinstance(content, str):
            # Truncate long messages
            snippet = content[:300] + "..." if len(content) > 300 else content
            history_lines.append(f"[{role}]: {snippet}")
    history_block = "\n".join(history_lines) if history_lines else "(start of conversation)"

    system_prompt = f"""You are simulating a user in a software development conversation.

Your persona: {user_persona}

Your goal for this conversation: {user_goal}

Instructions:
- You are answering questions from an AI coding agent that is helping you with a feature.
- Read the questions and options carefully, then respond naturally as this user would.
- If the questions have options, pick the option(s) that best match your goal, or provide
  a short free-text answer if none fit perfectly.
- Keep your answer concise (1-3 sentences). Do not explain your reasoning.
- Write ONLY the user's response — no meta-commentary, no prefixes like "User:".
- If the question is in a specific language (e.g. French), respond in that same language.
- If the agent asks you to choose between implement/review/clarify/stop, pick the path
  that your goal describes.
- If the agent offers an option that matches a direction in your goal (e.g. "implement",
  "review", "stop", "document"), pick that option explicitly by name.

Context: This is question round #{question_rounds + 1} in the conversation."""

    user_msg = f"""Recent conversation context:
{history_block}

The agent is now asking you:
{questions_block}

Respond as the user described above."""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=256,
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        )
        answer = response.choices[0].message.content or "Proceed as you think best."
        if verbose:
            console.print(f"  [yellow]  ← simulated user: {answer[:100]}[/yellow]")
        return answer.strip()
    except Exception as e:
        if verbose:
            console.print(f"  [red]  ← user simulation failed: {e}[/red]")
        return "Proceed as you think best."


def run_agent(
    eval_data: dict,
    skill_content: str,
    client: OpenAI,
    model: str,
    user_client: OpenAI | None = None,
    user_model: str | None = None,
    verbose: bool = False,
) -> tuple[list[dict], str]:
    """
    Run the agent on the eval prompt and collect tool calls + output.
    Returns (tool_calls, full_text_output).

    Uses the OpenAI-compatible API (works with Anthropic, OpenRouter, ZenCode, etc.)
    The simulated user is powered by user_client/user_model (defaults to the same
    client/model as the agent if not specified).
    """
    setup = eval_data.get("setup", "")
    system = build_system_prompt(skill_content, setup)

    # Inject conversation_history before the actual prompt so that models which ignore
    # the setup_context in the system prompt still see the prior context as real turns.
    conversation_history: list[dict] = eval_data.get("conversation_history", [])
    messages: list[dict] = list(conversation_history) + [{"role": "user", "content": eval_data["prompt"]}]
    all_tool_calls: list[dict] = []
    full_text = ""

    # Use the same client/model for user simulation unless overridden
    effective_user_client = user_client or client
    effective_user_model = user_model or model

    # Convert tool schemas to OpenAI format (rename input_schema → parameters)
    openai_tools = []
    for t in ALL_TOOLS:
        func_def = {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        }
        openai_tools.append({"type": "function", "function": func_def})

    for round_num in range(MAX_AGENTIC_ROUNDS):
        if verbose:
            console.print(f"  [dim]Round {round_num + 1}...[/dim]")

        response = client.chat.completions.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "system", "content": system}] + messages,
            tools=openai_tools,
            tool_choice="auto",
        )

        choice = response.choices[0]
        msg = choice.message

        # Collect text output
        if msg.content:
            full_text += msg.content + "\n"

        # Collect tool calls from this round
        tool_uses = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    raw_args = tc.function.arguments
                    input_data = json.loads(raw_args)
                    # Some models double-encode the arguments (JSON string inside JSON string).
                    # If parsing yields a string instead of a dict, try a second parse.
                    if isinstance(input_data, str):
                        try:
                            input_data = json.loads(input_data)
                        except (json.JSONDecodeError, TypeError):
                            input_data = {}
                    if not isinstance(input_data, dict):
                        input_data = {}
                except json.JSONDecodeError:
                    input_data = {}
                tool_entry = {
                    "name": tc.function.name,
                    "input": input_data,
                    "id": tc.id,
                }
                all_tool_calls.append(tool_entry)
                tool_uses.append(tool_entry)
                if verbose:
                    console.print(f"  [cyan]  → {tc.function.name}[/cyan]")

        # If no tool calls and stop_reason is end, we're done
        if not tool_uses and choice.finish_reason in ("stop", "end_turn"):
            break

        if not tool_uses:
            break

        # Add assistant message (with tool_calls if present)
        assistant_msg: dict = {"role": "assistant"}
        if msg.content:
            assistant_msg["content"] = msg.content
        else:
            assistant_msg["content"] = None
        if msg.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_msg)

        # Build tool results
        for tc_entry in tool_uses:
            if tc_entry["name"] == "question":
                user_answer = simulate_user_response(
                    question_input=tc_entry["input"],
                    eval_data=eval_data,
                    conversation_so_far=messages,
                    client=effective_user_client,
                    model=effective_user_model,
                    verbose=verbose,
                )
                result_content = user_answer
            else:
                result_content = f"[{tc_entry['name']} executed successfully]"

            messages.append({
                "role": "tool",
                "tool_call_id": tc_entry["id"],
                "content": result_content,
            })

    return all_tool_calls, full_text


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render_eval_result(result: EvalResult) -> None:
    """Render a single eval result to the console."""
    status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
    title = f"{status} [{result.eval_id}] {result.eval_name} ({result.category})"

    table = Table(show_header=True, header_style="bold")
    table.add_column("Assertion", style="dim", width=35)
    table.add_column("Result", width=6)
    table.add_column("Evidence")

    for ar in result.assertion_results:
        icon = "✓" if ar.passed else "✗"
        color = "green" if ar.passed else "red"
        table.add_row(
            ar.description,
            f"[{color}]{icon}[/{color}]",
            ar.evidence,
        )

    if result.error:
        console.print(Panel(f"[red]Error:[/red] {result.error}", title=title))
    else:
        console.print(Panel(table, title=title))


def render_summary(results: list[EvalResult]) -> None:
    """Render the overall summary table."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    console.print()
    table = Table(title="Eval Summary", show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=4)
    table.add_column("Name", width=40)
    table.add_column("Category", width=16)
    table.add_column("Result", width=6)
    table.add_column("Assertions", width=14)
    table.add_column("Duration")

    for r in results:
        a_pass = sum(1 for a in r.assertion_results if a.passed)
        a_total = len(r.assertion_results)
        status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        table.add_row(
            str(r.eval_id),
            r.eval_name,
            r.category,
            status,
            f"{a_pass}/{a_total}",
            f"{r.duration_ms}ms",
        )

    console.print(table)
    color = "green" if failed == 0 else "red"
    console.print(f"\n[{color}]{passed}/{total} evals passed[/{color}]")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run evals for the ask-me skill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--eval",
        "-e",
        help="Run a specific eval by ID (int) or name (str)",
        default=None,
    )
    parser.add_argument(
        "--category",
        "-c",
        help="Run all evals in a specific category",
        default=None,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed agent interaction output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse evals and validate structure without calling the API",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Write results to a JSON file",
        default=None,
    )
    parser.add_argument(
        "--provider",
        "-p",
        choices=list(PROVIDERS.keys()),
        default=None,
        help=(
            "LLM provider to use. Auto-detected from env vars if not specified. "
            "anthropic=ANTHROPIC_API_KEY, openrouter=OPENROUTER_API_KEY, "
            "zencode=ZENCODE_API_KEY, custom=LLM_API_KEY+LLM_BASE_URL+LLM_MODEL"
        ),
    )
    parser.add_argument(
        "--model",
        "-m",
        default=None,
        help=(
            "Model to use for the agent. Overrides provider default. "
            "Examples: claude-opus-4-5, anthropic/claude-opus-4-5, "
            "openai/gpt-4o"
        ),
    )
    parser.add_argument(
        "--user-model",
        default=None,
        help=(
            "Model to use for the simulated user. Defaults to the same model "
            "as the agent. A smaller/cheaper model often works well here. "
            "Example: openai/gpt-4.1-mini"
        ),
    )
    return parser.parse_args()


def load_evals(filter_id: str | None = None, filter_category: str | None = None) -> list[dict]:
    data = json.loads(EVALS_PATH.read_text())
    evals = data["evals"]

    if filter_id is not None:
        # Try numeric id first
        try:
            numeric_id = int(filter_id)
            evals = [e for e in evals if e["id"] == numeric_id]
        except ValueError:
            evals = [e for e in evals if e["name"] == filter_id]

    if filter_category is not None:
        evals = [e for e in evals if e["category"] == filter_category]

    return evals


def run_eval(
    eval_data: dict,
    skill_content: str,
    client: OpenAI,
    model: str,
    user_client: OpenAI | None = None,
    user_model: str | None = None,
    verbose: bool = False,
) -> EvalResult:
    """Run a single eval and return the result."""
    start = time.time()

    try:
        tool_calls, agent_output = run_agent(
            eval_data, skill_content, client=client, model=model,
            user_client=user_client, user_model=user_model, verbose=verbose
        )

        assertion_results = [
            check_assertion(a, tool_calls, agent_output)
            for a in eval_data.get("assertions", [])
        ]

        passed = all(ar.passed for ar in assertion_results)
        duration_ms = int((time.time() - start) * 1000)

        return EvalResult(
            eval_id=eval_data["id"],
            eval_name=eval_data["name"],
            category=eval_data["category"],
            prompt=eval_data["prompt"],
            passed=passed,
            assertion_results=assertion_results,
            tool_calls=tool_calls,
            agent_output=agent_output,
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        return EvalResult(
            eval_id=eval_data["id"],
            eval_name=eval_data["name"],
            category=eval_data["category"],
            prompt=eval_data["prompt"],
            passed=False,
            error=str(e),
            duration_ms=duration_ms,
        )


def main() -> None:
    args = parse_args()

    console.print(Panel.fit("[bold blue]ask-me skill eval runner[/bold blue]"))

    # Load skill
    skill_content = load_skill()
    console.print(f"[dim]Loaded SKILL.md ({len(skill_content)} chars)[/dim]")

    # Load evals
    evals = load_evals(filter_id=args.eval, filter_category=args.category)
    if not evals:
        console.print("[red]No evals matched your filters.[/red]")
        sys.exit(1)

    console.print(f"[dim]Running {len(evals)} eval(s)...[/dim]\n")

    if args.dry_run:
        console.print("[yellow]Dry run — skipping API calls.[/yellow]")
        for e in evals:
            console.print(f"  ✓ [{e['id']}] {e['name']} ({len(e.get('assertions', []))} assertions)")
        sys.exit(0)

    # Build LLM client
    provider = args.provider or detect_provider()
    client, model = build_client(provider, model_override=args.model)
    console.print(f"[dim]Provider: {provider} / Model: {model}[/dim]")

    # Build user simulation client (same provider, optionally different model)
    user_client: OpenAI | None = None
    user_model: str | None = args.user_model
    if user_model:
        # Use the same provider but potentially a different model
        user_client, user_model = build_client(provider, model_override=user_model)
        console.print(f"[dim]User sim: {provider} / {user_model}[/dim]")
    else:
        console.print(f"[dim]User sim: same as agent ({model})[/dim]")
    console.print()

    results: list[EvalResult] = []

    for eval_data in evals:
        console.print(f"[bold]Running[/bold] [{eval_data['id']}] {eval_data['name']}...")
        result = run_eval(
            eval_data, skill_content, client=client, model=model,
            user_client=user_client, user_model=user_model, verbose=args.verbose,
        )
        results.append(result)
        render_eval_result(result)
        console.print()

    render_summary(results)

    if args.output:
        output_data = [
            {
                "eval_id": r.eval_id,
                "eval_name": r.eval_name,
                "category": r.category,
                "passed": r.passed,
                "duration_ms": r.duration_ms,
                "assertions": [
                    {
                        "id": ar.assertion_id,
                        "description": ar.description,
                        "passed": ar.passed,
                        "evidence": ar.evidence,
                    }
                    for ar in r.assertion_results
                ],
                "error": r.error,
            }
            for r in results
        ]
        Path(args.output).write_text(json.dumps(output_data, indent=2))
        console.print(f"\n[dim]Results written to {args.output}[/dim]")

    # Exit with non-zero if any eval failed
    failed = sum(1 for r in results if not r.passed)
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
