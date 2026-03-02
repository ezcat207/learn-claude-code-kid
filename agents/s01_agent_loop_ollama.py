#!/usr/bin/env python3
"""
s01_agent_loop_ollama.py - The Agent Loop (Ollama version)

Same pattern as s01_agent_loop.py but uses Ollama via its
OpenAI-compatible API instead of Anthropic.

    while stop_reason == "tool_calls":
        response = LLM(messages, tools)
        execute tools
        append results

    +----------+      +--------+      +---------+
    |   User   | ---> | Ollama | ---> |  Tool   |
    |  prompt  |      |        |      | execute |
    +----------+      +---+----+      +----+----+
                          ^               |
                          |   tool_result |
                          +---------------+
                          (loop continues)

Requirements:
    pip install openai python-dotenv
    ollama pull qwen2.5-coder:7b   # or any tool-capable model
"""

import json
import os
import subprocess

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

client = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.getenv("OLLAMA_API_KEY", "ollama"),  # Ollama ignores the key
)
MODEL = os.getenv("OLLAMA_MODEL_ID", "qwen2.5-coder:7b")

SYSTEM = f"You are a coding agent at {os.getcwd()}. Use bash to solve tasks. Act, don't explain."

# OpenAI tool format (different from Anthropic's)
TOOLS = [{
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
}]


def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=os.getcwd(),
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


# -- The core pattern: same while loop, OpenAI message format --
def agent_loop(messages: list):
    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # Append assistant turn (convert to dict for mutability)
        messages.append(msg.model_dump(exclude_unset=False))

        # If no tool calls, we're done
        if response.choices[0].finish_reason != "tool_calls" or not msg.tool_calls:
            return

        # Execute each tool call, collect results
        for tool_call in msg.tool_calls:
            args = json.loads(tool_call.function.arguments)
            print(f"\033[33m$ {args['command']}\033[0m")
            output = run_bash(args["command"])
            print(output[:200])
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": output,
            })


if __name__ == "__main__":
    print(f"\033[90mUsing model: {MODEL} via {client.base_url}\033[0m\n")
    history = [{"role": "system", "content": SYSTEM}]
    while True:
        try:
            query = input("\033[36ms01-ollama >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        last = history[-1]
        content = last.get("content") or ""
        if content:
            print(content)
        print()
