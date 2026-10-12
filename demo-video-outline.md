# Demo video outline (under 3 minutes)

Film your screen running the agent. Read the lines in your own words.

## 0:00 - 0:20  The problem
"Support teams misroute up to 25 percent of tickets by hand. A billing
question goes to the backend team, a bug goes to billing. I built TriageBot,
an agent that reads a ticket and decides who owns it before any expensive
AI call happens."

## 0:20 - 1:10  The decision (show the code)
Open DECISION_PATTERN.md. Show the three typed questions.
"The meaningful decision goes to Strands Decider 2B, a tiny model that
returns a choice, a score, or a yes-no with a confidence number in about
115 milliseconds. Choice: which team. Score: urgency 1 to 5. Yes or no:
safe for an automated reply."

## 1:10 - 2:10  The agent running (show the terminal)
Run: python triage_bot.py --demo
Point at the output as it prints.
"Billing ticket, confidence high, auto-routed, Bedrock drafted the reply.
Technical ticket, auto-routed. Account ticket, auto-routed. And this last
one, just a compliment about the dashboard, comes back low confidence, so
the agent escalates to a human instead of guessing. That is the whole
trick: a cheap decision first, and the expensive step only runs when the
decision earns it."

## 2:10 - 2:45  The wiring
"On AWS this runs on Lambda when a ticket lands. Decider 2B classifies it
locally in milliseconds. Bedrock drafts replies for the auto-routed ones.
The repo has the typed questions and the confidence rule as a reusable
pattern anyone can drop into their own agent."

## 2:45 - 3:00  Close
"Decide first, generate second. Faster, cheaper, and honest about when
to ask a human."

Keep it under 3 minutes. One take is fine. Phone recording of the screen works.
