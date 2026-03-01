# HOOK — Inter-Agent Routing Research

**Date:** 2026-02-28
**Author:** PUNCH Cyber / HOOK Build Team
**Status:** Research Complete — Ready to Implement

---

## Executive Summary

OpenClaw provides **three mechanisms** for inter-agent communication. After researching docs, GitHub issues, DeepWiki, community blogs, and real-world implementations, the recommended approach for HOOK is:

**Primary: `sessions_spawn`** — Coordinator spawns specialist agents as subagents
**Future: `sessions_send` via `agentToAgent`** — Direct peer-to-peer messaging (has a known bug, defer)
**Optional: Lobster workflows** — Deterministic multi-step pipelines (overkill for Phase 2)

---

## Mechanism 1: `sessions_spawn` (RECOMMENDED for HOOK)

### How It Works
- The coordinator agent calls `sessions_spawn` with a `task` string and optional `agentId`
- OpenClaw creates an isolated session: `agent:<agentId>:subagent:<uuid>`
- The subagent runs in its own context, executes the task, then **announces the result back** to the requester's chat channel
- Always non-blocking: returns `{ status: "accepted", runId, childSessionKey }` immediately

### Config Required
```jsonc
{
  "agents": {
    "defaults": {
      "subagents": {
        "maxConcurrent": 3,          // max simultaneous subagent runs
        "maxSpawnDepth": 1,          // 1 = flat (no sub-sub-agents), 2 = orchestrator pattern
        "maxChildrenPerAgent": 5,    // safety valve per parent session
        "archiveAfterMinutes": 60,   // auto-cleanup
        "runTimeoutSeconds": 120     // abort long-running tasks
      }
    },
    "list": [
      {
        "id": "coordinator",
        "default": true,
        "subagents": {
          "allowAgents": ["triage-analyst", "osint-researcher", "incident-responder", "threat-intel", "report-writer"]
        }
      },
      { "id": "triage-analyst" },
      { "id": "osint-researcher" },
      { "id": "incident-responder" },
      { "id": "threat-intel" },
      { "id": "report-writer" }
    ]
  }
}
```

### Key Details
- `allowAgents` on the coordinator is what permits cross-agent spawning. Default is self-only.
- Use `agents_list` tool at runtime to discover which agents are available
- Subagents inherit the parent's tools MINUS session tools by default (configurable via `tools.subagents.tools`)
- Each subagent gets its own context window — parent context is NOT copied
- Subagent model can be overridden: `agents.defaults.subagents.model` or per-spawn `model` param
- After completion, OpenClaw runs an "announce" step that posts results back to the requester channel
- Reply `ANNOUNCE_SKIP` during announce to stay silent

### Tools Available to Subagents
By default, subagents get ALL tools except:
- `sessions_spawn` (no sub-sub-spawning at depth 1)
- `sessions_list`, `sessions_history`, `sessions_send`
- System tools (`gateway`, `cron`)

This means our specialist agents WILL have `exec` and can run `curl` commands — exactly what HOOK needs.

### Limitations
- Sub-agents cannot spawn their own sub-agents (at `maxSpawnDepth: 1`)
- Announce is best-effort — lost if gateway restarts mid-run
- Each subagent has its own token budget (cost consideration)
- Auto-generated session IDs (not addressable by name)

---

## Mechanism 2: `sessions_send` + `agentToAgent` (DEFER — Known Bug)

### How It Works
- Direct messaging between peer agents using `sessions_send(sessionKey, message)`
- Supports synchronous ping-pong: `session.agentToAgent.maxPingPongTurns` (0–5, default 5)
- Agents can have real back-and-forth conversations

### Config Required
```jsonc
{
  "tools": {
    "agentToAgent": {
      "enabled": true,
      "allow": ["coordinator", "triage-analyst", "osint-researcher", "incident-responder", "threat-intel", "report-writer"]
    }
  }
}
```

### ⚠️ CRITICAL BUG: GitHub Issue #5813
**`agentToAgent.enabled: true` breaks `sessions_spawn`**
- When agentToAgent is enabled, subagents spawned via sessions_spawn fail to start
- They appear in session list but stay at 0 tokens indefinitely
- 100% reproducible
- **Workaround:** Do NOT enable agentToAgent until this is fixed
- **Status:** Open issue as of Feb 2026

