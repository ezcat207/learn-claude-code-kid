# s05: Skill Loading — Teaching the Agent New Tricks On Demand

`s01 > s02 > s03 > s04 > [ s05 ] s06 | s07 > s08 > s09 > s10 > s11 > s12`

> **Don't put everything in the system prompt. Load knowledge only when needed.**

---

## The Problem: The System Prompt Gets Bloated

The system prompt is the background instruction you give the AI at the start — things like "you are a coding agent" and special rules. It's always in the context window, every single turn.

As you add more capabilities, you might be tempted to put everything there:

```
You are a coding agent.
Here's how to work with PDFs: [2000 words of instructions]
Here's how to do code reviews: [1500 words of instructions]
Here's how to write tests: [1000 words of instructions]
...
```

**Problem:** that's thousands of tokens wasted on every single turn, even when the AI is just running `ls`. And you're still limited — you can only fit so much before the system prompt itself is too big.

**Better idea:** only load the knowledge you actually need, right when you need it.

---

## The Solution: A Two-Layer Library

Think of it like a library card catalog:

- **Layer 1 (the catalog):** a short list of skill names and one-line descriptions in the system prompt — always there, costs almost nothing
- **Layer 2 (the books):** the full skill instructions, loaded into the conversation only when the AI asks for them

```
System prompt (Layer 1 — ~100 tokens per skill):
  Skills available:
    - pdf: Process and extract text from PDF files
    - code-review: Perform structured code review

When AI calls load_skill("pdf") (Layer 2 — loaded on demand):
  <skill name="pdf">
    Step 1: Install pdfplumber...
    Step 2: Extract text with...
    [full instructions, only when needed]
  </skill>
```

---

## How It Works — Step by Step

### Step 1: Skills live in files with YAML frontmatter

```
skills/
  pdf/
    SKILL.md      ← frontmatter + body
  code-review/
    SKILL.md
```

```yaml
---
name: pdf
description: Process and extract text from PDF files
tags: files, parsing
---
# How to work with PDFs

Step 1: Install pdfplumber with `pip install pdfplumber`
...
```

The `---` block at the top is YAML frontmatter — structured metadata. The rest is the skill body.

### Step 2: SkillLoader reads all skills at startup

```python
class SkillLoader:
    def _load_all(self):
        for f in self.skills_dir.rglob("SKILL.md"):  # find all skill files
            meta, body = self._parse_frontmatter(f.read_text())
            name = meta.get("name", f.parent.name)
            self.skills[name] = {"meta": meta, "body": body}
```

### Step 3: Layer 1 injected into system prompt (metadata only)

```python
def get_descriptions(self) -> str:
    return "\n".join(f"  - {name}: {skill['meta']['description']}"
                     for name, skill in self.skills.items())

SYSTEM = f"""You are a coding agent at {WORKDIR}.
Skills available:
{SKILL_LOADER.get_descriptions()}"""
# e.g. "  - pdf: Process and extract text from PDF files"
# Short! Only name + description. No body.
```

### Step 4: Layer 2 returned in tool_result (full body on demand)

```python
def get_content(self, name: str) -> str:
    skill = self.skills.get(name)
    return f"<skill name=\"{name}\">\n{skill['body']}\n</skill>"

TOOL_HANDLERS = {
    # ...
    "load_skill": lambda **kw: SKILL_LOADER.get_content(kw["name"]),
}
```

The AI sees the full instructions appear in the conversation — right when it needs them, not before.

---

## What the AI's Flow Looks Like

```
You: "Extract text from report.pdf"

AI: (calls load_skill "pdf")
  ← <skill name="pdf">
       Step 1: pip install pdfplumber
       Step 2: import pdfplumber; with pdfplumber.open("file.pdf") as pdf...
     </skill>

AI: (calls bash: pip install pdfplumber)
AI: (calls write_file: extract.py with the extraction code)
AI: (calls bash: python extract.py report.pdf)
AI: "Done! Text extracted to output.txt"
```

The skill instructions only appeared in the conversation during the one task that needed them. Other tasks don't pay for that context.

---

## What Changed From s04

| Piece | Before (s04) | After (s05) |
|-------|-------------|-------------|
| Knowledge | Hardcoded in system prompt | Files in `skills/` directory |
| System prompt | Fixed | + skill catalog (Layer 1) |
| New tool | N/A | `load_skill` (Layer 2 trigger) |
| Adding capability | Edit the code | Drop a new `SKILL.md` file |

---

## Try It

```sh
cd learn-claude-code
python agents/s05_skill_loading.py
```

1. `What skills do you have available?`
2. `Do a code review of agents/s01_agent_loop.py`
3. Add a new file `skills/my-skill/SKILL.md` with a frontmatter block and some instructions, then ask the agent to use it

---

## Running with Ollama (Local Models)

The `SkillLoader` class and two-layer injection pattern are **completely unchanged**. The only differences are the standard OpenAI format ones from s02.

### Nothing new to explain

The skill loading mechanism has no special Anthropic-specific logic. The `load_skill` tool returns a string (the skill body), and that string becomes a `"tool"` role message — same as any other tool result.

```python
# Anthropic format
results.append({"type": "tool_result", "tool_use_id": block.id,
                "content": SKILL_LOADER.get_content(name)})

# Ollama format
messages.append({"role": "tool", "tool_call_id": tool_call.id,
                 "content": SKILL_LOADER.get_content(name)})
```

Same skill content. Different envelope.

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s05_skill_loading_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
