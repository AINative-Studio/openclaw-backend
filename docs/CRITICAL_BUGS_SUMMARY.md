# CRITICAL BUGS - Agent Configuration UI

**Status:** BLOCKING - Feature Non-Functional ❌
**Discovered:** 2026-02-24
**Severity:** P0 - Production Blocking
**Estimated Fix Time:** 2-3 days

---

## CRITICAL: Feature Does Not Work

The agent configuration UI appears complete but **does not save any data**. All buttons are non-functional placeholders. Users cannot configure their agents.

---

## 6 Blocking Bugs

### BUG-001: Integrations UI Non-Functional ❌
**File:** `/components/openclaw/AgentSettingsTab.tsx:205-211`
**Problem:** IntegrationRow has no onConnect handler
**Impact:** Users cannot connect Gmail or LinkedIn
**Fix:** Wire GmailConnectionDialog and LinkedInConnectionDialog to integration rows

```tsx
// CURRENT (BROKEN):
{MOCK_INTEGRATIONS.map((integration) => (
  <IntegrationRow
    key={integration.id}
    integration={integration}
    // ❌ Missing: onConnect prop
  />
))}

// REQUIRED FIX:
{MOCK_INTEGRATIONS.map((integration) => (
  <IntegrationRow
    key={integration.id}
    integration={integration}
    onConnect={() => handleOpenIntegrationModal(integration.id)}
  />
))}
```

---

### BUG-002: API Keys UI Non-Functional ❌
**File:** `/components/openclaw/AgentSettingsTab.tsx:220-239`
**Problem:** "Add Key" buttons have no onClick handler
**Impact:** Users cannot add API keys for Anthropic, OpenAI, etc.
**Fix:** Wire ApiKeyModal component

```tsx
// CURRENT (BROKEN):
<button type="button" className={cn(...)}>
  <Plus className="h-3.5 w-3.5" />
  <span className="text-xs">Add Key</span>
  {/* ❌ No onClick handler */}
</button>

// REQUIRED FIX:
<button
  type="button"
  onClick={() => handleOpenApiKeyModal(provider.id)}
  className={cn(...)}
>
  <Plus className="h-3.5 w-3.5" />
  <span className="text-xs">Add Key</span>
</button>
```

---

### BUG-003: Channels UI Non-Functional ❌
**File:** `/components/openclaw/AgentChannelsTab.tsx:19-22`
**Problem:** onConnect has empty implementation
**Impact:** Users cannot connect Slack, Telegram, Discord, etc.
**Fix:** Wire channel modals (SlackChannelModal, TelegramChannelModal, etc.)

```tsx
// CURRENT (BROKEN):
onConnect={() => {
  // Connection logic would go here
}}

// REQUIRED FIX:
onConnect={() => handleOpenChannelModal(channel.id)}
```

---

### BUG-004: Active Hours Non-Functional ❌
**File:** `/components/openclaw/AgentSettingsTab.tsx:166-176`
**Problem:** Switch state exists but modal never opens
**Impact:** Users cannot configure active hours scheduling
**Fix:** Wire ActiveHoursModal component

```tsx
// CURRENT (BROKEN):
const [activeHours, setActiveHours] = useState(false);

<Switch
  checked={activeHours}
  onCheckedChange={setActiveHours}
  // ❌ Only changes boolean state, modal never opens
/>

// REQUIRED FIX:
<Switch
  checked={!!agent.configuration?.activeHours?.enabled}
  onCheckedChange={(enabled) => {
    if (enabled) {
      setActiveHoursModalOpen(true);
    } else {
      handleDisableActiveHours();
    }
  }}
/>
```

---

### BUG-005: Configuration Not Persisted to Backend ❌
**File:** `/components/openclaw/AgentSettingsTab.tsx:52-64`
**Problem:** handleSave() doesn't include configuration field
**Impact:** ALL configuration data is lost - nothing saves to database
**Fix:** Build configuration object and include in save request

```tsx
// CURRENT (BROKEN):
const handleSave = useCallback(() => {
  onSave({
    model,
    persona: persona.trim() || undefined,
    heartbeat: {
      enabled: heartbeatEnabled,
      interval: heartbeatEnabled ? heartbeatInterval : undefined,
      checklist: heartbeatEnabled && heartbeatChecklist.trim()
        ? heartbeatChecklist.split('\n').filter((line) => line.trim())
        : undefined,
    },
    // ❌ Missing: configuration field
  });
}, [model, persona, heartbeatEnabled, heartbeatInterval, heartbeatChecklist, onSave]);

// REQUIRED FIX:
const handleSave = useCallback(() => {
  onSave({
    model,
    persona: persona.trim() || undefined,
    heartbeat: { ... },
    configuration: {
      integrations: integrationConfig,
      apiKeys: apiKeyConfig,
      channels: channelConfig,
      activeHours: activeHoursConfig,
      fixPrompts: fixPrompts,
    },
  });
}, [model, persona, heartbeat, integrationConfig, apiKeyConfig, channelConfig, activeHoursConfig, fixPrompts, onSave]);
```

