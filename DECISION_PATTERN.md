# Reusable Decision Pattern: Fast Policy Classification for Support Tickets

Tags: #strands-decider-2b #policy

## What this pattern does

Classifies an incoming support ticket into an owning team and scores its
urgency, in about 115 milliseconds, before any expensive LLM call happens.
The confidence score tells the agent when to act on its own and when to ask
a human. Drop this into any agent that receives free-text requests.

## The typed questions (copy these)

Ask Strands Decider 2B three questions about the ticket text (`state`):

```python
QUESTIONS = {
    # CHOICE: policy pattern. Which team owns this ticket?
    "team": {
        "type": "choice",
        "instructions": "Which team should handle this support ticket?",
        "criteria": {
            "billing": "questions about charges, invoices, refunds, payments",
            "technical": "bugs, errors, crashes, features not working",
            "account": "login, password, access, profile, subscription changes",
        },
    },
    # SCORE: how urgent is it, 1 to 5?
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this support ticket?",
        "criteria": [
            "not urgent, can wait days",
            "low urgency, answer this week",
            "normal urgency, answer within a day",
            "high urgency, customer is blocked",
            "critical, money or data at risk right now",
        ],
    },
    # YES/NO: is it safe for an automated reply?
    "safe": {
        "type": "noul",
        "instructions": (
            "Is this ticket safe for an automated reply "
            "(no abuse, threats, or sensitive data)?"
        ),
        "criteria": {
            "true": "safe, polite ticket with no sensitive data",
            "false": "abusive, threatening, or contains sensitive data",
        },
    },
}
```

## The wiring: serve it, then ask it

```bash
# 1. Serve the model locally
pip install strands-decider
strands-decider serve StrandsAgents/strands-decider-2B-hobson-v19 --port 8000
```

```python
# 2. Ask it over HTTP (see triage_bot.py DeciderClient for the full client)
import json, urllib.request

def decide(state: str, url: str = "http://127.0.0.1:8000") -> dict:
    payload = {"state": state, "questions": QUESTIONS}
    req = urllib.request.Request(
        url + "/v1/systemone",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())["answers"]
```

Or use the CLI directly:

```bash
strands-decider ask StrandsAgents/strands-decider-2B-hobson-v19 \
  --state "My invoice shows double the amount" \
  --choice "Which team should handle this?=billing,technical,account"
```

## The confidence rule (the actual pattern)

```python
CONFIDENCE_THRESHOLD = 0.60

answers = decide(ticket_text)
team = answers["team"]["choice"]
conf = answers["team"]["confidence"]

if conf >= CONFIDENCE_THRESHOLD and answers["safe"]["noul"]:
    route_to_team(team)          # act on it
    draft_reply_with_llm(...)    # Bedrock does the generative part
else:
    escalate_to_human(ticket)    # low confidence or unsafe: never guess
```

That rule is the whole trick. A cheap decision model answers first, and its
calibrated confidence decides whether the expensive generative step is even
allowed to run. Measure the win: one Decider 2B call costs ~115ms and no
tokens, versus a full LLM classification round trip.

## How to use it in your agent

1. Serve Decider 2B next to your agent (same machine is fine).
2. Copy `QUESTIONS` and `decide()` above, or use `DeciderClient` from
   `triage_bot.py`, which also includes a transparent fallback for testing.
3. Put `decide()` at the top of your ticket pipeline, before any LLM call.
4. Tune the team labels in `criteria` to your own taxonomy; the pattern does
   not change.
5. Log `choice`, `confidence`, and the threshold outcome on every ticket so
   you can see when the model is unsure and retune the threshold.

## Wiring it as a Strands InterventionHandler

To make the check run automatically inside a Strands agent, put the decision
in `before_tool_call`: read the proposed tool call, ask the `safe` question,
and return `Proceed`, `Deny`, or `Guide` based on the confidence. The
decision stays in the tool path where an LLM call could never afford to sit.
