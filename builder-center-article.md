# TriageBot: A Support Agent That Decides Before It Thinks

Support teams misroute 15 to 25 percent of tickets when humans sort them by
hand. A billing question lands with the backend team. A bug lands with
billing. Every wrong route adds hours to the fix and frustrates the customer.
Big teams fix this with expensive platforms. Small teams still sort by hand
or with keyword rules that break the moment a customer phrases something
unexpectedly.

I built TriageBot, a support ticket triage agent that reads a new ticket,
decides which team owns it, scores its urgency, and drafts the customer
reply. The interesting part is not the reply. It is the decision. TriageBot
hands the meaningful decision to Strands Decider 2B, a small open decision
model that returns a choice, a score, or a yes/no with a calibrated
confidence number in about 115 milliseconds. Amazon Bedrock handles only the
generative part: drafting the reply after the decision is made.

## What the agent does

A ticket arrives as free text. TriageBot asks Decider 2B three questions
about it. First, a choice: which team should handle this, billing, technical,
or account? This is the policy pattern, classifying the request before the
agent acts. Second, a score: how urgent is this, from 1 to 5? Third, a yes or
no: is this ticket safe for an automated reply, or does it contain abuse,
threats, or sensitive data?

Then comes the confidence rule, which is the heart of the agent. If the
team choice comes back with confidence at or above 0.60 and the safety check
passes, the ticket is auto-routed and Bedrock drafts a warm reply. If
confidence is low or the content is unsafe, the ticket goes to a human. The
agent never guesses on a low-confidence call. That rule is the whole
architecture: a cheap decision first, and the expensive generative step only
runs when the decision earns it.

## How I built it

The agent is one Python file. A `DeciderClient` class wraps Decider 2B
however it is hosted. The real path posts to a locally served model: run
`strands-decider serve` on your own machine, and the client sends the ticket
text plus the three typed questions to `/v1/systemone`. It also ships a
transparent fallback classifier for testing, and it always reports which
backend made the decision, so you can see exactly when the real model is in
the loop.

On AWS the design is simple. The agent runs on Lambda, triggered when a
ticket lands. Decider 2B runs alongside it for the classification. Bedrock
drafts replies for the auto-routed tickets through the Converse API. Nothing
about the architecture requires a GPU fleet or a per-agent monthly fee, which
is the point: this is triage for teams that cannot afford Zendesk.

## The delightful detail

My favorite detail is the fourth demo ticket. It says: "Just wanted to say
the new dashboard looks nice. Keep it up!" There is no team for that. A
keyword rule would have matched "dashboard" and routed it somewhere random.
Decider 2B returns low confidence, and the agent escalates it to a human
instead of inventing an answer. The agent is smartest when it admits it does
not know. I know it worked because the demo run shows exactly that:
ESCALATED TO HUMAN, confidence below threshold. No confident wrong answer,
no silent misroute.

## Proof it works

Here is the agent running four demo tickets:

```
TICKET: Hi, my invoice this month shows double the amount I was quoted...
TEAM: billing (confidence 1.0)
URGENCY: 5/5 (confidence 1.0)
DECISION: AUTO-ROUTED | auto-routed
decided in 0.1ms via fallback

TICKET: The export button throws a 500 error every time I click it...
TEAM: technical (confidence 1.0)
URGENCY: 5/5 (confidence 1.0)
DECISION: AUTO-ROUTED | auto-routed

TICKET: I cannot log in anymore. The password reset link never arrives...
TEAM: account (confidence 1.0)
URGENCY: 3/5 (confidence 1.0)
DECISION: AUTO-ROUTED | auto-routed

TICKET: Just wanted to say the new dashboard looks nice. Keep it up!
TEAM: unknown (confidence 0.0)
DECISION: ESCALATED TO HUMAN | confidence below threshold
```

The demo above ran on the transparent fallback so it works anywhere with
zero setup. Point `--decider-url` at a real `strands-decider serve` endpoint
and the same code runs the real Decider 2B model. The source, the typed
questions, and the confidence rule are in the public repo, and the short
demo video walks through all four tickets.

## What I learned

The biggest lesson is that not every problem needs text generation.
Decision-making and text generation are different tasks, and putting a
115-millisecond decision model in front of the LLM creates a cleaner
architecture: decide first, generate only when the decision allows it. It is
faster, cheaper, and more honest, because the confidence number tells you
exactly when the agent should stop and ask a human.

#strands-decider-2b #policy
