# Agentic Engineering Guide vs. Agentura: Gap Analysis & 6-Month Roadmap

> **Source:** [The Agentic Engineering Guide](https://agents.siddhantkhare.com/) by Siddhant Khare (33 chapters, 10 parts)
> **Analysis date:** 2026-04-21
> **Scope:** All Agentura agents (CodeLens, ECM, Kairos/GE, Growth, PM, Shipwright) mapped against book's first principles

---

## Part 1: First Principles Alignment

The book defines 6 engineering disciplines. Here's where Agentura stands:

| Discipline | Book's First Principle | Agentura Status | Rating |
|---|---|---|---|
| **Context Engineering** | "Mediocre model + excellent context > frontier model + poor context" | Code graph builder, SKILL.md + DOMAIN.md + WORKSPACE.md injection, reflexion learning loop | **Strong** |
| **Agent Authorization** | Zanzibar/OpenFGA — least privilege, per-tool, per-resource | None. Executor runs with full env-var API keys. No per-agent, per-tool permission scoping | **Critical Gap** |
| **Agent Observability** | OTel traces per decision, cost attribution, session replay | Cost logging to PostgreSQL, Prometheus counters, but no distributed traces, no session replay, no OTel | **Partial** |
| **Agent Orchestration** | Distributed systems thinking — circuit breakers, fallbacks, termination | Pipeline engine with parallel/sequential, agent loop with max iterations, fallback chains via OpenRouter | **Good** |
| **Human-Agent Collaboration** | Conductor Model — engineers specify, agents execute, humans review | Slack bots, approval buttons, but no structured task specs, no human-in-the-loop gates for consequential actions | **Partial** |
| **Security** | Defense in depth — sandbox + authz + injection defense + policy | PTC/Claude Code workers have process isolation, but no seccomp, no Landlock, no output filtering, no prompt injection defense | **Weak** |

---

## Part 2: Agent-by-Agent Mapping

### CodeLens (Codebase Q&A)

**Book category:** Command Agent (L3) using Agentic Search pattern

**What it does right:**
- Code knowledge graph (Ch.6 — codebase knowledge graph pattern)
- Tool-calling loop with `query_code_graph` + `git_codebase` (Ch.17 — agent loop)
- Branch-aware graph building on demand (Ch.5 — fresh context for operations agents)
- Reflexion learning from corrections (Ch.19 — learning from mistakes)

**Gaps vs. book:**
- No context budget management (Ch.4 — token budget framework). Tool definitions sent every turn
- No Meta-MCP pattern (Ch.5 — 88% tool token reduction). Only 2 tools, but no lazy loading
- No eval suite (Ch.26 — golden dataset testing). No way to measure accuracy systematically
- No structured output (Ch.30). Raw text responses, no schema enforcement

### ECM Triage Bot (Order Diagnosis)

**Book category:** Command Agent (L3) with MCP tool integration

**What it does right:**
- Domain-scoped skills (triage, process-stuck-order, pattern-intelligence)
- Watch bot pattern for Forseti SLA breach auto-enrichment (Ch.18 — fleet-scale)
- Command aliases for structured input (`order {id}`, `stuck at {category}`)

**Gaps:**
- No circuit breaker on DB queries (Ch.17 — error recovery)
- No cost attribution per order investigation (Ch.15 — attribution hierarchy)
- Responded to ambient channel messages (fixed Apr 2026 — Ch.10 — deny-by-default)

### Kairos / GE (Trading Intelligence)

**Book category:** Command Agent (L3-L4) with scheduled heartbeats

**What it does right:**
- Heartbeat coordinator with SOUL.md personality (Ch.21 — conductor model)
- Active hours gating (Ch.17 — human-in-the-loop, business hours)
- Budget caps per agent ($30/month, $2/execution) (Ch.28 — token budgets)

**Gaps:**
- No fallback chain if Anthropic API is down (Ch.31 — fallback chains are non-negotiable)
- Heartbeat uses full context every beat, no summarization (Ch.4 — context window management)

### Growth Bot (Analytics)

**Book category:** Command Agent (L3) with domain specialization

**What it does right:**
- Rich command alias system (funnel, churn, pulse, cohort, etc.)
- Role-specific routing within domain
- MCP integration (Metabase, Databricks)

**Gaps:**
- No caching of repeated analytics queries (Ch.28 — caching pillar)
- Same Metabase query run daily costs the same each time

### PM Bot (Product Management)

**Book category:** Chat Agent (L2-L3)

**Gaps:** Similar to Growth — no eval, no cost optimization, no structured output

### Shipwright (PR Review Pipeline)

**Book category:** Multi-Agent Pipeline (L4)

**What it does right:**
- 4 parallel agents (reviewer, test-runner, SLT validator, doc-generator) (Ch.18 — parallel independent execution)
- Dedup on repo+PR with cooldown (Ch.16 — loop detection)
- `.shipwright.yaml` per-repo config (Ch.13 — AGENTS.md pattern)

**Gaps:**
- No distributed tracing across the 4 agents (Ch.18 — "invest in trace propagation before deploying multi-agent")
- No LLM-as-judge for review quality (Ch.26 — behavioral testing)
- No cost tracking per review (Ch.15)

---

## Part 3: Systemic Gaps (Platform-Level)

### 1. Authorization — CRITICAL (Ch.7, 8)

**Current state:** All agents share the same `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY`. MCP servers get env-var tokens. No per-agent, per-tool permission scoping.

**Book says:** "A human developer knows not to run DROP TABLE; an agent doesn't." Use OpenFGA with capability tokens — time-bound, scope-limited, auditable.

**Risk:** Any agent can call any MCP server with full credentials. A prompt injection in CodeLens could theoretically access Databricks via the shared executor.

### 2. Observability — HIGH (Ch.14, 15)

**Current state:** `cost_usd` logged per execution in PostgreSQL. Prometheus counters for Slack events. No distributed traces, no session replay, no anomaly alerting.

**Book says:** OTel traces per session with spans for every LLM call and tool call. Alert on cost >$5/session, duration >10min. Session replay for 1-5% sample.

**Missing:** Can't answer "why did CodeLens give a wrong answer?" without reading raw logs.

### 3. Evaluation — HIGH (Ch.26)

**Current state:** No eval pipeline. No golden datasets. No regression testing on prompt changes.

**Book says:** 50-100 golden examples per agent. Run evals on every prompt/skill change. Track task completion >85%, tool call accuracy >90%, hallucination <5%.

### 4. Sandboxing — MEDIUM (Ch.10)

**Current state:** PTC worker (200MB) and Claude Code worker (800MB) run in K8s pods with resource limits. No seccomp, no Landlock, no output filtering.

**Book says:** Containers provide deployment isolation, not security isolation. Agents are adversarial workloads. Need deny-by-default syscall filtering + output exfiltration scanning.

### 5. Model Routing — MEDIUM (Ch.31)

**Current state:** OpenRouter with `MODEL_ALIASES` and `FALLBACK_CHAINS`. Router uses Haiku. Per-skill model override in SKILL.md frontmatter.

**Book says:** Rule-based routing saves 3-5x. CASTER cascade (start cheap, escalate on failure) gives 40-60% reduction. Agentura has the primitives but doesn't cascade — each skill hardcodes its model.

### 6. Backpressure — MEDIUM (Ch.32)

**Current state:** No automated feedback loop. Agent output goes straight to Slack. No type checking, no test execution, no architecture enforcement on agent responses.

**Book says:** Full backpressure pipeline: static analysis → test execution → security scanning → architecture enforcement → human review. Self-correction rate >80%. Cycle <2 minutes.

---

## Part 4: 6-Month Roadmap

### Month 1-2: Foundation (L3 Solidification)

**Theme: "Measure before you optimize"**

| Week | Deliverable | Book Chapter | Impact |
|---|---|---|---|
| 1-2 | **OTel instrumentation** on executor — trace per session, span per LLM/tool call, cost attributes | Ch.14 | Can finally debug "why did the agent do that?" |
| 3-4 | **Golden dataset per agent** — 30 examples each for CodeLens, ECM, Shipwright | Ch.26 | Baseline accuracy measurement |
| 5-6 | **Cost attribution dashboard** — per agent, per skill, per user, daily/weekly trends | Ch.15, 28 | Know your cost drivers before optimizing |
| 7-8 | **Backpressure v1 for Shipwright** — run affected tests + type check on agent-generated PR suggestions before posting | Ch.32 | Review quality up, human review time down |

**Expected outcomes:** Accuracy baselines for all agents. Cost visibility. 30-40% reduction in human review time for Shipwright.

### Month 3-4: Security & Cost (L3→L4 Bridge)

**Theme: "Earn the right to run unattended"**

| Week | Deliverable | Book Chapter | Impact |
|---|---|---|---|
| 9-10 | **OpenFGA authorization** — per-agent tool permissions. CodeLens gets read-only code graph + git. ECM gets Databricks read + ClickUp write. No agent gets everything. | Ch.8 | Blast radius containment |
| 11-12 | **Model routing cascade** — classify task complexity at router level, start with Haiku, escalate to Sonnet only if confidence <0.7 | Ch.31 | 40-60% cost reduction on simple queries |
| 13-14 | **Output filtering** — scan agent responses for secrets, unexpected URLs, base64 blobs before posting to Slack | Ch.9 | Exfiltration defense |
| 15-16 | **Sandbox hardening** — seccomp profiles for PTC/Claude Code workers, deny-by-default network | Ch.10 | Defense in depth |

**Expected outcomes:** Per-agent permission scoping. 40-60% cost reduction via routing. No more "agent accidentally leaks secrets" risk.

### Month 5-6: Orchestration & Autonomy (L4)

**Theme: "Multi-agent systems that self-correct"**

| Week | Deliverable | Book Chapter | Impact |
|---|---|---|---|
| 17-18 | **A2A protocol for Shipwright** — structured handoff between reviewer, test-runner, SLT validator with trace propagation | Ch.12, 18 | Debuggable multi-agent pipeline |
| 19-20 | **Eval-driven CI** — run golden dataset + regression suite on every SKILL.md change. Block merge if accuracy drops >5% | Ch.26 | No silent regressions |
| 21-22 | **Context engineering v2** — Meta-MCP for tool compression, sliding window for long sessions, selective context loading per skill | Ch.4, 5 | 60-80% token reduction on complex sessions |
| 23-24 | **Background agent prototype** — one agent (e.g., ECM daily triage) runs fully unattended with anomaly detection, kill switch, and outcome-based alerting | Ch.22 (L5) | First L5 agent |

**Expected outcomes:** Distributed tracing across multi-agent workflows. Automated quality gates on skill changes. First background agent running autonomously.

---

## Part 5: Maturity Assessment (Book's Framework)

| Dimension | Current Level | Month 2 Target | Month 6 Target |
|---|---|---|---|
| **Usage** | L3 (team integration) | L3 | L4 |
| **Context** | L3 (SKILL.md, graphs) | L3 | L4 (Meta-MCP, compression) |
| **Security** | L1 (shared keys) | L2 | L3-L4 (OpenFGA, sandbox) |
| **Observability** | L2 (basic logging) | L3 (OTel traces) | L4 (anomaly detection) |
| **Cost** | L2 (per-execution log) | L3 (dashboards, budgets) | L4 (routing, cascade) |
| **Review** | L2 (human only) | L3 (backpressure v1) | L4 (eval-driven CI) |
| **Policies** | L2 (GUARDRAILS.md) | L3 (machine-readable) | L4 (OpenFGA + OPA) |

**Overall: L2 today → L3 by Month 2 → L4 by Month 6**

> The book says: "Measure maturity by the LOWEST dimension." Agentura's lowest is Security (L1). That's the first thing to fix.

---

## Appendix: Book Reference Map

| Book Chapter | Agentura Relevance | Priority |
|---|---|---|
| Ch.1 — Agentic Landscape | Foundational context | — |
| Ch.2 — Capability Jump | Model selection rationale | Low |
| Ch.3 — AAIF Standards | MCP adoption validation | Low |
| Ch.4 — Context Windows | Token budget enforcement | **High** |
| Ch.5 — Context Stack | Meta-MCP, compression | **High** |
| Ch.6 — RAG vs Agentic Search | CodeLens architecture validation | Low |
| Ch.7 — Security Crisis | Threat awareness | **Critical** |
| Ch.8 — Zanzibar/OpenFGA | Authorization implementation | **Critical** |
| Ch.9 — Prompt Injection | Output filtering | **High** |
| Ch.10 — Sandboxing | Worker hardening | **Medium** |
| Ch.11 — MCP | Already adopted | Low |
| Ch.12 — A2A | Shipwright pipeline | Medium |
| Ch.13 — AGENTS.md | SKILL.md already serves this | Low |
| Ch.14 — OTel Traces | Executor instrumentation | **High** |
| Ch.15 — Cost Tracking | Attribution dashboard | **High** |
| Ch.16 — Incident Response | Runbook formalization | Medium |
| Ch.17 — Agent Loop | Already implemented | Low |
| Ch.18 — Multi-Agent | Shipwright trace propagation | Medium |
| Ch.19 — Memory & Checkpoints | Reflexion system validation | Low |
| Ch.20 — AI Fatigue | Team practice | Low |
| Ch.21 — Conductor Model | Heartbeat system validation | Low |
| Ch.22 — Maturity Model | Assessment framework | **High** |
| Ch.23 — First Agent | Already past this stage | Low |
| Ch.24 — Security Checklist | Apply to all agents | **Critical** |
| Ch.25 — Measuring Impact | Dashboard metrics | Medium |
| Ch.26 — Evaluation & Testing | Golden datasets, eval CI | **High** |
| Ch.27 — Enterprise Adoption | Vendor strategy | Low |
| Ch.28 — Cost Control / FinOps | Routing cascade | **High** |
| Ch.29 — Governance | Audit trail formalization | Medium |
| Ch.30 — Structured Outputs | Schema enforcement | Medium |
| Ch.31 — Model Selection & Routing | CASTER cascade | **High** |
| Ch.32 — Backpressure | Shipwright feedback loop | **High** |
| Ch.33 — Adoption Playbook | Already adopted | Low |
