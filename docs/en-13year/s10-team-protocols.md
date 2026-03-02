# s10: Team Protocols — Shutdown and Plan Approval

`s01 > s02 > s03 > s04 > s05 > s06 > s07 > s08 > s09 > [ s10 ] s11 > s12`

> **Two protocols built on the same request/response pattern: shutdown and plan approval.**

---

## The Problem: Teammates Need Coordination Signals

In s09 we had teammates that could send messages and stay alive. But there was no structured way to:
- Ask a teammate to stop (and confirm they actually stopped)
- Have a teammate ask "is my plan okay?" before doing risky work

Without these, the team lead has no control and teammates have no safety valve.

---

## The Solution: Request/Response with Correlation IDs

Both protocols follow the same pattern:

```
lead sends request  →  teammate receives it  →  teammate sends response
     with request_id                                  with same request_id
```

The `request_id` lets the lead match responses to their original requests even when multiple teammates are active.

---

## How It Works — Step by Step

### Shutdown FSM

```
lead calls shutdown_request("alice")
  → generates request_id = "a1b2c3d4"
  → writes shutdown_request message to alice's inbox
  → stores {target: "alice", status: "pending"} in shutdown_requests dict

alice's loop reads inbox
  → sees shutdown_request with request_id
  → calls shutdown_response(request_id, approve=True)
  → updates shutdown_requests[request_id]["status"] = "approved"
  → sends shutdown_response message to lead's inbox
  → exits its loop

lead calls shutdown_response(request_id) to check status
  → returns current status from shutdown_requests dict
```

```python
# Lead side
def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    BUS.send("lead", teammate, "Please shut down gracefully.",
             "shutdown_request", {"request_id": req_id})
    return f"Shutdown request {req_id} sent to '{teammate}'"
```

### Plan Approval FSM

```
teammate calls plan_approval("Here is my plan: ...")
  → generates request_id = "e5f6a7b8"
  → stores {from: teammate, plan: ..., status: "pending"} in plan_requests dict
  → sends plan_approval_response message to lead's inbox

lead reads inbox, sees plan
  → calls plan_approval(request_id, approve=True, feedback="Looks good")
  → sends plan_approval_response back to teammate's inbox

teammate reads inbox
  → sees approval → continues with plan
  → sees rejection → revises plan
```

### Five Message Types

```python
VALID_MSG_TYPES = {
    "message",               # plain text
    "broadcast",             # to all teammates
    "shutdown_request",      # lead → teammate: please stop
    "shutdown_response",     # teammate → lead: stopped (or rejected)
    "plan_approval_response" # both directions: submit plan / approve plan
}
```

---

## What Changed From s09

| Piece | Before (s09) | After (s10) |
|-------|-------------|-------------|
| Shutdown | None | request/response with FSM |
| Plan approval | None | request/response with FSM |
| New tools | None | `shutdown_request`, `shutdown_response`, `plan_approval` |
| Teammate tools | send/read only | + `shutdown_response`, `plan_approval` |

---

## Try It

```sh
cd learn-claude-code
python agents/s10_team_protocols.py
```

1. `Spawn a teammate named alice with role "coder" and ask her to list Python files`
2. `Send a shutdown request to alice and check the status`
3. `Spawn a teammate bob and ask him to submit a plan for a risky file change`

---

## Running with Ollama (Local Models)

The `MessageBus`, `TeammateManager`, request tracker dicts, and all protocol logic are **completely unchanged**. The only differences are the standard OpenAI format conversions.

### The key change: detecting tool calls by name

In the Anthropic version, the teammate loop checks `block.name` to identify tool calls. In the OpenAI version, it checks `tool_call.function.name`:

```python
# Anthropic version (s10)
for block in response.content:
    if block.type == "tool_use":
        if block.name == "shutdown_response":
            should_exit = args.get("approve", False)

# Ollama version (s10_ollama)
for tool_call in msg_obj.tool_calls:
    args = json.loads(tool_call.function.arguments)
    if tool_call.function.name == "shutdown_response":
        should_exit = args.get("approve", False)
```

The shutdown/plan approval logic, request tracking dicts, and inbox messaging are all identical.

### Setup

```sh
ollama pull glm-4.7:cloud
python agents/s10_team_protocols_ollama.py
```

`.env` config:
```sh
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL_ID=glm-4.7:cloud
```
