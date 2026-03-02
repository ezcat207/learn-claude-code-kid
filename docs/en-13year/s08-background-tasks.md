# s08: Background Tasks — Doing Two Things at Once

`s01 > s02 > s03 > s04 > s05 > s06 > s07 > [ s08 ] s09 > s10 > s11 > s12`

> **Fire and forget — the agent keeps working while a command runs in the background.**

---

## The Problem: Slow Commands Block Everything

Every time the agent calls `bash`, the whole program freezes and waits. For a quick `ls` that's fine. But for slow commands — installing packages, running tests, building a project — waiting means doing nothing.

Imagine the agent has 3 tasks:
1. Install dependencies (`pip install -r requirements.txt` — takes 30 seconds)
2. Run tests (`pytest` — takes 20 seconds)
3. Check code style (`ruff check .` — takes 2 seconds)

With blocking bash, total time: 52 seconds, working on one thing at a time.

With background tasks: kick off all three, keep working on other things while they run, collect results when done.

---

## The Solution: Threads + a Notification Queue

We add a `background_run` tool that spawns a **background thread** and returns a task ID immediately. The agent keeps going. When the command finishes, the result is placed in a **notification queue**. Before every LLM call, we drain that queue and inject the results into the conversation.

```
Agent ----[background_run: pip install]----[background_run: pytest]----[other work]----
               |                                |
               v                                v
         Thread: pip install            Thread: pytest
               |                                |
               +-----------+--------------------+
                           |
                    notification queue
                           |
                  [drained before next LLM call]
                           |
               <background-results>
                 [bg:a1b2c3d4] completed: pip install ok
                 [bg:e5f6a7b8] completed: 42 passed
               </background-results>
```

---

## How It Works — Step by Step

### Step 1: BackgroundManager — thread pool + queue

```python
class BackgroundManager:
    def run(self, command: str) -> str:
        task_id = str(uuid.uuid4())[:8]   # short random ID
        thread = threading.Thread(
            target=self._execute, args=(task_id, command), daemon=True
        )
        thread.start()
        return f"Background task {task_id} started: {command[:80]}"
        # ^^^^ Returns IMMEDIATELY — agent doesn't wait

    def _execute(self, task_id: str, command: str):
        # Runs in its own thread
        r = subprocess.run(command, ...)
        # When done, push result to notification queue
        self._notification_queue.append({
            "task_id": task_id, "status": "completed", "result": output
        })
```

### Step 2: Drain the queue before each LLM call

```python
def agent_loop(messages: list):
    while True:
        # Check if any background tasks finished
        notifs = BG.drain_notifications()
        if notifs:
            notif_text = "\n".join(
                f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs
            )
            messages.append({"role": "user",
                              "content": f"<background-results>\n{notif_text}\n</background-results>"})
            messages.append({"role": "assistant", "content": "Noted background results."})
        # Now make the LLM call with fresh context
        response = client.messages.create(...)
```

The AI sees the completed results at the top of its next turn — like checking your email before starting the day.

### Step 3: `check_background` lets the AI poll if it needs to

```python
{"name": "check_background",
 "description": "Check background task status. Omit task_id to list all."}
# AI can call this proactively: "How's that pip install going?"
```

---

## What Changed From s07

| Piece | Before (s07) | After (s08) |
|-------|-------------|-------------|
| Slow commands | Block the agent | Run in background thread |
| Parallelism | None | Multiple commands at once |
| New tools | None | `background_run`, `check_background` |
| Result delivery | Immediate | Notification queue, drained before each LLM call |

---

## Try It

```sh
cd learn-claude-code
python agents/s08_background_tasks.py
```

1. `Run these three commands in parallel: ls -la, echo "hello", python --version`
2. `Start a background task that sleeps for 3 seconds, then do some other work, then check on it`
3. `Run pytest in the background while reading requirements.txt`

---

## Running with Ollama (Local Models)

The `BackgroundManager` class, threading logic, and notification queue are **completely unchanged**. This is the easiest Ollama conversion in the series.

### The notification injection is identical

The background notification injection adds plain `"user"` / `"assistant"` messages — no tool calls involved. This part looks exactly the same in both versions:

```python
# Identical in both Anthropic and Ollama versions
notifs = BG.drain_notifications()
if notifs and messages:
    notif_text = "\n".join(
        f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs
    )
    messages.append({"role": "user",
                     "content": f"<background-results>\n{notif_text}\n</background-results>"})
    messages.append({"role": "assistant", "content": "Noted background results."})
```

The only differences are the standard tool format changes from s02: `{"type": "function", ...}` wrapper and `"tool"` role messages.

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s08_background_tasks_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
