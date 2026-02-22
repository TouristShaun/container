# AI-Powered GitHub Alternative for Multi-CLI Pair Programming

## 1) Vision
Build a self-hosted collaboration platform ("Infinity Forge") that allows multiple AI coding CLIs (Claude Code, OpenAI Codex CLI, Gemini CLI) to pair program against a shared codebase using Git worktrees, with first-class agent-to-agent communication, instruction lifecycle management, and controlled autonomous execution.

Primary environment:
- **Control plane + services** on a DigitalOcean Droplet.
- **AI CLIs** running on your MacBook Air, connected to the platform over secure APIs/WebSocket.

## 2) Product Goals
1. Replace core GitHub workflow primitives for your use-case (single operator + many AI workers).
2. Support many concurrent agents per provider with deterministic routing.
3. Let agents communicate through the system (threaded, auditable, policy-aware).
4. Let you update instructions at any point while preserving long-running context.
5. Use Git worktrees to isolate and parallelize coding tasks.
6. Make first milestone: "perfect OAuth for a team-of-one referral-only app ecosystem".

## 3) High-Level Architecture

```text
┌──────────────────────────────┐
│          MacBook Air         │
│  Claude/Codex/Gemini CLIs    │
│  + local runner adapters      │
└──────────────┬───────────────┘
               │ mTLS + JWT + WS
┌──────────────▼─────────────────────────────────────────────────────────┐
│                         DigitalOcean Droplet                          │
│                                                                       │
│  API Gateway  ── AuthN/AuthZ ── Org/Project Service                  │
│       │                         │                                      │
│       ├── Agent Orchestrator ───┼── Instruction Service               │
│       │                         │                                      │
│       ├── Task/Queue Service ───┼── Worktree Manager                  │
│       │                         │                                      │
│       ├── Inter-Agent Bus  ─────┼── Suggestion/Review Service         │
│       │                         │                                      │
│       ├── Git Service (bare repo + refs + merge queue)               │
│       │                                                                │
│       └── Observability (logs/traces/audit/events)                    │
│                                                                       │
│  Data: PostgreSQL + Redis + Object Storage (S3-compatible)           │
└───────────────────────────────────────────────────────────────────────┘
```

## 4) Core Domain Model
- **Project**: shared codebase boundary.
- **InstructionSet**: current canonical operating instructions.
- **InstructionVersion**: immutable snapshots + migration notes.
- **AgentProfile**: provider type (`claude`, `codex`, `gemini`), alpha weight, capabilities.
- **Session**: one run of an agent against a task.
- **Task**: user objective; decomposed into subtasks.
- **WorktreeLease**: lifecycle for a Git worktree and associated branch.
- **ConversationThread**: inter-agent and human-agent messages.
- **Proposal**: suggested enhancement, patchset, or architectural recommendation.
- **Policy**: guardrails (filesystem, command class, secret scope, merge constraints).

## 5) Worktree-Native Collaboration
### Branching strategy
- Base branch: `main`.
- Per task: `task/<ticket>-<slug>`.
- Per agent attempt: `agent/<provider>/<task>/<run-id>`.
- Optional integration branch for consensus merge: `integration/<task>`.

### Worktree lifecycle
1. Orchestrator assigns subtask to an agent type.
2. Worktree Manager creates branch + worktree directory.
3. CLI adapter receives checkout path and run token.
4. Agent edits, commits, pushes to Git Service.
5. Review service runs checks and opens proposal.
6. Merge queue handles fast-forward/squash/rebase policies.

### Concurrency controls
- File-level ownership hints (soft locks).
- Semantic conflict detector using AST + git diff.
- Auto-rebase bot + conflict resolution task spawning.

## 6) Agent-to-Agent Communication
Implement a platform-native messaging layer:
- **Channels**:
  - `task:<id>` shared room for all agents on task.
  - `agent:<id>` direct messages.
  - `review:<proposal-id>` critique threads.
- **Message types**:
  - `question`, `proposal`, `status`, `handoff`, `blocker`, `patch_ref`, `policy_alert`.
- **Memory model**:
  - Short-term thread context in Redis.
  - Durable summaries in PostgreSQL.
  - Auto-summarization checkpoint every N messages.
- **Safety**:
  - Prompt injection scanner.
  - Secret redaction.
  - Policy engine blocks disallowed requests.

## 7) Alpha-Based Agent Allocation
You requested "alpha for each CLI type determines at the start of instructions".

Use **alpha weights** as default scheduling ratios at task initialization:

```yaml
agent_alpha:
  claude: 0.40
  codex: 0.35
  gemini: 0.25
```

Rules:
1. Parse alpha config from instruction header.
2. Normalize to sum=1.0.
3. For each new task, allocate planned subtasks proportionally.
4. Permit dynamic override if one provider lacks capability.
5. Log all overrides in audit trail.

## 8) Instruction Update Lifecycle (Graceful Mid-Run Changes)
Your requirement: "easy updates to instructions and agents handle gracefully in the time they need."

Design:
1. **Patch-based updates**: you submit delta instructions, not full rewrites.
2. **Versioned rollout**:
   - `draft` -> `staged` -> `active`.
3. **Agent sync protocol**:
   - orchestrator sends `instruction_update` event with semantic diff.
   - running agents mark current step boundary.
   - at safe checkpoint, they acknowledge and re-plan.
4. **Compatibility tags**:
   - `breaking`, `non_breaking`, `policy_only`.
5. **Timeout behavior**:
   - if agent does not ack in threshold, session is paused and resumed with reconciled context.

