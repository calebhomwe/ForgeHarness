# Architecture decisions (and why)

**Why not LangGraph on day one?** The supervisor is ~200 lines over SQLite. Every state
transition is a committed row → durable + resumable, which is 80% of what you'd buy from
a framework, with zero dependency risk. Swap-in point: `supervisor.run()` is the only
caller of `run_task_once()`; a LangGraph graph can call the same function per node.

**Why not Temporal on day one?** Same durability property, no server to babysit. When you
need multi-machine workers or week-long human approvals with timers, see SCALING.md.

**Why SQLite over Postgres?** Solo dev, one machine, zero setup, transactional. db.py is
the entire storage API — reimplement it and nothing else changes.

**Why the agent never self-reports success:** evaluators run OUTSIDE the worker process
against contracts. This is the single highest-leverage anti-hallucination mechanism.

**Why only VERIFIED fixes enter prompts:** unverified "fixes" from failed attempts are
noise; promotion-on-green means memory quality only goes up.

**Why model escalation per retry:** cheap first, pay for Opus-class only when the cheap
tier has demonstrably failed — doc-46's ladder, automated.

**Failure→asset pipeline:** every failure stores an experience row; every green task
verifies its rows; `harness fix` seeds curated ones. Over months this becomes the moat:
a project-specific error→fix corpus no competitor can copy.
