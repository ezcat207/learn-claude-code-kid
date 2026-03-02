# s01: The Agent Loop — How AI Actually *Does* Stuff

`[ s01 ] s02 > s03 > s04 > s05 > s06 | s07 > s08 > s09 > s10 > s11 > s12`

> **One loop + one tool = an agent.**

---

## The Problem: AI Can Talk, But It Can't *Act*

Imagine you're texting a super-smart friend who knows everything — but they're stuck in a room with no windows, no computer, and no phone. You can ask them questions and they'll answer, but they can't *check* anything for you. They can't open a file. They can't run your code. They can only think.

That's what an AI (like Claude or ChatGPT) is by default. It can *reason* about code, but it can't touch the real world.

**Without a loop:** every time the AI needs to run a command, *you* have to manually copy-paste the result back. You're doing the work of a computer. You become the loop.

---

## The Solution: Give It a Loop + a Tool

We give the AI one tool — the ability to run a **bash command** (a line you type in a terminal, like `ls` to list files or `python hello.py` to run a program).

Then we wrap everything in a loop:

```
You ask a question
  → AI thinks, decides to run a command
    → Computer runs the command, gets the result
      → AI sees the result, thinks again
        → AI runs another command... or stops
```

The loop keeps going until the AI says *"I'm done, no more commands needed."*

---

## How It Works — Step by Step

Think of it like passing notes back and forth in class — except you keep the whole stack so everyone remembers the full conversation.

### Step 1: Your question becomes the first note

```python
messages.append({"role": "user", "content": query})
#                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
#   A note that says: "From: user | Message: <your question>"
#
#   messages = a list (stack of notes) that grows over time
```

### Step 2: Send everything to the AI

```python
response = client.messages.create(
    model=MODEL,       # which AI to use, e.g. "claude-3-5-sonnet"
    system=SYSTEM,     # background instructions ("you are a helpful assistant")
    messages=messages, # ALL notes so far — AI needs the full history
    tools=TOOLS,       # list of tools the AI is allowed to use
    max_tokens=8000,   # max length of the AI's reply
)
# client.messages.create() = pressing "send" over the internet to the AI
```

### Step 3: Did the AI call a tool, or just answer?

```python
messages.append({"role": "assistant", "content": response.content})
# Add the AI's reply to our stack of notes

if response.stop_reason != "tool_use":
    return  # AI just gave a text answer — we're done!
#
# stop_reason = what the AI says when it finishes replying
#   "tool_use"  → "I want to run a command"
#   anything else → "I'm done talking"
#
# != means "is not equal to"
```

### Step 4: Run the command, send the result back

```python
results = []
for block in response.content:          # look through the AI's reply
    if block.type == "tool_use":         # did it ask to run a command?
        output = run_bash(block.input["command"])  # run it on our computer!
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,     # ID to match this result with the request
            "content": output,           # what the command printed out
        })
messages.append({"role": "user", "content": results})
# Send results back as if "we" replied — then loop back to Step 2
```

---

## The Full Agent (Under 30 Lines!)

```python
def agent_loop(query):
    messages = [{"role": "user", "content": query}]  # start with your question
    while True:                                        # keep looping...
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":         # ...until AI is done
            return

        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = run_bash(block.input["command"])
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
        messages.append({"role": "user", "content": results})
```

That's it. That's the whole agent. Everything in the next 11 sessions builds on top of this — without changing this loop.

---

## What's New Here

| Piece | Before | After |
|-------|--------|-------|
| Loop | Nothing | `while True` — stops when AI is done |
| Tool | Nothing | `bash` (run terminal commands) |
| Memory | Nothing | A growing list of all messages |
| Stop condition | Nothing | `stop_reason != "tool_use"` |

---

## Try It

```sh
cd learn-claude-code
python agents/s01_agent_loop.py
```

1. `Create a file called hello.py that prints "Hello, World!"`
2. `List all Python files in this directory`
3. `What is the current git branch?`
4. `Create a directory called test_output and write 3 files in it`

---

## Running with Ollama (Local Models)

You can run the same agent loop using a **local model** through [Ollama](https://ollama.com) — no API key, no internet, everything runs on your machine.

### What changes?

The loop logic is identical. The only difference is the **library and message format**.

| | Anthropic version | Ollama version |
|---|---|---|
| Library | `anthropic` | `openai` (Ollama speaks OpenAI's language) |
| Tool format | `input_schema` | `function.parameters` |
| Tool result | `"tool_result"` block | `"tool"` role message |
| Stop signal | `stop_reason == "tool_use"` | `finish_reason == "tool_calls"` |
| System prompt | separate `system=` param | first item in `messages` list |

### The Ollama agent loop

```python
def agent_loop(messages: list):
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,       # same tool, different format
            tool_choice="auto",
        )
        msg = response.choices[0].message
        messages.append(msg.model_dump())

        if response.choices[0].finish_reason != "tool_calls":
            return  # AI is done — no more commands

        for tool_call in msg.tool_calls:
            args = json.loads(tool_call.function.arguments)
            output = run_bash(args["command"])
            messages.append({
                "role": "tool",           # <-- "tool" instead of "user"
                "tool_call_id": tool_call.id,
                "content": output,
            })
```

The loop still looks the same. AI calls a tool → we run it → send the result back → repeat.

### Setup

```sh
# 1. Install Ollama  →  https://ollama.com
# 2. Pull a model that supports tool calling
ollama pull glm-4.7:cloud

# 3. Install the OpenAI Python library
pip install openai

# 4. Run
python agents/s01_agent_loop_ollama.py
```

Your `.env` controls which model and endpoint to use:

```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
OLLAMA_API_KEY=ollama   # Ollama ignores this, but the library requires it
```