### Also: Issue #5157
- Sub-agents see session tools in their system prompt but they're not actually bound to the API
- Model hallucinates tool calls based on prompt text
- Marked "closed as not planned" — by design for now

### Recommendation
**Do NOT use agentToAgent in Phase 2.** Use `sessions_spawn` only. Revisit when #5813 is resolved.

---

## Mechanism 3: Lobster Workflows (FUTURE — Phase 3+)

### What It Is
- Deterministic workflow engine: YAML/JSON pipeline definitions
- Steps execute sequentially with explicit approval gates
- Can chain `openclaw.invoke` calls to different agent tools
- Supports `llm_task` for structured JSON-only LLM steps with schema validation
- Resumable with tokens — halted workflows can be approved and continued

### Config Required
```jsonc
{
  "plugins": {
    "entries": {
      "lobster": { "enabled": true },
      "llm-task": { "enabled": true }
    }
  },
  "agents": {
    "list": [{ "id": "coordinator", "tools": { "allow": ["lobster", "llm-task"] } }]
  }
}
```

### Why Defer
- Requires Lobster CLI installed on gateway host
- Adds complexity beyond what Phase 2 needs
- Best for: repeatable, deterministic workflows (IR playbooks, daily triage)
- HOOK's coordinator-to-specialist routing works fine with sessions_spawn
- Consider for Phase 3 when building automated IR playbooks

---

## Mechanism 4: File-Based Coordination (NOT RECOMMENDED)

