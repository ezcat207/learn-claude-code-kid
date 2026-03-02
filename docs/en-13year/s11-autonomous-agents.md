# s11: Autonomous Agents — The Agent Finds Work Itself

`s01 > s02 > s03 > s04 > s05 > s06 > s07 > s08 > s09 > s10 > [ s11 ] s12`

> **Teammates don't wait for instructions. They poll for tasks and claim them.**

---

## The Problem: The Lead Is a Bottleneck

In s09–s10, the lead had to tell each teammate exactly what to do. With many teammates and many tasks, the lead becomes a coordination bottleneck — constantly assigning work instead of doing work.

What if teammates could find work themselves?

---

## The Solution: Work/Idle Loop + Task Board Polling

Each teammate runs a two-phase loop:

```
+-------+
| spawn |
+---+---+
    |
    v
+-------+  tool_calls  +-------+
| WORK  | <----------- |  LLM  |
+---+---+              +-------+
    |
    | finish_reason != tool_calls  OR  idle tool called
    v
+--------+
| IDLE   | poll every 5s for up to 60s
+---+----+
    |
    +---> inbox message? → inject into messages → resume WORK
    |
    +---> unclaimed task in .tasks/? → claim it → resume WORK
    |
    +---> timeout → shutdown
```

When in the WORK phase, the teammate calls `idle` when it runs out of work. When in the IDLE phase, it polls `.tasks/` for unclaimed tasks.

---

## How It Works — Step by Step

### Step 1: scan_unclaimed_tasks — finds work without a lead

```python
def scan_unclaimed_tasks() -> list:
    for f in sorted(TASKS_DIR.glob("task_*.json")):
        task = json.loads(f.read_text())
        if (task.get("status") == "pending"
                and not task.get("owner")
                and not task.get("blockedBy")):
            unclaimed.append(task)
    return unclaimed
```

A task is claimable when it's `pending`, has no `owner`, and no `blockedBy` dependencies.

### Step 2: claim_task — atomic ownership grab

```python
def claim_task(task_id: int, owner: str) -> str:
    with _claim_lock:              # prevents two teammates claiming the same task
        task = json.loads(path.read_text())
        task["owner"] = owner
        task["status"] = "in_progress"
        path.write_text(json.dumps(task, indent=2))
    return f"Claimed task #{task_id} for {owner}"
```

The `_claim_lock` prevents race conditions when two teammates see the same unclaimed task.

### Step 3: idle tool triggers phase transition

```python
# In the work phase loop:
for tool_call in msg_obj.tool_calls:
    if tool_call.function.name == "idle":
        idle_requested = True
        output = "Entering idle phase. Will poll for new tasks."
    else:
        output = self._exec(name, tool_call.function.name, args)
    # append tool result...
if idle_requested:
    break  # exit work phase → enter idle phase
```

The AI calls `idle` when it has no more work. This exits the work loop.

### Step 4: Identity re-injection after compression

When context is compressed, the teammate might forget who it is. If only a few messages remain, the loop injects an identity reminder:

```python
if len(messages) <= 3:
    messages.insert(0, make_identity_block(name, role, team_name))
    messages.insert(1, {"role": "assistant", "content": f"I am {name}. Continuing."})
```

```python
def make_identity_block(name: str, role: str, team_name: str) -> dict:
    return {
        "role": "user",
        "content": f"<identity>You are '{name}', role: {role}, team: {team_name}. Continue your work.</identity>",
    }
```

---

## What Changed From s10

| Piece | Before (s10) | After (s11) |
|-------|-------------|-------------|
| Task assignment | Lead assigns manually | Teammates auto-claim from `.tasks/` |
| Teammate lifecycle | work → idle (permanent) | work → idle → work → ... |
| New tools | None | `idle`, `claim_task` |
| New functions | None | `scan_unclaimed_tasks`, `claim_task`, `make_identity_block` |

---

## Try It

```sh
cd learn-claude-code
python agents/s11_autonomous_agents.py
```

1. Create some tasks with `/tasks`, then `Spawn a teammate named alice with role "coder"` and watch her auto-claim them
2. `Spawn two teammates to work in parallel — they'll compete to claim the same tasks`
3. Use `/team` to watch teammates move between working/idle states

---

## Running with Ollama (Local Models)

The `scan_unclaimed_tasks`, `claim_task`, `make_identity_block` functions and the `_claim_lock` / `_tracker_lock` logic are **completely unchanged**. The TeammateManager `_loop` uses OpenAI format.

### The idle detection change

Anthropic checks `block.name`; OpenAI checks `tool_call.function.name`:

```python
# Anthropic version (s11)
for block in response.content:
    if block.type == "tool_use":
        if block.name == "idle":
            idle_requested = True

# Ollama version (s11_ollama)
for tool_call in msg_obj.tool_calls:
    if tool_call.function.name == "idle":
        idle_requested = True
```

The idle phase polling loop, inbox checks, and task scanning are identical in both versions.

### The teammate loop in OpenAI format

```python
def _loop(self, name: str, role: str, prompt: str):
    messages = [
        {"role": "system", "content": sys_prompt},  # system in messages[]
        {"role": "user", "content": prompt},
    ]
    while True:
        # -- WORK PHASE --
        for _ in range(50):
            response = client.chat.completions.create(
                model=MODEL, messages=messages,
                tools=tools, tool_choice="auto",
            )
            msg_obj = response.choices[0].message
            messages.append(msg_obj.model_dump(exclude_unset=False))
            if response.choices[0].finish_reason != "tool_calls":
                break
            idle_requested = any(
                tc.function.name == "idle" for tc in msg_obj.tool_calls
            )
            for tool_call in msg_obj.tool_calls:
                output = ...
                messages.append({"role": "tool", "tool_call_id": ..., "content": ...})
            if idle_requested:
                break
        # -- IDLE PHASE: identical to Anthropic version --
        ...
```

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s11_autonomous_agents_ollama.py
```

Special commands:
```sh
s11-ollama >> /team    # list teammates and status
s11-ollama >> /inbox   # read lead's inbox
s11-ollama >> /tasks   # list all tasks
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
