# s12: Worktree + Task Isolation — One Directory Per Task

`s01 > s02 > s03 > s04 > s05 > s06 > s07 > s08 > s09 > s10 > s11 > [ s12 ]`

> **Tasks are the control plane. Worktrees are the execution plane. They bind by ID.**

---

## The Problem: Parallel Changes Conflict

When the agent works on multiple tasks simultaneously, changes in one task can break another. Installing a library for task A could affect task B's tests. Editing the same file for two tasks causes merge confusion.

The solution: give each task its own isolated directory.

---

## The Solution: Git Worktrees + Task Binding

Git worktrees let you check out the same repo at multiple paths simultaneously. Each task gets its own worktree branch:

```
main repo at /project
  ├── .worktrees/
  │   ├── index.json         (worktree registry)
  │   ├── events.jsonl       (lifecycle audit log)
  │   ├── auth-refactor/     (task 12's isolated directory)
  │   └── add-tests/         (task 15's isolated directory)
  └── .tasks/
      ├── task_12.json       (status: in_progress, worktree: auth-refactor)
      └── task_15.json       (status: in_progress, worktree: add-tests)
```

The task knows its worktree by name. The worktree knows its task by ID.

---

## How It Works — Step by Step

### Step 1: WorktreeManager — creates and tracks worktrees

```python
def create(self, name: str, task_id: int = None, base_ref: str = "HEAD") -> str:
    branch = f"wt/{name}"
    self._run_git(["worktree", "add", "-b", branch, str(path), base_ref])
    entry = {
        "name": name, "path": str(path), "branch": branch,
        "task_id": task_id, "status": "active"
    }
    self._save_index(entry)           # add to .worktrees/index.json
    if task_id:
        self.tasks.bind_worktree(task_id, name)  # link task → worktree
    self.events.emit("worktree.create.after", ...)
```

Creates the git branch, registers in the index, binds to the task, emits a lifecycle event.

### Step 2: TaskManager — adds worktree binding

```python
def bind_worktree(self, task_id: int, worktree: str, owner: str = "") -> str:
    task = self._load(task_id)
    task["worktree"] = worktree          # link task → worktree name
    if task["status"] == "pending":
        task["status"] = "in_progress"   # auto-advance status
    self._save(task)
```

The task file tracks which worktree it lives in. This survives context compression (it's on disk).

### Step 3: worktree_run — execute commands in isolation

```python
def run(self, name: str, command: str) -> str:
    wt = self._find(name)
    path = Path(wt["path"])
    r = subprocess.run(command, shell=True, cwd=path, ...)
```

`cwd=path` means the command runs inside the worktree directory — completely isolated from the main workspace.

### Step 4: EventBus — append-only audit log

```python
class EventBus:
    def emit(self, event: str, task: dict = None, worktree: dict = None, error: str = None):
        payload = {"event": event, "ts": time.time(), "task": task or {}, "worktree": worktree or {}}
        self.path.open("a").write(json.dumps(payload) + "\n")
```

Every create/remove/keep/fail emits an event. The AI can call `worktree_events` to see the full lifecycle history.

### Step 5: Closeout — keep or remove

```python
# worktree_remove: remove the worktree and optionally complete its task
def remove(self, name: str, force: bool = False, complete_task: bool = False) -> str:
    self._run_git(["worktree", "remove", wt["path"]])
    if complete_task:
        self.tasks.update(task_id, status="completed")
        self.tasks.unbind_worktree(task_id)

# worktree_keep: mark as kept (for review) without removing
def keep(self, name: str) -> str:
    item["status"] = "kept"
    self._save_index(idx)
```

`remove` with `complete_task=True` is the clean finish: wipe the worktree and mark the task done in one call.

---

## The 16 Tools

| Category | Tools |
|----------|-------|
| Base | `bash`, `read_file`, `write_file`, `edit_file` |
| Tasks | `task_create`, `task_list`, `task_get`, `task_update`, `task_bind_worktree` |
| Worktrees | `worktree_create`, `worktree_list`, `worktree_status`, `worktree_run`, `worktree_keep`, `worktree_remove`, `worktree_events` |

---

## What Changed From s11

| Piece | Before (s11) | After (s12) |
|-------|-------------|-------------|
| Task isolation | None (shared workspace) | Git worktree per task |
| Parallelism | Thread-based teammates | Directory-based isolation |
| Observability | None | `EventBus` lifecycle events |
| New classes | None | `WorktreeManager`, `EventBus` |
| New tools | None | 7 worktree tools + `task_bind_worktree` |

---

## Try It

```sh
cd learn-claude-code
python agents/s12_worktree_task_isolation.py
```

1. `Create a task called "add logging" and allocate a worktree for it`
2. `Run git log in the auth-refactor worktree`
3. `Create two tasks and two worktrees for them in parallel, then check their status`

---

## Running with Ollama (Local Models)

This is the **simplest Ollama conversion** in the series. There are no threads and no special protocol logic. The `WorktreeManager`, `TaskManager`, and `EventBus` classes are **completely unchanged**. The only differences are the standard OpenAI format conversions.

### What changes

Tool definitions wrap with `{"type": "function", "function": {...}}`. Tool results become separate `"tool"` messages. Stop condition changes to `finish_reason != "tool_calls"`. System prompt moves into `messages[]`.

```python
# Anthropic agent_loop
response = client.messages.create(
    model=MODEL, system=SYSTEM, messages=messages, tools=TOOLS, max_tokens=8000
)
messages.append({"role": "assistant", "content": response.content})
if response.stop_reason != "tool_use":
    return
for block in response.content:
    if block.type == "tool_use":
        output = handler(**block.input)
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(output)})
messages.append({"role": "user", "content": results})

# Ollama agent_loop
response = client.chat.completions.create(
    model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
)
msg = response.choices[0].message
messages.append(msg.model_dump(exclude_unset=False))
if response.choices[0].finish_reason != "tool_calls":
    return
for tool_call in msg.tool_calls:
    args = json.loads(tool_call.function.arguments)
    output = handler(**args)
    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": str(output)})
```

All 16 tools, the `TOOL_HANDLERS` dict, and the manager classes are identical.

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s12_worktree_task_isolation_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
