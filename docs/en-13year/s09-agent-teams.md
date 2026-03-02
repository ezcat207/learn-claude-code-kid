# s09: Agent Teams — Teammates That Remember and Talk

`s01 > s02 > s03 > s04 > s05 > s06 > s07 > s08 > [ s09 ] s10 > s11 > s12`

> **Unlike subagents, teammates persist. They keep working, go idle, and can be messaged.**

---

## The Problem: Subagents Are One-Shot

In s04, we learned about subagents — child agents that spin up, do a task, return a summary, and disappear. Great for one-off jobs.

But what if you want agents that:
- Work in parallel on different pieces of a big project
- Send messages to each other as they make progress
- Stay alive to receive new instructions after finishing a task
- Have a name and role that you can refer to later

Subagents can't do this. You need **teammates**.

---

## The Solution: Persistent Named Agents with Inboxes

Each teammate is a **thread** that runs its own agent loop indefinitely. They communicate through **JSONL inbox files** — one file per agent, append to send, drain to receive.

```
.team/config.json          .team/inbox/
  {members: [              alice.jsonl   ← messages for alice
    alice (coder): idle    bob.jsonl     ← messages for bob
    bob (reviewer): working lead.jsonl   ← messages for lead
  ]}

send_message("alice", "fix the bug"):
  open("alice.jsonl", "a").write(json message)

alice's loop reads inbox every turn:
  inbox = read_inbox("alice")   ← drain alice.jsonl
  for msg in inbox:
      messages.append(...)      ← inject into alice's conversation
```

---

## How It Works — Step by Step

### Step 1: MessageBus — JSONL inbox files

```python
class MessageBus:
    def send(self, sender: str, to: str, content: str, msg_type="message") -> str:
        msg = {"type": msg_type, "from": sender, "content": content, "timestamp": ...}
        with open(f".team/inbox/{to}.jsonl", "a") as f:   # append to inbox
            f.write(json.dumps(msg) + "\n")

    def read_inbox(self, name: str) -> list:
        inbox_path = f".team/inbox/{name}.jsonl"
        messages = [json.loads(l) for l in inbox_path.read_text().splitlines()]
        inbox_path.write_text("")    # drain after reading
        return messages
```

Sending is just appending a line to a file. Reading drains the file. Simple and reliable — works across threads without locks.

### Step 2: TeammateManager — spawn and run

```python
class TeammateManager:
    def spawn(self, name: str, role: str, prompt: str) -> str:
        thread = threading.Thread(
            target=self._teammate_loop,
            args=(name, role, prompt),
            daemon=True,
        )
        thread.start()
        return f"Spawned '{name}' (role: {role})"

    def _teammate_loop(self, name: str, role: str, prompt: str):
        messages = [{"role": "user", "content": prompt}]   # start with the initial task
        for _ in range(50):                                  # safety limit
            inbox = BUS.read_inbox(name)                     # check for new messages
            for msg in inbox:
                messages.append({"role": "user", "content": json.dumps(msg)})
            response = client.messages.create(...)           # same agent loop
            if response.stop_reason != "tool_use":
                break                                        # done for now → goes idle
        member["status"] = "idle"                           # ready for more work
```

### Step 3: Five message types

```python
VALID_MSG_TYPES = {
    "message",               # normal text
    "broadcast",             # sent to all teammates at once
    "shutdown_request",      # ask a teammate to stop (handled in s10)
    "shutdown_response",     # their reply (handled in s10)
    "plan_approval_response" # approve/reject a plan (handled in s10)
}
```

Not all types are fully handled in s09 — s10 adds the shutdown and approval flows.

### Step 4: Lead reads its inbox before each turn

```python
def agent_loop(messages: list):
    while True:
        inbox = BUS.read_inbox("lead")      # check if any teammates sent messages
        if inbox:
            messages.append({"role": "user",
                              "content": f"<inbox>{json.dumps(inbox)}</inbox>"})
            messages.append({"role": "assistant", "content": "Noted inbox messages."})
        response = client.messages.create(...)
```

The lead checks its inbox the same way teammates do.

---

## Subagent (s04) vs Teammate (s09)

| | Subagent | Teammate |
|---|---|---|
| Lifetime | Spawn → work → die | Spawn → work → idle → work → ... |
| Context | Fresh every time | Persists across messages |
| Communication | One prompt in, one summary out | Inbox/outbox messaging |
| Config | None | `.team/config.json` |
| Good for | Isolated one-shot tasks | Long-running collaborative work |

---

## What Changed From s08

| Piece | Before (s08) | After (s09) |
|-------|-------------|-------------|
| Other agents | Subagents (ephemeral) | Teammates (persistent) |
| Communication | None between agents | JSONL inbox files |
| Parallelism | Background threads | Named teammate threads |
| New tools | None | `spawn_teammate`, `list_teammates`, `send_message`, `read_inbox`, `broadcast` |

---

## Try It

```sh
cd learn-claude-code
python agents/s09_agent_teams.py
```

1. `Spawn a teammate named alice with role "coder" and ask her to list all Python files`
2. `Check /team to see teammate status, then check /inbox to see if alice replied`
3. `Spawn two teammates to work on different files in parallel, then collect their summaries`

---

## Running with Ollama (Local Models)

The `MessageBus` and `TeammateManager` classes are **identical**. The one meaningful change is inside `_teammate_tools()` and `_teammate_loop()` — both now use OpenAI format.

### The teammate loop in OpenAI format

```python
def _teammate_loop(self, name: str, role: str, prompt: str):
    sys_prompt = f"You are '{name}', role: {role}..."
    messages = [
        {"role": "system", "content": sys_prompt},  # system in messages[]
        {"role": "user", "content": prompt},
    ]
    for _ in range(50):
        inbox = BUS.read_inbox(name)
        for msg in inbox:
            messages.append({"role": "user", "content": json.dumps(msg)})
        response = client.chat.completions.create(
            model=MODEL, messages=messages,
            tools=tools, tool_choice="auto",
        )
        msg_obj = response.choices[0].message
        messages.append(msg_obj.model_dump(exclude_unset=False))
        if response.choices[0].finish_reason != "tool_calls" or not msg_obj.tool_calls:
            break
        for tool_call in msg_obj.tool_calls:
            args = json.loads(tool_call.function.arguments)
            output = self._exec(name, tool_call.function.name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(output),
            })
```

The threading, inbox checking, idle state transition — all unchanged.

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s09_agent_teams_ollama.py
```

Special commands still work:
```sh
s09-ollama >> /team    # list teammates and their status
s09-ollama >> /inbox   # read the lead's inbox
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
