# s03: TodoWrite — Giving the Agent a To-Do List

`s01 > s02 > [ s03 ] s04 > s05 > s06 | s07 > s08 > s09 > s10 > s11 > s12`

> **An agent without a plan drifts. List the steps first, then execute.**

---

## The Problem: The AI Forgets What It Was Doing

AI models have a **context window** — think of it like short-term memory. The AI can only "see" a certain amount of text at once. As the conversation gets longer, old parts scroll off and get crowded out.

Here's what goes wrong on a big task:

1. You ask: *"Refactor this file: add type hints, docstrings, and a main guard"* (3 sub-tasks)
2. AI starts: does type hints ✓, does docstrings ✓ — going great
3. But now the conversation is long. The original instructions are buried way back
4. The AI starts making stuff up or repeating work because it forgot step 3 existed

It's like being asked to do 10 chores, but the list was on the first page of a very long notebook — by chore 5, you've forgotten what 6-10 were.

---

## The Solution: A Sticky Note That Updates

We give the AI a new tool: `todo`. It works like a visible sticky note that the AI writes on and checks throughout its work.

```
[ ] Add type hints        ← not started yet
[>] Add docstrings        ← currently doing this
[x] Add main guard        ← done!
```

The AI uses this tool to write its plan at the start, mark tasks in-progress as it works, and check them off when done. The sticky note is always part of the conversation, so it never gets forgotten.

We also add a **nag reminder**: if the AI goes 3 rounds without updating its to-do list, the system automatically injects a nudge: *"Hey, update your todos."* Like a parent reminding you to check your homework list.

---

## How It Works — Step by Step

### Step 1: The TodoManager keeps track of tasks

```python
class TodoManager:
    def update(self, items: list) -> str:
        validated, in_progress_count = [], 0
        for item in items:
            status = item.get("status", "pending")  # "pending", "in_progress", or "done"
            if status == "in_progress":
                in_progress_count += 1              # count how many are active
            validated.append({"id": item["id"], "text": item["text"],
                              "status": status})
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress")
        # ^^^ Only ONE task can be marked "doing" at a time.
        # This forces the AI to focus instead of juggling 5 things at once.
        self.items = validated
        return self.render()  # returns a printable version of the list
```

`class` is a way to group related data and functions together. `TodoManager` is like a whiteboard object: it holds the task list and knows how to update and display it.

### Step 2: `todo` goes into the tool menu like any other tool

```python
TOOL_HANDLERS = {
    # ...tools from s02...
    "todo": lambda **kw: TODO.update(kw["items"]),
}
# TODO = one shared TodoManager for the whole session
```

Nothing special here — it's just another entry in the dispatch map from s02.

### Step 3: The nag reminder

```python
if rounds_since_todo >= 3 and messages:        # been 3 rounds since last todo update?
    last = messages[-1]                         # grab the last message
    if last["role"] == "user" and isinstance(last.get("content"), list):
        last["content"].insert(0, {
            "type": "text",
            "text": "<reminder>Update your todos.</reminder>",
        })
# This inserts a reminder INTO the tool results we're about to send back.
# The AI sees it and thinks "oh right, I should update my list."
```

`rounds_since_todo` is a counter that resets to 0 every time the AI calls the `todo` tool. If it reaches 3, we slip a reminder into the next message — the AI sees it automatically.

---

## What the AI's Flow Looks Like Now

```
You: "Refactor hello.py: type hints, docstrings, main guard"

AI: (calls todo)
    [ ] Add type hints
    [ ] Add docstrings
    [ ] Add main guard

AI: (calls read_file "hello.py", then edit_file to add type hints)
    (calls todo)
    [x] Add type hints
    [>] Add docstrings
    [ ] Add main guard

AI: (calls edit_file to add docstrings)
    (calls todo)
    [x] Add type hints
    [x] Add docstrings
    [>] Add main guard

AI: (calls edit_file to add main guard)
    (calls todo)
    [x] Add type hints
    [x] Add docstrings
    [x] Add main guard

AI: "Done! All three changes are complete."
```

The list acts as a shared memory that doesn't fade, even in a long conversation.

---

## What Changed From s02

| Piece | Before (s02) | After (s03) |
|-------|-------------|-------------|
| Tools | 4 | 5 (+ `todo`) |
| Planning | None | TodoManager with statuses |
| Nag reminder | None | `<reminder>` injected after 3 rounds |
| Agent loop | Simple dispatch | + `rounds_since_todo` counter |

---

## Try It

```sh
cd learn-claude-code
python agents/s03_todo_write.py
```

1. `Refactor the file hello.py: add type hints, docstrings, and a main guard`
2. `Create a Python package with __init__.py, utils.py, and tests/test_utils.py`
3. `Review all Python files and fix any style issues`

---

## Running with Ollama (Local Models)

The `TodoManager` and all tool logic are **identical**. The only thing that changes is how the nag reminder is injected, because the message formats differ.

### The nag reminder difference

In the Anthropic version, the reminder is a `{"type": "text"}` block slipped *inside* the user message that carries tool results — all in one message:

```python
# Anthropic: reminder lives inside the tool-results user message
results.insert(0, {"type": "text", "text": "<reminder>Update your todos.</reminder>"})
messages.append({"role": "user", "content": results})
```

In the OpenAI/Ollama version, tool results are separate `"tool"` messages, so there's no single user message to insert into. Instead, we append a plain `"user"` message right after:

```python
# Ollama: reminder is a separate user message that follows the tool results
for tool_call in msg.tool_calls:
    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": output})

if rounds_since_todo >= 3:
    messages.append({"role": "user", "content": "<reminder>Update your todos.</reminder>"})
#                   ^^^^^^^^^^^^^^^^^^^^^^^^^
#   Comes after all "tool" messages — the model sees it on its next turn
```

The AI sees the reminder at the top of its next context, just like before. Same effect, different placement.

### Everything else is unchanged

| Piece | Anthropic (s03) | Ollama (s03_ollama) |
|-------|----------------|---------------------|
| `TodoManager` class | ✓ | identical |
| Tool functions | ✓ | identical |
| `TOOL_HANDLERS` map | ✓ | identical |
| `rounds_since_todo` counter | ✓ | identical |
| Nag reminder | inside user message | separate user message |
| Tool format | `input_schema` | `function.parameters` |

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s03_todo_write_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
