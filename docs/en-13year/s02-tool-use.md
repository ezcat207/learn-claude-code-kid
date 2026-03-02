# s02: Tool Use — Giving the Agent Better Tools

`s01 > [ s02 ] s03 > s04 > s05 > s06 | s07 > s08 > s09 > s10 > s11 > s12`

> **Adding a tool = adding one handler. The loop never changes.**

---

## The Problem: One Tool Isn't Enough (and It's Risky)

In s01, the only tool was `bash` — the AI could run any terminal command it wanted.

That's like giving someone a Swiss Army knife and saying "use this for everything." It works, but it's messy and dangerous:

- `cat` (the command to print a file) cuts off long files in weird ways
- `sed` (a text-editing command) breaks on special characters like `$` or `\`
- The AI could accidentally run a command that deletes files or does something unexpected — there's no safety net

**Better idea:** give the AI specific tools with guardrails built in. A `read_file` tool that's *only* for reading files. A `write_file` tool that's *only* for writing. Each one safe by design.

**Key insight:** adding new tools does *not* require touching the loop from s01.

---

## The Solution: A Tool Menu + a Locked Room

Instead of one all-powerful bash command, we build a **dispatch map** — think of it like a restaurant menu that maps each item name to the kitchen station that makes it:

```
"read_file"  →  run_read()    (reads a file safely)
"write_file" →  run_write()   (writes a file safely)
"edit_file"  →  run_edit()    (changes part of a file)
"bash"       →  run_bash()    (still there, for everything else)
```

When the AI calls a tool, we just look it up in the menu and run the right function.

We also add a **sandbox** (a locked room): all file tools check that the path stays inside the project folder. The AI can't accidentally reach outside.

---

## How It Works — Step by Step

### Step 1: A safe path checker

Before reading or writing any file, we make sure the path is inside our project folder:

```python
def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()      # turn "subdir/file.txt" into a full path
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path
# If the AI tries to read "/etc/passwords", this raises an error and stops it.
# WORKDIR = our project folder, the "locked room"
```

### Step 2: Each tool is its own function

```python
def run_read(path: str, limit: int = None) -> str:
    text = safe_path(path).read_text()  # read the file (safe_path checks first)
    lines = text.splitlines()           # split into a list of lines
    if limit and limit < len(lines):
        lines = lines[:limit]           # only return the first `limit` lines
    return "\n".join(lines)[:50000]     # cap at 50,000 characters total
```

### Step 3: The dispatch map — tool name → function

```python
TOOL_HANDLERS = {
    "bash":       lambda **kw: run_bash(kw["command"]),
    "read_file":  lambda **kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda **kw: run_write(kw["path"], kw["content"]),
    "edit_file":  lambda **kw: run_edit(kw["path"], kw["old_text"], kw["new_text"]),
}
# lambda **kw: ...  means "a small function that takes any named arguments"
# kw["path"] means "the argument named 'path'"
```

This is a Python dictionary (`{}`). Instead of writing a long `if/elif` chain:
```python
# Old messy way:
if tool_name == "bash":
    run_bash(...)
elif tool_name == "read_file":
    run_read(...)
elif tool_name == "write_file":
    ...
```
We just do one lookup: `TOOL_HANDLERS[tool_name]` — cleaner, and adding a new tool is just one new line.

### Step 4: The loop uses the map (same loop as s01, tiny change)

```python
for block in response.content:
    if block.type == "tool_use":
        handler = TOOL_HANDLERS.get(block.name)   # look up by name
        output = handler(**block.input) if handler \
            else f"Unknown tool: {block.name}"     # run it, or report unknown
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": output,
        })
```

The loop body is almost identical to s01. We just replaced the hardcoded `run_bash(...)` with a lookup.

---

## What Changed From s01

| Piece | Before (s01) | After (s02) |
|-------|-------------|-------------|
| Tools | 1 (bash only) | 4 (bash, read, write, edit) |
| Dispatch | Hardcoded bash call | `TOOL_HANDLERS` dictionary |
| File safety | None | `safe_path()` blocks escaping the folder |
| Agent loop | Unchanged | Still unchanged |

---

## Try It

```sh
cd learn-claude-code
python agents/s02_tool_use.py
```

1. `Read the file requirements.txt`
2. `Create a file called greet.py with a greet(name) function`
3. `Edit greet.py to add a docstring to the function`
4. `Read greet.py to verify the edit worked`

---

## Running with Ollama (Local Models)

The dispatch-map pattern works identically with Ollama. The only changes are in how tools are **defined** and how results are **sent back**.

### Tool definition format

Anthropic wraps the schema directly on the tool. OpenAI adds a `"function"` wrapper:

```python
# Anthropic format (s02_tool_use.py)
{"name": "read_file",
 "description": "Read file contents.",
 "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}

# OpenAI/Ollama format (s02_tool_use_ollama.py)
{"type": "function", "function": {
    "name": "read_file",
    "description": "Read file contents.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}
#  ^^^^^^^^^^^^^^^^^^^^^^^^^^^
#  Extra "type"+"function" wrapper — only difference
```

### Tool result format

Anthropic tool results are blocks inside a single `"user"` message. OpenAI makes each result its own `"tool"` message:

```python
# Anthropic format
messages.append({"role": "user", "content": [
    {"type": "tool_result", "tool_use_id": block.id, "content": output},
    # more results...
]})

# OpenAI/Ollama format — one message per result
for tool_call in msg.tool_calls:
    args = json.loads(tool_call.function.arguments)
    output = TOOL_HANDLERS[tool_call.function.name](**args)
    messages.append({
        "role": "tool",           # its own message, not nested in "user"
        "tool_call_id": tool_call.id,
        "content": output,
    })
```

The dispatch map itself (`TOOL_HANDLERS`) and all the tool functions (`run_read`, `run_write`, etc.) are **completely unchanged**.

### Setup

```sh
ollama pull glm-4.7:cloud   # or any tool-capable model
python agents/s02_tool_use_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
