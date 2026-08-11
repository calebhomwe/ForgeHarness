# When to upgrade each module (triggers, not vibes)

| Today | Upgrade | Trigger |
|---|---|---|
| SQLite (db.py) | Postgres | >1 machine writing, or you want dashboards/Grafana |
| Keyword experience lookup | Qdrant hybrid RAG | >500 experience rows, misses on paraphrased errors |
| Direct OpenRouter | LiteLLM proxy | want caching, per-key limits, provider fallback → run proxy, set llm_base_url: http://localhost:4000/v1 (config-only change) |
| supervisor.run() loop | LangGraph | branching multi-agent plans (research→architect→code→review) instead of linear task execution |
| Crash-resume via rows | Temporal | multi-day tasks, distributed workers, human approvals with SLAs/timers |
| runs/ folders | HF datasets | you start LoRA training on trajectories (schema in doc-46 §8 maps 1:1 to our attempts+evaluations tables) |
| vault/ markdown | Obsidian + ingestion pipeline | you begin licensed doc ingestion at scale (doc-46 §7) |

Rule: upgrade a module ONLY when its trigger fires. Each is isolated behind one file.
