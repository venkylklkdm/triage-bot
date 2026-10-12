# TriageBot

A support ticket triage agent. Reads a ticket, hands the meaningful decision
to **Strands Decider 2B** (~115ms, local), and uses **Amazon Bedrock** only
for the generative part: drafting the customer reply.

Decision pattern: **#policy** (classify the request before acting),
plus urgency scoring and a safety yes/no. Tags: `#strands-decider-2b #policy`.

## How it works

```
ticket text
    |
    v
Decider 2B  -- choice: which team? (billing / technical / account)
            -- score:  urgency 1 to 5
            -- yes/no: safe for an automated reply?
    |
    v
confidence >= 0.60 and safe  -->  auto-route + Bedrock drafts the reply
otherwise                  -->  escalate to a human (never guess)
```

## Run it

```bash
pip install strands-decider          # for the real decision model

# Terminal 1: serve the model locally
strands-decider serve StrandsAgents/strands-decider-2B-hobson-v19 --port 8000

# Terminal 2: triage tickets with the real model
python triage_bot.py --demo --decider-url http://127.0.0.1:8000

# No model? The transparent fallback still works for testing:
python triage_bot.py --demo
python triage_bot.py --ticket "My invoice shows double the amount"
```

## Files

- `triage_bot.py` - the agent (DeciderClient, triage pipeline, Bedrock drafts)
- `DECISION_PATTERN.md` - the reusable decision recipe: typed questions,
  serve wiring, and the confidence rule. Drop it into your own agent.
- `builder-center-article.md` - the Builder Center writeup.

## AWS design

Lambda (triggered on new ticket) -> Decider 2B (classification, local) ->
Bedrock Converse API (reply draft) -> route to team queue or escalate.
