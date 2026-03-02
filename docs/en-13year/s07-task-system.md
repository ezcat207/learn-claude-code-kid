# s07: Task System — Memory That Survives Forever

`s01 > s02 > s03 > s04 > s05 > s06 > [ s07 ] s08 > s09 > s10 > s11 > s12`

> **Tasks on disk outlast any conversation. They can't be compressed away.**

---

## The Problem: Plans Disappear When Memory Is Compressed

In s03 we gave the AI a to-do list. It worked — but the list lived inside the conversation. When s06's context compression kicked in and replaced the history with a summary, the to-do list might be summarised as *"the agent was tracking some tasks"* — not the actual task details.

The problem: anything inside the conversation can be lost or garbled by compression. A long project that spans many turns needs a plan that **survives** compression.

---

## The Solution: Tasks as Files

We move tasks out of the conversation entirely and store them as JSON files in `.tasks/`:

```
.tasks/
  task_1.json   {"id": 1, "subject": "Write tests", "status": "completed", ...}
  task_2.json   {"id": 2, "subject": "Fix bug", "status": "in_progress", "blockedBy": []}
  task_3.json   {"id": 3, "subject": "Write docs", "status": "pending", "blockedBy": [2]}
```

The AI never holds the task list in its memory — it asks for it with `task_list`, reads individual tasks with `task_get`. No matter how many times the context gets compressed, the tasks are safe on disk.

We also add a **dependency graph**: tasks can block each other. Task 3 can't start until task 2 is done. When task 2 is marked `completed`, the system automatically removes it from task 3's `blockedBy` list.

---

## How It Works — Step by Step

### Step 1: TaskManager — CRUD with dependencies

```python
class TaskManager:
    def create(self, subject: str, description: str = "") -> str:
        task = {"id": self._next_id, "subject": subject,
                "status": "pending", "blockedBy": [], "blocks": []}
        self._save(task)  # writes .tasks/task_N.json

    def update(self, task_id: int, status: str = None, ...) -> str:
        task = self._load(task_id)
        if status == "completed":
            self._clear_dependency(task_id)  # unblock everything waiting on this
        ...

    def _clear_dependency(self, completed_id: int):
        # Find every other task that lists completed_id in blockedBy, remove it
        for f in self.dir.glob("task_*.json"):
            task = json.loads(f.read_text())
            if completed_id in task["blockedBy"]:
                task["blockedBy"].remove(completed_id)
                self._save(task)
```

### Step 2: Four task tools in the dispatch map

```python
TOOL_HANDLERS = {
    # ...base tools...
    "task_create": lambda **kw: TASKS.create(kw["subject"], kw.get("description", "")),
    "task_update": lambda **kw: TASKS.update(kw["task_id"], kw.get("status"), ...),
    "task_list":   lambda **kw: TASKS.list_all(),   # prints all tasks with status
    "task_get":    lambda **kw: TASKS.get(kw["task_id"]),
}
```

Adding tools never touches the loop — same pattern since s02.

### Step 3: Dependency resolution in action

```
task_1  →  task_2  →  task_3
complete    blocked    blocked

After completing task_1:
  _clear_dependency(1) removes 1 from task_2's blockedBy list
  task_2 is now unblocked → AI can start it
```

---

## What the AI's Flow Looks Like

```
You: "Plan and implement three improvements to utils.py"

AI: (task_create "Add type hints")
AI: (task_create "Add docstrings") — blocks task 1
AI: (task_create "Add main guard")

AI: (task_list)
  [ ] #1: Add type hints
  [ ] #2: Add docstrings
  [ ] #3: Add main guard

AI: (task_update 1, status="in_progress")
AI: (edit_file utils.py — adds type hints)
AI: (task_update 1, status="completed")   ← automatically unblocks anything waiting on 1

AI: (task_update 2, status="in_progress")
...and so on
```

Even if the context is compressed between steps, the task files on disk preserve the full plan.

---

## What Changed From s06

| Piece | Before (s06) | After (s07) |
|-------|-------------|-------------|
| Task tracking | In-conversation todo (s03) | Files in `.tasks/` |
| Survives compression | No | Yes — it's on disk |
| Dependencies | None | `blockedBy` / `blocks` graph |
| New tools | None | `task_create`, `task_update`, `task_list`, `task_get` |

---

## Try It

```sh
cd learn-claude-code
python agents/s07_task_system.py
```

1. `Plan and implement three small improvements to any Python file`
2. `Create a task, mark it in_progress, then complete it`
3. `Create two tasks where the second blocks the first, then complete the first and see the second unblock`

---

## Running with Ollama (Local Models)

The `TaskManager` class and all four task tool functions are **completely unchanged**. The only differences are the standard OpenAI format ones.

### Nothing new here

Task tools return strings (JSON text), which become `"tool"` messages like any other tool. The dependency graph, file persistence, and `_clear_dependency` logic are all identical.

```python
# Dispatch is the same — just a different tool format wrapper
{"type": "function", "function": {
    "name": "task_create",
    "description": "Create a new task.",
    "parameters": {"type": "object",
                   "properties": {"subject": {"type": "string"}},
                   "required": ["subject"]}}}
```

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s07_task_system_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
