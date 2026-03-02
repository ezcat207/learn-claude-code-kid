# s04: Subagents — Spawning a Helper with Fresh Memory

`s01 > s02 > s03 > [ s04 ] s05 > s06 | s07 > s08 > s09 > s10 > s11 > s12`

> **Delegate big tasks to a child agent. It shares the filesystem but not your memory.**

---

## The Problem: Big Tasks Fill Up Memory

Remember how the AI has a context window — a limit on how much it can "see" at once? In s01-s03 the tasks were small. But what about big ones?

Imagine you ask: *"Review every Python file in this project and find all bugs."*

The AI starts reading files, one by one. Each file goes into the conversation history. After 10 files, the history is huge. The AI starts forgetting what it saw in file 1 by the time it reaches file 10. Or it hits the limit and crashes.

**The problem:** one long conversation = one giant pile of memory. The longer it runs, the worse it gets.

---

## The Solution: Hire a Helper with a Clean Desk

Instead of doing everything in one conversation, the parent agent can **spawn a subagent** — a second AI with a completely fresh, empty memory — to handle a specific chunk of work.

```
Parent: "Review the files in /src"
  → Spawns subagent with prompt: "Review /src/utils.py for bugs"
    → Subagent reads file, finds bugs, writes summary
    → Summary (a few lines) comes back to parent
  → Parent sees only the summary, not the whole subagent conversation
```

The subagent's full conversation — all the file contents, all the back-and-forth — is **thrown away**. Only the summary returns. The parent's memory stays clean.

---

## How It Works — Step by Step

### Step 1: A new `task` tool triggers a subagent

```python
PARENT_TOOLS = CHILD_TOOLS + [
    {"name": "task",
     "description": "Spawn a subagent with fresh context.",
     "input_schema": {"type": "object",
                      "properties": {"prompt": {"type": "string"}},
                      "required": ["prompt"]}}
]
# Parent has all base tools PLUS one new tool: task
# Child tools = bash, read_file, write_file, edit_file (no task — no recursion)
```

### Step 2: `run_subagent` — the full child agent loop

```python
def run_subagent(prompt: str) -> str:
    sub_messages = [{"role": "user", "content": prompt}]  # fresh — no history!
    for _ in range(30):                                    # safety limit
        response = client.messages.create(
            model=MODEL, system=SUBAGENT_SYSTEM,
            messages=sub_messages,
            tools=CHILD_TOOLS, max_tokens=8000,
        )
        sub_messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            break                                          # subagent is done
        # ... run tools, append results (same loop as s01) ...
    return "".join(b.text for b in response.content if hasattr(b, "text"))
    #       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    #       Only the final text summary comes back. The whole sub_messages list
    #       is local — it disappears when this function returns.
```

### Step 3: Parent dispatches to subagent or handles directly

```python
for block in response.content:
    if block.type == "tool_use":
        if block.name == "task":
            output = run_subagent(block.input["prompt"])  # spawn child
        else:
            handler = TOOL_HANDLERS.get(block.name)
            output = handler(**block.input)               # handle directly
```

---

## What the Flow Looks Like

```
You: "Check every Python file for syntax errors"

Parent AI: (calls task)
  → prompt: "Check agents/s01_agent_loop.py for syntax errors"
  Subagent: (calls bash: python -m py_compile agents/s01_agent_loop.py)
  Subagent: "No syntax errors found."
  ← summary: "No syntax errors found."

Parent AI: (calls task)
  → prompt: "Check agents/s02_tool_use.py for syntax errors"
  Subagent: (calls bash)
  ← summary: "No syntax errors found."

Parent AI: "All files checked. No syntax errors."
```

The parent only ever holds short summaries. Each subagent lives and dies in its own call.

---

## What Changed From s03

| Piece | Before (s03) | After (s04) |
|-------|-------------|-------------|
| Tools | 5 (bash, read, write, edit, todo) | + `task` (spawn subagent) |
| Memory | Single growing history | Parent clean, child fresh |
| Big tasks | Gets slower and forgetful | Delegated to fresh child |
| Child loop | N/A | Same loop as s01 |

---

## Try It

```sh
cd learn-claude-code
python agents/s04_subagent.py
```

1. `Review all Python files in the agents/ folder and summarize what each one does`
2. `Find all TODO comments across the codebase and report them`
3. `Check every file for syntax errors and list any problems`

---

## Running with Ollama (Local Models)

The subagent pattern works identically with Ollama. The only changes are the standard OpenAI format differences.

### The subagent loop in OpenAI format

```python
def run_subagent(prompt: str) -> str:
    sub_messages = [
        {"role": "system", "content": SUBAGENT_SYSTEM},  # system goes in messages[]
        {"role": "user", "content": prompt},
    ]
    for _ in range(30):
        response = client.chat.completions.create(
            model=MODEL, messages=sub_messages,
            tools=CHILD_TOOLS, tool_choice="auto",
        )
        msg = response.choices[0].message
        sub_messages.append(msg.model_dump(exclude_unset=False))
        if response.choices[0].finish_reason != "tool_calls" or not msg.tool_calls:
            break
        for tool_call in msg.tool_calls:
            args = json.loads(tool_call.function.arguments)
            output = TOOL_HANDLERS[tool_call.function.name](**args)
            sub_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(output)[:50000],
            })
    return msg.content or "(no summary)"
    #      ^^^^^^^^^^^
    #      msg.content instead of iterating over response.content blocks
```

The key idea — fresh `sub_messages = []`, discard after return — is identical.

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s04_subagent_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