## 9) OAuth-First Milestone (Referral-Only, Team-of-One)
First task is a best-in-class OAuth system for a solo operator distributing apps by referral.

### Identity model
- **Operator**: you (team of one).
- **Member**: opt-in user in Infinity Forward Ltd ecosystem.
- **App**: member-specific or shared app.
- **Relationship contract**: explicit consent artifact (terms + durable acceptance log).

### OAuth architecture
- Build centralized **Authorization Server** with OIDC support.
- Each member app is an OAuth client (confidential or PKCE public client).
- Use fine-grained scopes:
  - `profile:read`, `membership:read`, `apps:connect`, `referral:verify`, `agent:assist`.
- Use token exchange for app-to-app delegation.
- Use dynamic client registration restricted by operator policy.

### Referral-only onboarding flow
1. Operator creates signed invite token (short TTL, single-use).
2. Invitee lands on onboarding portal.
3. Invite token verified + relationship contract consent captured.
4. Membership record created, referral graph updated.
5. OAuth client bootstrap for that member's app(s).
6. Optional cross-app communication permissions granted by consent screen.

### Security controls
- PKCE everywhere possible.
- DPoP or mTLS for high-trust clients.
- Rotating refresh tokens with reuse detection.
- Device/session risk scoring.
- Signed audit logs (append-only).

## 10) App-to-App Communication & Enhancement Suggestions
To allow "members apps speak to each other" and "suggest enhancements":

- Introduce **App Mesh Gateway**:
  - service identity via OAuth client credentials + JWT bearer assertions.
  - policy-driven API access between member apps.
- Add **Enhancement Broker**:
  - apps emit suggestions as structured events.
  - ranking engine scores impact/risk.
  - operator-approved automation can create tasks for AI agents.

## 11) Deployment on a Single Droplet (Alpha Stage)
Use a modular monolith + background workers initially.

### Stack recommendation
- Backend: TypeScript (NestJS) or Go (Fiber/Chi).
- DB: PostgreSQL.
- Cache/queue: Redis + BullMQ / Faktory.
- Git backend: bare repos on disk + libgit2/isomorphic-git operations.
- Real-time: WebSocket gateway.
- Auth server: ORY Hydra / Zitadel / custom OIDC service.
- Reverse proxy: Caddy or Nginx.
- Observability: OpenTelemetry + Grafana Loki/Tempo.

### Services (can be same deployable at first)
- `gateway`
- `orchestrator`
- `git-service`
- `instruction-service`
- `comms-service`
- `oauth-service`
- `worker`

## 12) MacBook CLI Integration Pattern
Each CLI gets a thin adapter process:
- Authenticates to droplet.
- Receives task payload + worktree path + constraints.
- Streams logs, events, and diffs back.
- Reads inter-agent messages and posts replies.

Adapters normalize differences in CLI capabilities:
- command invocation,
- tool permissions,
- streaming output parsing,
- structured result schema.

## 13) API Surface (Minimal)
- `POST /v1/tasks`
- `POST /v1/tasks/{id}/dispatch`
- `POST /v1/instructions/patch`
- `GET /v1/instructions/active`
- `POST /v1/messages`
- `GET /v1/messages/stream`
- `POST /v1/worktrees/lease`
- `POST /v1/proposals`
- `POST /v1/oauth/invites`
- `POST /v1/oauth/consent`
- `POST /v1/oauth/token-exchange`

## 14) Data Schema (Starter)
- `projects`
- `instruction_sets`, `instruction_versions`
- `agent_profiles`, `agent_sessions`
- `tasks`, `subtasks`, `task_assignments`
- `worktree_leases`
- `threads`, `messages`, `message_summaries`
- `proposals`, `reviews`, `merge_events`
- `oauth_clients`, `oauth_consents`, `oauth_invites`, `membership_contracts`
- `audit_events`

## 15) Phased Build Plan
### Phase 0 (Week 1)
- Git service with worktree leases.
- Task orchestration.
- One CLI adapter (Codex first).
- Basic message bus.

### Phase 1 (Week 2-3)
- Add Claude + Gemini adapters.
- Alpha-weighted scheduler.
- Instruction versioning and safe checkpoint updates.

### Phase 2 (Week 4-5)
- OAuth/OIDC server integration.
- Referral-only onboarding and consent ledger.
- App-to-app delegated auth.

### Phase 3 (Week 6)
- Enhancement broker.
- Policy tuning + audit dashboards.
- Hardening and disaster recovery tests.

## 16) Non-Negotiable Guardrails
- Every agent action is attributable and replayable.
- No direct secret exposure to agent channels.
- Instruction updates are transactional and versioned.
- Merge-to-main always policy gated.
- OAuth consent and invite artifacts are immutable.

## 17) Suggested First Backlog Items
1. Bootstrap monorepo + local dev compose stack.
2. Implement `worktree_leases` API and service.
3. Build Codex adapter prototype.
4. Add task channel messaging.
5. Add instruction patch/activate workflow.
6. Add OAuth invite issuance + redemption.
7. Add consent ledger and membership contract store.
8. End-to-end test: invite -> onboard -> app token -> cross-app call.

## 18) Success Criteria for Alpha
- 3+ concurrent agents can modify the same repo via worktrees without corrupting main.
- You can patch instructions mid-run and all sessions converge.
- Agents can communicate in-thread and produce merged proposals.
- Referral-only onboarding works end-to-end with auditable consent.
- Member app A can securely call member app B with policy checks.
