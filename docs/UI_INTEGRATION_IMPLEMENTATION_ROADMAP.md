# UI Integration Implementation Roadmap

**Date**: 2026-02-27
**Status**: Issues Created and Ready for Development

This document tracks all GitHub issues created for the UI ↔ OpenClaw Gateway integration work, organized by phase and repository.

## Overview

**Total Issues**: 12 (7 backend, 5 frontend)
**Estimated Duration**: 8 weeks
**Reference**: `docs/UI_OPENCLAW_GATEWAY_INTEGRATION_GAP_ANALYSIS.md`

---

## Phase 1: Critical Fixes (Week 1-2)

**Goal**: Fix the channels architecture mismatch

### Backend (openclaw-backend)

| Issue # | Title | Points | Status |
|---------|-------|--------|--------|
| [#81](https://github.com/AINative-Studio/openclaw-backend/issues/81) | Create Global Channel Management API Endpoints | 5 | Open |
| [#82](https://github.com/AINative-Studio/openclaw-backend/issues/82) | Migrate Agent Channel Config to Global Workspace Settings | 2 | Open |

**Total**: 7 story points (1 week)

### Frontend (agent-swarm-monitor)

| Issue # | Title | Status |
|---------|-------|--------|
| [#6](https://github.com/AINative-Studio/agent-swarm-monitor/issues/6) | Refactor Channels Page to Use Global Channel API | Open |

**Dependencies**:
- Frontend #6 depends on Backend #81

**Key Deliverables**:
- ✅ Channels managed globally via OpenClaw Gateway (not per-agent)
- ✅ New `/channels` API endpoints (list, enable, disable, status)
- ✅ OpenClawGatewayProxy service created
- ✅ Migration script for existing channel configs
- ✅ UI channels page refactored (agent picker removed)

---

## Phase 2: Core Features (Week 3-4)

**Goal**: Add API key management, team management, enhanced monitoring

### Backend (openclaw-backend)

| Issue # | Title | Points | Status |
|---------|-------|--------|--------|
| [#83](https://github.com/AINative-Studio/openclaw-backend/issues/83) | Create API Key Management Endpoints | 3 | Open |
| [#84](https://github.com/AINative-Studio/openclaw-backend/issues/84) | Create Team Management Endpoints | 3 | Open |

**Total**: 6 story points (1 week)

### Frontend (agent-swarm-monitor)

| Issue # | Title | Status |
|---------|-------|--------|
| [#7](https://github.com/AINative-Studio/agent-swarm-monitor/issues/7) | Integrate API Key Management with Backend | Open |
| [#8](https://github.com/AINative-Studio/agent-swarm-monitor/issues/8) | Integrate Team Management Page with Backend | Open |
| [#9](https://github.com/AINative-Studio/agent-swarm-monitor/issues/9) | Enhance Monitoring Page with Prometheus Metrics | Open |

**Dependencies**:
- Frontend #7 depends on Backend #83
- Frontend #8 depends on Backend #84

**Key Deliverables**:
- ✅ API keys stored and encrypted in backend (not local React state)
- ✅ Team members managed via backend (invite, remove, role management)
- ✅ Settings page fully integrated
- ✅ Monitoring page shows Prometheus metrics, timeline, alert thresholds

---

## Phase 3: Advanced Features (Week 5-6)

**Goal**: Expose P2P networking and task queue visibility

### Backend (openclaw-backend)

| Issue # | Title | Points | Status |
|---------|-------|--------|--------|
| [#85](https://github.com/AINative-Studio/openclaw-backend/issues/85) | Create P2P Network Management UI Endpoints | 3 | Open |
| [#86](https://github.com/AINative-Studio/openclaw-backend/issues/86) | Create Task Queue Visibility Endpoints | 3 | Open |

**Total**: 6 story points (1 week)

### Frontend (agent-swarm-monitor)

| Issue # | Title | Status |
|---------|-------|--------|
| [#10](https://github.com/AINative-Studio/agent-swarm-monitor/issues/10) | Create Network Management Page (/network) | Open |
| [#11](https://github.com/AINative-Studio/agent-swarm-monitor/issues/11) | Create Task Queue Page (/tasks) | Open |

**Dependencies**:
- Frontend #10 depends on Backend #85
- Frontend #11 depends on Backend #86

**Key Deliverables**:
- ✅ `/network` page showing WireGuard peers, network quality, IP pool status
- ✅ `/tasks` page showing task queue, active leases, task history
- ✅ Provision peer UI with QR code generation
- ✅ Task detail modal with execution history

---

## Phase 4: Security (Week 7-8)

**Goal**: Expose security management features (capability tokens, audit logs)

### Backend (openclaw-backend)

| Issue # | Title | Points | Status |
|---------|-------|--------|--------|
| [#87](https://github.com/AINative-Studio/openclaw-backend/issues/87) | Create Security Management UI Endpoints | 5 | Open |

**Total**: 5 story points (1 week)

### Frontend (agent-swarm-monitor)

| Issue # | Title | Status |
|---------|-------|--------|
| [#12](https://github.com/AINative-Studio/agent-swarm-monitor/issues/12) | Create Security Management Page (/security) | Open |

**Dependencies**:
- Frontend #12 depends on Backend #87

**Key Deliverables**:
- ✅ `/security` page with 3 tabs: Capability Tokens, Peer Keys, Audit Logs
- ✅ Token management UI (issue, revoke, rotate)
- ✅ Peer key viewer with fingerprints
- ✅ Audit log search with filters and export

---

## Issue Distribution by Repository

### openclaw-backend (7 issues)

**Phase 1**: 2 issues (7 points)
**Phase 2**: 2 issues (6 points)
**Phase 3**: 2 issues (6 points)
**Phase 4**: 1 issue (5 points)

**Total**: 24 story points (~5 weeks engineering time)

### agent-swarm-monitor (5 issues)

**Phase 1**: 1 issue
**Phase 2**: 3 issues
**Phase 3**: 2 issues
**Phase 4**: 1 issue

**Total**: ~3-4 weeks engineering time

---

## Critical Path

```
Phase 1 (CRITICAL - must be done first)
├─ Backend #81: Channel API endpoints
├─ Backend #82: Migration script
└─ Frontend #6: Channels page refactor

Phase 2 (Core features)
├─ Backend #83: API key endpoints  → Frontend #7: Settings integration
├─ Backend #84: Team endpoints     → Frontend #8: Team integration
└─ Frontend #9: Monitoring enhancements (no backend dependency)

Phase 3 (Advanced features)
├─ Backend #85: Network endpoints  → Frontend #10: Network page
└─ Backend #86: Task endpoints     → Frontend #11: Task page

Phase 4 (Security)
└─ Backend #87: Security endpoints → Frontend #12: Security page
```

---

## Repository URLs

- **Backend**: https://github.com/AINative-Studio/openclaw-backend
- **Frontend**: https://github.com/AINative-Studio/agent-swarm-monitor

---

## Development Workflow

### For Each Issue

1. **Backend Issue**:
   - Create endpoint in `backend/api/v1/endpoints/`
   - Create/update service in `backend/services/`
   - Create/update schemas in `backend/schemas/`
   - Create/update models in `backend/models/` (if DB changes)
   - Write integration tests
   - Update API documentation
   - Create PR referencing issue

2. **Frontend Issue**:
   - Create/update page in `app/`
   - Create React Query hooks in `hooks/`
   - Create/update components in `components/`
   - Remove mock data from `lib/openclaw-mock-data.ts`
   - Write component tests
   - Create PR referencing issue

### Testing Strategy

**Backend**:
- Integration tests for all new endpoints
- Test OpenClaw Gateway proxy operations
- Test error handling and edge cases

**Frontend**:
- Component tests with React Testing Library
- E2E tests for critical flows (channel connection, API key management)
- Visual regression tests for new pages

---

## Success Criteria

### Phase 1 Complete When:
- [ ] All agents' channel configs migrated to OpenClaw Gateway
- [ ] Channels page no longer has agent picker
- [ ] WhatsApp/Telegram/Slack/Discord can be enabled globally
- [ ] Zero channel credentials in agent database

### Phase 2 Complete When:
- [ ] API keys stored in backend (encrypted)
- [ ] Team members managed via backend
- [ ] Settings page fully functional
- [ ] Monitoring page shows metrics and timeline

### Phase 3 Complete When:
- [ ] `/network` page live with peer management
- [ ] `/tasks` page live with queue visibility
- [ ] Peer provisioning works end-to-end

### Phase 4 Complete When:
- [ ] `/security` page live with all 3 tabs
- [ ] Capability tokens can be issued/revoked via UI
- [ ] Audit logs searchable and exportable

---

## Risk Mitigation

### High Risk Items

1. **OpenClaw Gateway Integration** (Phase 1)
   - Risk: OpenClaw CLI/config management may have unexpected behavior
   - Mitigation: Thorough testing with actual OpenClaw Gateway instance, fallback to manual config if needed

2. **Data Migration** (Phase 1)
   - Risk: Existing agent channel configs may have inconsistent data
   - Mitigation: Dry-run migration script, rollback procedure documented

3. **Encryption Key Management** (Phase 2)
   - Risk: Losing encryption key = losing all API keys
   - Mitigation: Key rotation procedure, backup/recovery documented

### Dependencies

- OpenClaw Gateway must be running on localhost:18789
- `~/.openclaw/openclaw.json` must be readable/writable by backend
- Database migrations must run without downtime

---

## Next Steps

1. **Team Review**: Review this roadmap and gap analysis with team
2. **Sprint Planning**: Assign issues to sprints (recommend 2-week sprints)
3. **Start Phase 1**: Begin with openclaw-backend#81 (highest priority)
4. **Weekly Sync**: Frontend/backend teams sync on integration points
5. **Demo After Each Phase**: Show working features to stakeholders

---

## Notes

- All issues use standard GitHub labels (enhancement, type:feature, etc.)
- Story points follow Fibonacci scale (1, 2, 3, 5, 8)
- Frontend issues don't have point estimates (estimated in days in issue body)
- Issues can be reassigned to different phases if priorities change
- Gap analysis document is the source of truth for technical details

---

**Last Updated**: 2026-02-27
**Next Review**: Start of Phase 2 (Week 3)
