"""
TriageBot - a support ticket triage agent.

Pipeline:
  ticket text
      |
      v
  Strands Decider 2B  (fast, local, ~115ms)
      - CHOICE: which team owns this ticket?  (policy pattern)
      - SCORE:  how urgent is it, 1 to 5?
      - NOUL:   is anything in the ticket abusive or unsafe to auto-reply?
      |
      v
  Router: confidence >= threshold -> auto-route + draft reply
          confidence <  threshold -> escalate to a human
      |
      v
  Amazon Bedrock (generative part): drafts the customer reply for the
  auto-routed tickets. Falls back to a template when Bedrock is unavailable.

Usage:
    python triage_bot.py --demo
    python triage_bot.py --ticket "My invoice shows double the amount..."
    python triage_bot.py --demo --decider-url http://127.0.0.1:8000
    python triage_bot.py --serve-check   # verify a local strands-decider server

Real Decider 2B path: run `strands-decider serve <model> --port 8000`
locally, then pass --decider-url. Without it, a transparent local fallback
classifies with keyword rules so the agent is testable anywhere.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import sys
import urllib.request

TEAMS = {
    "billing": "questions about charges, invoices, refunds, payments",
    "technical": "bugs, errors, crashes, features not working",
    "account": "login, password, access, profile, subscription changes",
    "unknown": "does not clearly fit any team",
}

CONFIDENCE_THRESHOLD = 0.60


@dataclasses.dataclass
class Decision:
    team: str
    team_confidence: float
    urgency: int          # 1..5
    urgency_confidence: float
    safe_to_autoreply: bool
    latency_ms: float
    backend: str


# ------------------------------------------------------------------ Decider

class DeciderClient:
    """Wraps Strands Decider 2B, however it is hosted.

    Backend "serve": POSTs to a `strands-decider serve` endpoint
    (/v1/systemone). This is the real Decider 2B path.
    Backend "fallback": transparent keyword rules, used when no model
    is reachable. Always reports which backend made the decision.
    """

    def __init__(self, url: str | None = None):
        self.url = url.rstrip("/") if url else None

    # -- real model -------------------------------------------------
    def _ask_serve(self, state: str) -> dict | None:
        if not self.url:
            return None
        payload = {
            "state": state,
            "questions": {
                "team": {
                    "type": "choice",
                    "instructions": "Which team should handle this support ticket?",
                    "criteria": {k: v for k, v in TEAMS.items() if k != "unknown"},
                },
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
            },
        }
        try:
            req = urllib.request.Request(
                self.url + "/v1/systemone",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read().decode())["answers"]
        except Exception:
            return None

    # -- transparent fallback ---------------------------------------
    _KEYWORDS = {
        "billing": ["invoice", "charge", "charged", "refund", "payment", "billing",
                    "subscription", "price", "overcharged", "receipt"],
        "technical": ["error", "bug", "crash", "broken", "not working", "fails",
                      "failed", "timeout", "500", "exception", "stuck"],
        "account": ["login", "password", "sign in", "locked", "access",
                    "2fa", "account", "profile", "reset"],
    }
    _URGENT = ["urgent", "asap", "immediately", "critical", "down", "blocked",
               "losing money", "can't work", "cannot work", "outage"]
    _UNSAFE = ["idiot", "stupid", "kill you", "sue you", "incompetent"]

    def _ask_fallback(self, state: str) -> dict:
        low = state.lower()
        scores = {t: sum(1 for k in ks if k in low)
                  for t, ks in self._KEYWORDS.items()}
        best = max(scores, key=scores.get)
        team = best if scores[best] else "unknown"
        total = sum(scores.values()) or 1
        team_conf = round(scores[best] / total, 2) if scores[best] else 0.0
        urgency = 5 if any(k in low for k in self._URGENT) else (
            3 if scores[best] else 2)
        safe = not any(k in low for k in self._UNSAFE)
        return {
            "team": {"choice": team, "confidence": team_conf},
            "urgency": {"score": urgency, "confidence": round(team_conf, 2)},
            "safe": {"noul": safe, "confidence": 0.99 if safe else 0.5},
        }

    # -- public ------------------------------------------------------
    def decide(self, state: str) -> Decision:
        import time
        t0 = time.perf_counter()
        answers = self._ask_serve(state)
        backend = "decider-2b"
        if answers is None:
            answers = self._ask_fallback(state)
            backend = "fallback"
        ms = (time.perf_counter() - t0) * 1000

        team = answers["team"].get("choice", "unknown")
        team_conf = float(answers["team"].get("confidence", 0.0))
        urgency = int(answers["urgency"].get("score", 2))
        urgency_conf = float(answers["urgency"].get("confidence", 0.0))
        safe = bool(answers["safe"].get("noul", True))
        return Decision(team, team_conf, urgency, urgency_conf, safe, ms, backend)


# ------------------------------------------------------------------ Bedrock

def bedrock_draft(ticket: str, team: str, urgency: int) -> str | None:
    """Ask Amazon Bedrock to draft the customer reply. None if unavailable."""
    try:
        import boto3  # type: ignore
        client = boto3.client("bedrock-runtime", region_name="us-east-1")
    except Exception:
        return None
    prompt = (
        f"Draft a short, warm customer-support reply to this ticket. "
        f"It was routed to the {team} team with urgency {urgency}/5. "
        f"Do not promise refunds or timelines. Ticket:\n\n{ticket}"
    )
    try:
        resp = client.converse(
            modelId="anthropic.claude-3-5-sonnet-20241022-v2:0",
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 300},
        )
        return resp["output"]["message"]["content"][0]["text"]
    except Exception:
        return None


def template_draft(team: str, urgency: int) -> str:
    return (f"Thanks for reaching out. Your ticket is with our {team} team "
            f"(urgency {urgency}/5) and we will get back to you shortly.")


# ------------------------------------------------------------------ Agent

def triage(ticket: str, decider: DeciderClient) -> dict:
    decision = decider.decide(ticket)
    auto = (decision.team_confidence >= CONFIDENCE_THRESHOLD
            and decision.safe_to_autoreply
            and decision.team != "unknown")
    draft = None
    if auto:
        draft = bedrock_draft(ticket, decision.team, decision.urgency) \
            or template_draft(decision.team, decision.urgency)
    return {
        "ticket": ticket,
        "team": decision.team,
        "team_confidence": decision.team_confidence,
        "urgency": decision.urgency,
        "urgency_confidence": decision.urgency_confidence,
        "auto_routed": auto,
        "escalated_to_human": not auto,
        "reason": ("confidence below threshold or unsafe content"
                   if not auto else "auto-routed"),
        "draft_reply": draft,
        "decision_latency_ms": round(decision.latency_ms, 1),
        "decision_backend": decision.backend,
        "checked_at": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
    }


DEMO_TICKETS = [
    "Hi, my invoice this month shows double the amount I was quoted. "
    "Please refund the extra charge ASAP, this is urgent.",

    "The export button throws a 500 error every time I click it. "
    "Nothing downloads. This started after yesterday's update.",

    "I cannot log in anymore. The password reset link never arrives "
    "in my inbox. I need access today for a client demo.",

    "Just wanted to say the new dashboard looks nice. Keep it up!",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--ticket", default="")
    ap.add_argument("--decider-url", default="",
                    help="strands-decider serve endpoint, e.g. http://127.0.0.1:8000")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    decider = DeciderClient(args.decider_url or None)
    tickets = DEMO_TICKETS if (args.demo or not args.ticket) else [args.ticket]

    results = [triage(t, decider) for t in tickets]
    if args.json:
        print(json.dumps(results, indent=2))
        return
    for r in results:
        print("=" * 60)
        print("TICKET:", r["ticket"][:80])
        print(f"TEAM: {r['team']} (confidence {r['team_confidence']})")
        print(f"URGENCY: {r['urgency']}/5 "
              f"(confidence {r['urgency_confidence']})")
        print("DECISION:",
              "AUTO-ROUTED" if r["auto_routed"] else "ESCALATED TO HUMAN",
              f"| {r['reason']}")
        print(f"decided in {r['decision_latency_ms']}ms via {r['decision_backend']}")
        if r["draft_reply"]:
            print("DRAFT REPLY:", r["draft_reply"][:200])


if __name__ == "__main__":
    main()
