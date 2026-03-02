# s06: Context Compact — Making the Agent Work Forever

`s01 > s02 > s03 > s04 > s05 > [ s06 ] | s07 > s08 > s09 > s10 > s11 > s12`

> **The agent that forgets strategically never runs out of memory.**

---

## The Problem: Long Sessions Die

Every message you exchange with the AI takes up space in the context window. Over a long session, the window fills up:

```
Turn 1:  [user][assistant]                       — plenty of room
Turn 10: [user][assistant][tool][tool][tool]...  — getting full
Turn 30: [user][assistant]...[tool][tool][tool]  — almost no room left
Turn 40: ❌ Error: context length exceeded
```

The AI can't see the beginning of the conversation anymore. It forgets what it was doing. Or it just crashes.

Subagents (s04) help for isolated tasks, but what about one long ongoing session — like a full refactor or a big debugging session?

---

## The Solution: Three Layers of Forgetting

We build a **compression pipeline** that runs automatically. Three layers, each kicking in at a different severity:

```
Layer 1: micro_compact   — silent, every turn
  Old tool results → "[Previous: used bash]"  (saves ~90% of their size)

Layer 2: auto_compact    — when tokens > 50,000
  Save full transcript to disk
  Ask LLM: "summarize this conversation"
  Replace entire history with the summary

Layer 3: compact tool    — AI decides it needs it
  Same as auto_compact, but triggered by the AI itself
```

Think of it like a desk:
- Layer 1: clear away old sticky notes (micro)
- Layer 2: file everything away and start fresh with a summary (auto)
- Layer 3: the AI calls for a filing break itself (manual)

---

## How It Works — Step by Step

### Layer 1: micro_compact — trim old tool results

Most tool results are long file contents or command output. Once they're a few turns old, the AI has already processed them. We can safely shrink them.

```python
def micro_compact(messages: list) -> list:
    # Find all tool_result entries in the message history
    tool_results = [...]  # positions of all tool results
    if len(tool_results) <= KEEP_RECENT:   # keep last 3 untouched
        return messages
    # Replace old ones with a tiny placeholder
    for old_result in tool_results[:-KEEP_RECENT]:
        old_result["content"] = f"[Previous: used {tool_name}]"
    #                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    #   Was: 5000 chars of file content
    #   Now: 28 chars
```

This runs silently before every LLM call. The AI still knows what tools it ran — just not what they returned.

### Layer 2: auto_compact — summarize when memory is full

```python
def auto_compact(messages: list) -> list:
    # 1. Save the full conversation to disk (never lose data)
    transcript_path = TRANSCRIPT_DIR / f"transcript_{int(time.time())}.jsonl"
    # ... write messages to file ...

    # 2. Ask the LLM to summarize what happened
    response = client.messages.create(
        model=MODEL,
        messages=[{"role": "user", "content":
            "Summarize this conversation for continuity. Include: "
            "1) What was accomplished, 2) Current state, 3) Key decisions made.\n\n"
            + conversation_text}],
    )
    summary = response.content[0].text

    # 3. Replace the whole history with just the summary
    return [
        {"role": "user",      "content": f"[Compressed. Transcript: {transcript_path}]\n\n{summary}"},
        {"role": "assistant", "content": "Understood. Continuing from summary."},
    ]
    # Two messages instead of 200. Full transcript is safe on disk.
```

### Layer 3: The `compact` tool — AI-triggered compression

```python
TOOLS = [
    # ...base tools...
    {"name": "compact", "description": "Trigger manual conversation compression.",
     "input_schema": {"type": "object", "properties":
         {"focus": {"type": "string", "description": "What to preserve in the summary"}}}},
]
# AI can call this anytime it feels like the context is getting messy.
```

### Everything plugged into the loop

```python
def agent_loop(messages: list):
    while True:
        micro_compact(messages)                           # Layer 1: every turn
        if estimate_tokens(messages) > THRESHOLD:
            messages[:] = auto_compact(messages)         # Layer 2: when full
        response = client.messages.create(...)
        # ...tool dispatch...
        if manual_compact:
            messages[:] = auto_compact(messages)         # Layer 3: AI-triggered
```

---

## What Changed From s05

| Piece | Before (s05) | After (s06) |
|-------|-------------|-------------|
| Session length | Crashes when context fills | Runs indefinitely |
| Tool results | Kept forever, full size | Old ones compressed (Layer 1) |
| Long history | Crashes | Auto-summarized (Layer 2) |
| AI control | Can't compress | Can call `compact` tool (Layer 3) |
| Data safety | Lost on crash | Full transcripts saved to disk |

---

## Try It

```sh
cd learn-claude-code
python agents/s06_context_compact.py
```

1. `Read all the Python files in agents/ one by one and describe what each does` (lots of reads — triggers Layer 1)
2. Have a very long back-and-forth session until you see `[auto_compact triggered]` (Layer 2)
3. Type `Please compact your context` and watch the AI call the compact tool (Layer 3)

---

## Running with Ollama (Local Models)

The three-layer compression pipeline works with Ollama. The main adaptation is in **Layer 1 (`micro_compact`)**, because the OpenAI message format stores tool results differently.

### The micro_compact difference

In the Anthropic format, tool results are blocks *nested inside* a `"user"` message. In OpenAI format, they are separate `"tool"` role messages. So micro_compact looks for `role == "tool"` messages instead:

```python
# Anthropic micro_compact: find tool_result blocks inside user messages
for msg in messages:
    if msg["role"] == "user":
        for part in msg["content"]:
            if part.get("type") == "tool_result":
                # compress if old

# Ollama micro_compact: find "tool" role messages directly
tool_msg_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
# Build tool_call_id -> name map from assistant messages' tool_calls list
tool_name_map = {}
for msg in messages:
    if msg.get("role") == "assistant":
        for tc in (msg.get("tool_calls") or []):
            tool_name_map[tc["id"]] = tc["function"]["name"]
# Compress old tool messages
for idx in tool_msg_indices[:-KEEP_RECENT]:
    messages[idx]["content"] = f"[Previous: used {tool_name_map[...]}]"
```

### The auto_compact difference

`auto_compact` calls the LLM to write a summary. In OpenAI format that uses `client.chat.completions.create()` and reads `response.choices[0].message.content` instead of `response.content[0].text`:

```python
# Anthropic
response = client.messages.create(model=MODEL, messages=[...])
summary = response.content[0].text

# Ollama
response = client.chat.completions.create(model=MODEL, messages=[...])
summary = response.choices[0].message.content
```

Everything else — the transcript saving, the threshold check, the manual `compact` tool — is identical.

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s06_context_compact_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