Some community members use shared filesystem + polling (agent reads another agent's session files). This works but:
- No push notification — requires polling
- Fragile — depends on file paths and timing
- OpenClaw's native tools are better

---

## Recommended HOOK Architecture

```
User (Slack #hook-test)
    │
    ▼
OpenClaw Gateway (:18789)
    │
    ├── Binding: match.channel = "slack" → agentId: "coordinator"
    │
    ▼
Coordinator Agent (default, receives all messages)
    │
    ├── sessions_spawn(agentId: "triage-analyst", task: "Analyze this alert...")
    ├── sessions_spawn(agentId: "osint-researcher", task: "Enrich IOC 45.77.x.x...")
    ├── sessions_spawn(agentId: "incident-responder", task: "Containment guidance for...")
    ├── sessions_spawn(agentId: "threat-intel", task: "Attribution analysis for...")
    └── sessions_spawn(agentId: "report-writer", task: "Write executive summary...")
         │
         ▼
    Results announced back to #hook-test
```

### Flow
1. User posts alert/question to `#hook-test`
2. Coordinator receives it (default agent via binding)
3. Coordinator's SOUL.md has routing logic: decides which specialist(s) to invoke
4. Coordinator calls `sessions_spawn` with task description and target `agentId`
5. Specialist runs in isolated session with full `exec` + `curl` access
6. Specialist completes → result announced back to Slack channel
7. Coordinator can chain: spawn triage → read result → spawn osint → read result → spawn report-writer

### Config Skeleton for openclaw.json
```jsonc
{
  "agents": {
    "defaults": {
      "model": { "primary": "openai/gpt-4.1" },
      "workspace": "~/.openclaw/workspace",
      "subagents": {
        "maxConcurrent": 3,
        "maxSpawnDepth": 1,
        "maxChildrenPerAgent": 5,
        "runTimeoutSeconds": 180,
        "archiveAfterMinutes": 60
      }
    },
    "list": [
      {
        "id": "coordinator",
        "default": true,
        "workspace": "/path/to/hook/workspaces/coordinator",
        "subagents": {
          "allowAgents": ["triage-analyst", "osint-researcher", "incident-responder", "threat-intel", "report-writer"]
        }
      },
      {
        "id": "triage-analyst",
        "workspace": "/path/to/hook/workspaces/triage-analyst",
        "model": { "primary": "openai/gpt-4.1" }
      },
      {
        "id": "osint-researcher",
        "workspace": "/path/to/hook/workspaces/osint-researcher",
        "model": { "primary": "openai/gpt-4.1" }
      },
      {
        "id": "incident-responder",
        "workspace": "/path/to/hook/workspaces/incident-responder",
        "model": { "primary": "openai/gpt-5" }
      },
      {
        "id": "threat-intel",
        "workspace": "/path/to/hook/workspaces/threat-intel",
        "model": { "primary": "openai/gpt-5" }
      },
      {
        "id": "report-writer",
        "workspace": "/path/to/hook/workspaces/report-writer",
        "model": { "primary": "openai/gpt-4.1" }
      }
    ]
  },
  "bindings": [
    { "agentId": "coordinator", "match": { "channel": "slack" } }
  ]
}
```

---

## Key Lessons from Community

1. **"Don't orchestrate with LLMs"** — LLMs are unreliable routers. Keep routing logic in SOUL.md prompts simple and explicit. Don't ask the LLM to decide complex flow control.

2. **Sub-agents keep the main session clean** — Noise stays in the subagent transcript, not the coordinator's context.

3. **Cost control** — Each subagent has its own context/tokens. Use cheaper models for subagents where possible (`agents.defaults.subagents.model`).

4. **Get one agent stable first** — Don't jump to multi-agent immediately. Get the coordinator working alone, then add specialists one at a time.

5. **Validate with `openclaw agents list --bindings`** — Routing bugs are almost always binding bugs.

6. **Auth profiles are per-agent** — API keys need to be available in each agent's agentDir, or inherited from main.

---

## Open Questions for Implementation

1. **Will subagent exec have access to env vars (API keys)?** — ✅ **ANSWERED (Phase 2):** Yes. The coordinator's `env` config propagates to subagents when sandbox is off (exec runs on host). All agents have access to `$VT_API_KEY`, `$CENSYS_API_ID`, `$CENSYS_API_SECRET`, `$ABUSEIPDB_API_KEY`. When sandboxing is enabled, env vars must be passed via `agents.defaults.sandbox.docker.env`.

2. **How does subagent announce format in Slack?** — ✅ **ANSWERED (Phase 3):** Announces appear as system messages in the chat channel with a normalized template: Status (success/error/timeout) + Result (the subagent's summary text). Formatting is clean enough to read and extract findings from.

3. **Can coordinator read subagent results programmatically?** — ✅ **ANSWERED (Phase 3):** Yes, two methods: (a) The announce callback is delivered as a system message to the coordinator's chat — passive receipt. (b) `sessions_history(childSessionKey)` returns the full subagent transcript including tool calls — active retrieval. The `childSessionKey` is returned by `sessions_spawn` in the response object.

4. **Tool allowlist inheritance** — ✅ **ANSWERED (Phase 2):** Subagents get all tools except session tools (`sessions_spawn`, `sessions_list`, `sessions_history`, `sessions_send`) and system tools (`gateway`, `cron`). This means specialist agents DO get `exec`, `read`, `write`, `edit` by default. No explicit `tools.subagents.tools.allow` needed for HOOK's current setup.

---

## References

- [OpenClaw Multi-Agent Routing](https://docs.openclaw.ai/concepts/multi-agent)
- [OpenClaw Session Tools](https://docs.openclaw.ai/concepts/session-tool)
- [OpenClaw Sub-Agents](https://docs.openclaw.ai/tools/subagents) (via Fossies mirror)
- [OpenClaw Tools Index](https://docs.openclaw.ai/tools)
- [DeepWiki: Multi-Agent Configuration](https://deepwiki.com/openclaw/openclaw/4.3-multi-agent-configuration)
- [DeepWiki: Subagent Management](https://deepwiki.com/openclaw/openclaw/9.6-subagent-management)
- [GitHub Issue #5813: agentToAgent breaks sessions_spawn](https://github.com/openclaw/openclaw/issues/5813)
- [GitHub Issue #5157: Sub-agent session tools not bound](https://github.com/openclaw/openclaw/issues/5157)
- [Medium: Teaching AI Agents to Talk to Each Other](https://medium.com/@chen.yang_50796/teaching-ai-agents-to-talk-to-each-other-inter-agent-communication-in-openclaw-736e60310005)
- [DEV: Deterministic Multi-Agent Pipeline](https://dev.to/ggondim/how-i-built-a-deterministic-multi-agent-dev-pipeline-inside-openclaw-and-contributed-a-missing-4ool)
- [LumaDock: OpenClaw Multi-Agent Setup](https://lumadock.com/tutorials/openclaw-multi-agent-setup)
- [Dan Malone: AI Mission Control with OpenClaw](https://www.dan-malone.com/blog/building-a-multi-agent-ai-team-in-a-telegram-forum)
- [OpenClaw Lobster](https://github.com/openclaw/lobster)
- [OpenClaw LLM Task](https://docs.openclaw.ai/tools/llm-task)