---

### BUG-006: Mock Data Still Used Instead of Backend Data ❌
**Files:**
- `/components/openclaw/AgentSettingsTab.tsx:205` (MOCK_INTEGRATIONS)
- `/components/openclaw/AgentSettingsTab.tsx:220` (MOCK_API_KEY_PROVIDERS)
- `/components/openclaw/AgentChannelsTab.tsx:15` (MOCK_CHANNELS)

**Problem:** Hardcoded mock data displayed instead of agent.configuration
**Impact:** Users see fake data that doesn't reflect their actual configuration
**Fix:** Derive UI state from agent.configuration field

```tsx
// CURRENT (BROKEN):
{MOCK_INTEGRATIONS.map((integration) => (
  ...
))}

// REQUIRED FIX:
const integrations = useMemo(() => {
  const config = agent.configuration?.integrations || {};
  return [
    {
      id: 'gmail',
      name: 'Gmail',
      icon: 'gmail',
      description: 'Receive emails...',
      connected: !!config.gmail?.enabled,
    },
    {
      id: 'linkedin',
      name: 'LinkedIn',
      icon: 'linkedin',
      description: 'Post content...',
      connected: !!config.linkedin?.enabled,
    },
  ];
}, [agent.configuration]);

{integrations.map((integration) => (
  ...
))}
```

---

## What Actually Works ✅

1. **Type Definitions** - Complete and correct (`/types/agent-configuration.ts`)
2. **Modal Components** - All functional in isolation (ApiKeyModal, ActiveHoursModal, etc.)
3. **Backend API** - GET/PATCH endpoints exist and work
4. **Database Schema** - configuration JSON column exists

---

## What's Missing ❌

1. **State Management** - No configuration state tracking
2. **Modal Wiring** - Modals exist but are never imported/opened
3. **Save Logic** - Configuration not included in save request
4. **Data Flow** - Mock data instead of backend data

---

## Quick Fix Checklist

```tsx
// Add to AgentSettingsTab.tsx:

// 1. Import modals
import ApiKeyModal from './ApiKeyModal';
import ActiveHoursModal from './ActiveHoursModal';
import GmailConnectionDialog from './GmailConnectionDialog';
import LinkedInConnectionDialog from './LinkedInConnectionDialog';

// 2. Add state for configuration
const [configuration, setConfiguration] = useState<AgentConfiguration>(
  agent.configuration || {}
);

// 3. Add state for modal open/close
const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false);
const [activeHoursModalOpen, setActiveHoursModalOpen] = useState(false);
const [gmailDialogOpen, setGmailDialogOpen] = useState(false);
// ... etc for all modals

// 4. Add handlers
const handleSaveApiKey = (providerId: string, apiKey: string) => {
  setConfiguration(prev => ({
    ...prev,
    apiKeys: {
      ...prev.apiKeys,
      [providerId]: {
        key: apiKey,
        masked: maskApiKey(apiKey),
        addedAt: new Date().toISOString(),
      },
    },
  }));
};

// 5. Update handleSave to include configuration
const handleSave = () => {
  onSave({
    model,
    persona,
    heartbeat: { ... },
    configuration, // ← Add this
  });
};

// 6. Wire modals to buttons/rows
<IntegrationRow
  integration={integration}
  onConnect={() => {
    if (integration.id === 'gmail') setGmailDialogOpen(true);
    if (integration.id === 'linkedin') setLinkedInDialogOpen(true);
  }}
/>

// 7. Render modals
<ApiKeyModal
  open={apiKeyModalOpen}
  onOpenChange={setApiKeyModalOpen}
  onSave={handleSaveApiKey}
  // ... props
/>

<ActiveHoursModal
  open={activeHoursModalOpen}
  onClose={() => setActiveHoursModalOpen(false)}
  onSave={handleSaveActiveHours}
  // ... props
/>

// ... etc for all modals
```

---

## Impact Assessment

### User Impact
- **Critical:** Users cannot configure their agents at all
- **Severity:** Feature appears to work (buttons exist) but does nothing
- **Frustration:** High - misleading UI

### Business Impact
- **Production Readiness:** NOT READY
- **Release Blocker:** YES
- **Workaround:** NONE - feature must be fixed

---

## Root Cause

**Coordination Failure:** Each agent (3-7) built their individual modals correctly, but no agent was assigned to integrate them into the parent component. The "glue code" connecting modals to AgentSettingsTab/AgentChannelsTab was never implemented.

---

## Recommended Action

1. **Assign to:** Senior Frontend Engineer or Integration Specialist
2. **Priority:** P0 - Immediate
3. **Estimated Effort:** 2-3 days
4. **Dependencies:** None - all pieces exist, just need wiring
5. **Testing:** Full QA cycle required after fix

---

**Report Date:** 2026-02-24
**Reported By:** Agent 10 (QA Engineer)
**Next Action:** Escalate to team lead for assignment
