# Frontend Implementation Plan
# Agent Swarm Monitor - OpenClaw Platform Alignment

**Repository**: agent-swarm-monitor
**Last Updated**: March 2, 2026
**Status**: Phase 4 (Chat Persistence) Prioritized

## Overview

This document provides a sprint-based implementation plan for the **agent-swarm-monitor** frontend to align with the OpenClaw platform architecture. The plan is synchronized with the backend implementation plan and focuses on building UI components that expose OpenClaw features currently missing from the AgentSwarm dashboard.

**Critical Priority**: Epic 1 (Chat History UI) - Users report "everytim I go to tchat with an agent, al the context is gone" - chat persistence is essential for dev workflow.

## Architecture Context

### Current Stack
- **React** - UI framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Utility-first styling
- **React Router** - Client-side routing
- **Axios** - HTTP client
- **WebSocket** - Real-time agent communication

### Backend Integration Points
- **FastAPI Backend** - REST API at `http://localhost:8000`
- **OpenClaw Gateway** - WebSocket at `ws://localhost:18789`
- **ZeroDB** - Cloud storage for chat/memory (via backend proxy)
- **PostgreSQL** - Metadata via backend API

### Missing UI Components (from Gap Analysis)
1. **Chat History** - No conversation persistence
2. **Workspace Files Editor** - 9 .md files (AGENTS.md, SOUL.md, etc.)
3. **Cron Jobs Manager** - Scheduled automation UI
4. **Skills Manager** - Workspace + managed skills
5. **Channel Bindings** - Communication platform routing
6. **Nodes Visualization** - P2P network graph
7. **Config Editor** - Agent configuration UI
8. **Agent Logs Viewer** - OpenClaw agent logs (not backend logs)
9. **Workspace Switcher** - Currently mislabeled as "organization"

---

## Epic 1: Chat History UI (Phase 4 Priority)
**Duration**: 2 weeks (10 working days)
**Dependencies**: Backend Epic 1 (Conversation API endpoints)

### Sprint 1: Workspace Switcher & Conversations API Integration (Days 1-2)

**Goal**: Fix organization → workspace terminology and integrate conversation list API

#### User Stories
1. **Rename Organization to Workspace** (CRITICAL)
   - AS A user
   - I WANT the UI to use "Workspace" terminology instead of "Organization"
   - SO THAT it matches the OpenClaw platform architecture

   **Acceptance Criteria**:
   - [ ] Rename `OrganizationSelector` component to `WorkspaceSelector`
   - [ ] Update all UI text: "Organization" → "Workspace"
   - [ ] Update route paths: `/organizations/:id` → `/workspaces/:id`
   - [ ] Update state management: `selectedOrganization` → `selectedWorkspace`
   - [ ] Ensure backend `/workspaces` API endpoint is integrated
   - [ ] Workspace switcher displays workspace name (not organization)
   - [ ] Switching workspace refreshes agent list and conversation history

2. **Integrate Conversations API**
   - AS A user
   - I WANT to see a list of my past conversations with agents
   - SO THAT I can review chat history

   **Acceptance Criteria**:
   - [ ] Create `ConversationService` API client (axios)
   - [ ] Implement `GET /workspaces/{id}/conversations` endpoint integration
   - [ ] Implement `GET /conversations/{id}` endpoint integration
   - [ ] Create `Conversation` TypeScript interface matching backend schema
   - [ ] Handle loading states and error states
   - [ ] Display conversation metadata (agent name, start time, message count)

#### Tasks
- [ ] Rename `src/components/OrganizationSelector.tsx` → `WorkspaceSelector.tsx`
- [ ] Update `src/contexts/AuthContext.tsx` (organization → workspace)
- [ ] Update `src/pages/Dashboard.tsx` (organization references)
- [ ] Update `src/api/organizationService.ts` → `workspaceService.ts`
- [ ] Create `src/api/conversationService.ts` with methods:
  - `listConversations(workspaceId: string, agentId?: string)`
  - `getConversation(conversationId: string)`
  - `getMessages(conversationId: string, limit?: number, offset?: number)`
- [ ] Create `src/types/conversation.ts` interfaces
- [ ] Write unit tests for `ConversationService`

---

### Sprint 2: Conversation List Component (Days 3-4)

**Goal**: Build conversation history sidebar

#### User Stories
1. **View Conversation List**
   - AS A user
   - I WANT to see a list of my conversations in a sidebar
   - SO THAT I can navigate to specific chat sessions

   **Acceptance Criteria**:
   - [ ] Sidebar shows conversations grouped by agent
   - [ ] Each conversation displays: agent avatar, agent name, last message preview, timestamp
   - [ ] Conversations sorted by most recent first
   - [ ] Active conversation highlighted in sidebar
   - [ ] Click conversation to load full transcript
   - [ ] Empty state when no conversations exist
   - [ ] Skeleton loading state while fetching

2. **Filter and Search Conversations**
   - AS A user
   - I WANT to filter conversations by agent and search by content
   - SO THAT I can quickly find specific chats

   **Acceptance Criteria**:
   - [ ] Dropdown to filter by agent (all agents or specific agent)
   - [ ] Search bar filters conversations by agent name or message content
   - [ ] Search results update in real-time as user types
   - [ ] Clear search button
   - [ ] Shows "No results" message when filter/search returns empty

#### Tasks
- [ ] Create `src/components/Conversations/ConversationList.tsx`
- [ ] Create `src/components/Conversations/ConversationListItem.tsx`
- [ ] Create `src/components/Conversations/ConversationSidebar.tsx`
- [ ] Implement agent filter dropdown
- [ ] Implement search functionality (client-side filtering initially)
- [ ] Add pagination (load more on scroll)
- [ ] Style with Tailwind CSS
- [ ] Write Storybook stories for each component
- [ ] Write unit tests with React Testing Library

---

### Sprint 3: Message Transcript Viewer (Days 5-6)

**Goal**: Display full conversation transcript with user/assistant messages

#### User Stories
1. **View Message Transcript**
   - AS A user
   - I WANT to view the full transcript of a conversation
   - SO THAT I can see the complete chat history with an agent

   **Acceptance Criteria**:
   - [ ] Main panel shows message transcript
   - [ ] User messages aligned right with distinct styling
   - [ ] Assistant messages aligned left with agent avatar
   - [ ] Timestamps displayed for each message
   - [ ] Markdown rendering for assistant responses
   - [ ] Code blocks syntax-highlighted
   - [ ] Auto-scroll to bottom on new message
   - [ ] Scroll to top loads older messages (pagination)

2. **New Message Input**
   - AS A user
   - I WANT to send new messages in an existing conversation
   - SO THAT I can continue chatting with the agent

   **Acceptance Criteria**:
   - [ ] Message input box at bottom of transcript
   - [ ] Multiline support (Shift+Enter for newline, Enter to send)
   - [ ] Send button enabled only when input is non-empty
   - [ ] Loading state while message is being sent
   - [ ] Optimistic UI update (message appears immediately)
   - [ ] Error handling if send fails (retry option)

#### Tasks
- [ ] Create `src/components/Conversations/MessageTranscript.tsx`
- [ ] Create `src/components/Conversations/Message.tsx` (user vs assistant variants)
- [ ] Create `src/components/Conversations/MessageInput.tsx`
- [ ] Integrate `react-markdown` for assistant message rendering
- [ ] Integrate `react-syntax-highlighter` for code blocks
- [ ] Implement infinite scroll pagination (load older messages)
- [ ] Implement `sendMessage()` API call to backend
- [ ] Handle WebSocket updates for real-time new messages
- [ ] Write integration tests with MSW (Mock Service Worker)

---

### Sprint 4: Semantic Search UI (Days 7-8)

**Goal**: Enable semantic search across conversation history using ZeroDB Memory API

#### User Stories
1. **Semantic Search**
   - AS A user
   - I WANT to search my conversation history using natural language
   - SO THAT I can find relevant past discussions without remembering exact keywords

   **Acceptance Criteria**:
   - [ ] Search bar with "Semantic Search" toggle (switch between keyword and semantic)
   - [ ] Semantic search powered by ZeroDB Memory API (`/search_memories`)
   - [ ] Results show conversation excerpts with matched context highlighted
   - [ ] Click result to jump to that conversation and scroll to matched message
   - [ ] Loading state during semantic search (may take 1-2 seconds)
   - [ ] Error handling if ZeroDB unavailable (fallback to keyword search)

2. **Search Results Display**
   - AS A user
   - I WANT to see search results with context
   - SO THAT I can determine relevance before clicking

   **Acceptance Criteria**:
   - [ ] Each result shows: agent name, conversation date, message snippet (200 chars)
   - [ ] Matched terms/phrases highlighted in snippet
   - [ ] Relevance score displayed (from ZeroDB similarity score)
   - [ ] Results sorted by relevance (highest first)
   - [ ] Pagination for large result sets

#### Tasks
- [ ] Create `src/components/Conversations/SemanticSearch.tsx`
- [ ] Create `src/components/Conversations/SearchResults.tsx`
- [ ] Integrate backend `/conversations/search` endpoint (proxies ZeroDB Memory API)
- [ ] Implement keyword vs semantic search toggle
- [ ] Implement result highlighting logic
- [ ] Implement "jump to message" navigation
- [ ] Add debounce to search input (300ms)
- [ ] Write E2E tests with Playwright

---

### Sprint 5: Real-time Message Updates (Days 9-10)

**Goal**: WebSocket integration for live message streaming

#### User Stories
1. **Real-time Message Streaming**
   - AS A user
   - I WANT to see assistant responses stream in real-time
   - SO THAT I get immediate feedback during long-running agent tasks

   **Acceptance Criteria**:
   - [ ] Assistant messages stream token-by-token (like ChatGPT)
   - [ ] Typing indicator while assistant is composing response
   - [ ] Smooth auto-scroll as new tokens arrive
   - [ ] Stop generation button (sends cancel signal to backend)
   - [ ] Reconnect logic if WebSocket connection drops
   - [ ] Offline indicator if connection lost

2. **Multi-tab Synchronization**
   - AS A user
   - I WANT conversations to sync across multiple browser tabs
   - SO THAT I can switch tabs without losing context

   **Acceptance Criteria**:
   - [ ] New messages appear in all open tabs viewing the same conversation
   - [ ] Conversation list updates in all tabs when new conversation started
   - [ ] Uses WebSocket broadcast or localStorage events for cross-tab sync

#### Tasks
- [ ] Create `src/hooks/useWebSocket.ts` custom hook
- [ ] Create `src/hooks/useConversationSync.ts` (WebSocket + localStorage)
- [ ] Implement message streaming UI (typewriter effect)
- [ ] Implement typing indicator component
- [ ] Implement stop generation button
- [ ] Add WebSocket reconnect logic with exponential backoff
- [ ] Add connection status indicator to UI
- [ ] Test cross-tab synchronization
- [ ] Write integration tests for WebSocket flows

---

### Epic 1: Backlog Issues (GitHub Format)

```markdown
### Issue #[FRONTEND-001]: Rename Organization to Workspace Throughout UI
**Epic**: Chat History UI
**Sprint**: 1
**Priority**: CRITICAL
**Estimate**: 3 story points

**Description**:
The UI currently uses "Organization" terminology to switch between workspaces, but the OpenClaw platform uses "Workspace" as the canonical term. This causes confusion and misalignment with the backend API and documentation.

**Acceptance Criteria**:
- [ ] Rename `OrganizationSelector` component to `WorkspaceSelector`
- [ ] Update all UI text: "Organization" → "Workspace"
- [ ] Update route paths: `/organizations/:id` → `/workspaces/:id`
- [ ] Update state management: `selectedOrganization` → `selectedWorkspace`
- [ ] Ensure backend `/workspaces` API endpoint is integrated
- [ ] Workspace switcher displays workspace name correctly
- [ ] Switching workspace refreshes agent list and conversation history

**Technical Notes**:
- Update `src/components/OrganizationSelector.tsx` → `WorkspaceSelector.tsx`
- Update `src/contexts/AuthContext.tsx`
- Update `src/pages/Dashboard.tsx`
- Rename `src/api/organizationService.ts` → `workspaceService.ts`
- Verify backend API endpoint `/workspaces` exists and supports switching
---

### Issue #[FRONTEND-002]: Create ConversationService API Client
**Epic**: Chat History UI
**Sprint**: 1
**Priority**: HIGH
**Estimate**: 5 story points

**Description**:
Create a TypeScript service class to interact with the backend Conversation API endpoints. This service will handle fetching conversation lists, individual conversations, and messages.

**Acceptance Criteria**:
- [ ] Create `src/api/conversationService.ts`
- [ ] Implement methods:
  - `listConversations(workspaceId: string, agentId?: string): Promise<Conversation[]>`
  - `getConversation(conversationId: string): Promise<Conversation>`
  - `getMessages(conversationId: string, limit?: number, offset?: number): Promise<Message[]>`
  - `sendMessage(conversationId: string, content: string): Promise<Message>`
- [ ] Create TypeScript interfaces in `src/types/conversation.ts`
- [ ] Handle authentication (include JWT token in headers)
- [ ] Handle error responses (4xx, 5xx)
- [ ] Write unit tests with Jest and MSW

**Technical Notes**:
- Use axios for HTTP requests
- Base URL: `process.env.REACT_APP_API_URL` (default: `http://localhost:8000`)
- Endpoints:
  - `GET /workspaces/{workspace_id}/conversations`
  - `GET /conversations/{conversation_id}`
  - `GET /conversations/{conversation_id}/messages`
  - `POST /conversations/{conversation_id}/messages`
---

### Issue #[FRONTEND-003]: Build Conversation List Sidebar Component
**Epic**: Chat History UI
**Sprint**: 2
**Priority**: HIGH
**Estimate**: 8 story points

**Description**:
Create a sidebar component that displays a list of conversations grouped by agent, with filtering and search capabilities.

**Acceptance Criteria**:
- [ ] Sidebar shows conversations grouped by agent
- [ ] Each conversation displays: agent avatar, agent name, last message preview, timestamp
- [ ] Conversations sorted by most recent first
- [ ] Active conversation highlighted
- [ ] Click conversation to load full transcript
- [ ] Empty state when no conversations exist
- [ ] Skeleton loading state while fetching
- [ ] Dropdown to filter by agent
- [ ] Search bar filters by agent name or message content
- [ ] Pagination (load more on scroll)

**Technical Notes**:
- Components:
  - `src/components/Conversations/ConversationSidebar.tsx` (container)
  - `src/components/Conversations/ConversationList.tsx` (list logic)
  - `src/components/Conversations/ConversationListItem.tsx` (item rendering)
- Use React Query for data fetching and caching
- Implement infinite scroll with `react-intersection-observer`
- Write Storybook stories for visual testing
---

### Issue #[FRONTEND-004]: Build Message Transcript Viewer
**Epic**: Chat History UI
**Sprint**: 3
**Priority**: HIGH
**Estimate**: 8 story points

**Description**:
Create a message transcript viewer that displays the full conversation history with user and assistant messages, supports markdown rendering, and allows sending new messages.

**Acceptance Criteria**:
- [ ] Main panel shows message transcript
- [ ] User messages aligned right, assistant messages aligned left
- [ ] Timestamps displayed for each message
- [ ] Markdown rendering for assistant responses
- [ ] Code blocks syntax-highlighted
- [ ] Auto-scroll to bottom on new message
- [ ] Scroll to top loads older messages (pagination)
- [ ] Message input box at bottom
- [ ] Multiline support (Shift+Enter for newline)
- [ ] Send button enabled only when input non-empty
- [ ] Loading state while sending message
- [ ] Optimistic UI update

**Technical Notes**:
- Components:
  - `src/components/Conversations/MessageTranscript.tsx`
  - `src/components/Conversations/Message.tsx`
  - `src/components/Conversations/MessageInput.tsx`
- Use `react-markdown` for rendering
- Use `react-syntax-highlighter` for code blocks
- Implement infinite scroll for older messages
- Handle WebSocket updates for real-time messages
---

### Issue #[FRONTEND-005]: Implement Semantic Search UI
**Epic**: Chat History UI
**Sprint**: 4
**Priority**: MEDIUM
**Estimate**: 5 story points

**Description**:
Add semantic search capability using ZeroDB Memory API to enable natural language search across conversation history.

**Acceptance Criteria**:
- [ ] Search bar with "Semantic Search" toggle
- [ ] Semantic search powered by backend `/conversations/search` endpoint
- [ ] Results show conversation excerpts with context highlighted
- [ ] Click result to jump to conversation and scroll to matched message
- [ ] Loading state during semantic search
- [ ] Error handling with fallback to keyword search
- [ ] Results display: agent name, date, snippet, relevance score
- [ ] Results sorted by relevance
- [ ] Pagination for large result sets

**Technical Notes**:
- Components:
  - `src/components/Conversations/SemanticSearch.tsx`
  - `src/components/Conversations/SearchResults.tsx`
- Backend endpoint: `GET /conversations/search?q={query}&semantic=true`
- Debounce search input (300ms)
- Use React Query for caching search results
---

### Issue #[FRONTEND-006]: Implement Real-time Message Streaming
**Epic**: Chat History UI
**Sprint**: 5
**Priority**: HIGH
**Estimate**: 8 story points

**Description**:
Integrate WebSocket for real-time message streaming and cross-tab synchronization.

**Acceptance Criteria**:
- [ ] Assistant messages stream token-by-token
- [ ] Typing indicator while assistant is composing
- [ ] Smooth auto-scroll as tokens arrive
- [ ] Stop generation button
- [ ] Reconnect logic if WebSocket drops
- [ ] Offline indicator if connection lost
- [ ] Multi-tab synchronization (new messages appear in all tabs)
- [ ] Uses WebSocket + localStorage for cross-tab sync

**Technical Notes**:
- Create custom hooks:
  - `src/hooks/useWebSocket.ts`
  - `src/hooks/useConversationSync.ts`
- WebSocket URL: `process.env.REACT_APP_WS_URL` (default: `ws://localhost:18789`)
- Implement exponential backoff for reconnects
- Use localStorage events for cross-tab communication
- Add connection status indicator to header
---

### Issue #[FRONTEND-007]: Write Integration Tests for Chat History
**Epic**: Chat History UI
**Sprint**: 5
**Priority**: MEDIUM
**Estimate**: 5 story points

**Description**:
Write comprehensive integration and E2E tests for chat history UI.

**Acceptance Criteria**:
- [ ] Unit tests for all components (React Testing Library)
- [ ] Integration tests for API service (MSW)
- [ ] E2E tests for complete user flows (Playwright):
  - Load conversations → Select conversation → View messages → Send message
  - Perform semantic search → Click result → Jump to message
  - Real-time message streaming across tabs
- [ ] Test coverage >= 80%

**Technical Notes**:
- Use Mock Service Worker (MSW) for API mocking
- Use Playwright for E2E tests
- Mock WebSocket connections in tests
- Test error states and edge cases
```

---

## Epic 2: Workspace Files Editor (Phase 4.1)
**Duration**: 1.5 weeks (7-8 working days)
**Dependencies**: Backend Epic 3 (Workspace Files API)

### Sprint 6: Workspace Files List & Navigation (Days 1-2)

**Goal**: Build file tree navigation for 9 workspace .md files

#### User Stories
1. **View Workspace Files**
   - AS A user
   - I WANT to see a file tree of my agent's workspace files
   - SO THAT I can navigate to specific configuration files

   **Acceptance Criteria**:
   - [ ] File tree sidebar shows 9 workspace files:
     - AGENTS.md, SOUL.md, USER.md, IDENTITY.md, TOOLS.md, HEARTBEAT.md, BOOT.md, BOOTSTRAP.md, MEMORY.md
   - [ ] Files organized by category (identity, automation, memory)
   - [ ] Active file highlighted
   - [ ] Click file to load content in editor
   - [ ] File status indicators (modified, saved, error)

#### Tasks
- [ ] Create `src/components/WorkspaceFiles/FileTree.tsx`
- [ ] Create `src/components/WorkspaceFiles/FileTreeItem.tsx`
- [ ] Create `src/api/workspaceFileService.ts`
- [ ] Implement `GET /agents/{agent_id}/workspace/files` endpoint integration
- [ ] Create TypeScript interface for `WorkspaceFile`

---

### Sprint 7: Markdown Editor with Preview (Days 3-5)

**Goal**: Build markdown editor with live preview and syntax highlighting

#### User Stories
1. **Edit Workspace File**
   - AS A user
   - I WANT to edit workspace .md files with a rich markdown editor
   - SO THAT I can customize my agent's configuration

   **Acceptance Criteria**:
   - [ ] Monaco Editor for markdown editing
   - [ ] Live preview panel (side-by-side or toggle)
   - [ ] Syntax highlighting for markdown
   - [ ] Auto-save after 2 seconds of inactivity
   - [ ] Save button with manual save
   - [ ] Undo/redo support
   - [ ] Full-screen mode toggle

2. **File Templates**
   - AS A user
   - I WANT to use templates for each workspace file type
   - SO THAT I can quickly scaffold new agent configurations

   **Acceptance Criteria**:
   - [ ] "Reset to Template" button for each file
   - [ ] Templates match OpenClaw default structure
   - [ ] Confirmation modal before resetting (prevent accidental data loss)

#### Tasks
- [ ] Create `src/components/WorkspaceFiles/MarkdownEditor.tsx`
- [ ] Integrate `@monaco-editor/react`
- [ ] Create `src/components/WorkspaceFiles/MarkdownPreview.tsx`
- [ ] Implement auto-save with debounce (2 seconds)
- [ ] Implement `PUT /agents/{agent_id}/workspace/files/{file_name}` endpoint
- [ ] Create default templates in `src/constants/workspaceTemplates.ts`
- [ ] Add full-screen mode with keyboard shortcut (F11)

---

### Sprint 8: Workspace File Validation & Help (Days 6-8)

**Goal**: Add validation and contextual help for workspace files

#### User Stories
1. **Workspace File Validation**
   - AS A user
   - I WANT to see validation errors for workspace files
   - SO THAT I can fix misconfigurations before saving

   **Acceptance Criteria**:
   - [ ] IDENTITY.md validation: requires name, emoji, avatar URL
   - [ ] SOUL.md validation: requires personality description
   - [ ] HEARTBEAT.md validation: checks cron expression if present
   - [ ] Inline error indicators in editor
   - [ ] Error panel listing all validation errors
   - [ ] Save button disabled if validation fails

2. **Contextual Help**
   - AS A user
   - I WANT to see help text for each workspace file
   - SO THAT I understand what each file is for

   **Acceptance Criteria**:
   - [ ] Help panel with description of current file
   - [ ] Example snippets for each file type
   - [ ] Link to OpenClaw documentation for detailed info
   - [ ] Collapsible help panel (can be hidden)

#### Tasks
- [ ] Create validation schemas with Zod for each file type
- [ ] Create `src/components/WorkspaceFiles/ValidationPanel.tsx`
- [ ] Create `src/components/WorkspaceFiles/HelpPanel.tsx`
- [ ] Add inline error markers to Monaco Editor
- [ ] Create help content in `src/constants/workspaceFileHelp.ts`
- [ ] Disable save button when validation fails

---

## Epic 3: Cron Jobs Manager (Phase 4.2)
**Duration**: 1 week (5 working days)
**Dependencies**: Backend Epic 4 (Cron Jobs API)

### Sprint 9: Cron Jobs List & Status (Days 1-2)

**Goal**: Display list of agent cron jobs with status indicators

#### User Stories
1. **View Cron Jobs**
   - AS A user
   - I WANT to see a list of cron jobs configured for my agent
   - SO THAT I can monitor scheduled automations

   **Acceptance Criteria**:
   - [ ] Table shows cron jobs with columns: Name, Schedule, Next Run, Status, Actions
   - [ ] Status indicators: Active, Paused, Failed, Never Run
   - [ ] Next run time displayed in user's local timezone
   - [ ] Enable/disable toggle for each job
   - [ ] Delete job with confirmation modal

#### Tasks
- [ ] Create `src/components/CronJobs/CronJobList.tsx`
- [ ] Create `src/components/CronJobs/CronJobRow.tsx`
- [ ] Create `src/api/cronJobService.ts`
- [ ] Implement `GET /agents/{agent_id}/cron-jobs` endpoint integration
- [ ] Implement `DELETE /agents/{agent_id}/cron-jobs/{job_id}` endpoint
- [ ] Display next run time with `date-fns` for timezone formatting

---

### Sprint 10: Cron Expression Builder (Days 3-4)

**Goal**: Build visual cron expression editor

#### User Stories
1. **Create/Edit Cron Job**
   - AS A user
   - I WANT to create cron jobs using a visual editor
   - SO THAT I don't need to manually write cron expressions

   **Acceptance Criteria**:
   - [ ] Modal form for creating/editing cron jobs
   - [ ] Fields: Name, Cron Expression, Timezone, Session Type, Model, Delivery
   - [ ] Visual cron builder with dropdowns (minute, hour, day, month, weekday)
   - [ ] "Custom" mode for manual cron expression entry
   - [ ] Cron expression preview in plain English (e.g., "Every day at 7:00 AM EST")
   - [ ] Validation for cron expression syntax
   - [ ] One-shot scheduling option (--at "20m" style)

#### Tasks
- [ ] Create `src/components/CronJobs/CronJobModal.tsx`
- [ ] Create `src/components/CronJobs/CronExpressionBuilder.tsx`
- [ ] Integrate `react-cron-generator` or build custom cron UI
- [ ] Create cron expression parser/validator
- [ ] Implement human-readable cron description
- [ ] Implement `POST /agents/{agent_id}/cron-jobs` endpoint
- [ ] Implement `PUT /agents/{agent_id}/cron-jobs/{job_id}` endpoint

---

### Sprint 11: Cron Job Logs & Execution History (Day 5)

**Goal**: Display execution history and logs for cron jobs

#### User Stories
1. **View Cron Job Logs**
   - AS A user
   - I WANT to see execution history for cron jobs
   - SO THAT I can debug failures and verify successful runs

   **Acceptance Criteria**:
   - [ ] Execution history table: Timestamp, Status, Duration, Output Preview
   - [ ] Click row to expand full output/error message
   - [ ] Filter by status (success, failed, all)
   - [ ] Pagination for large execution history
   - [ ] "Run Now" button to trigger manual execution

#### Tasks
- [ ] Create `src/components/CronJobs/CronJobLogs.tsx`
- [ ] Implement `GET /agents/{agent_id}/cron-jobs/{job_id}/executions` endpoint
- [ ] Implement `POST /agents/{agent_id}/cron-jobs/{job_id}/trigger` endpoint
- [ ] Add expandable rows to table for full log details
- [ ] Add status filter dropdown

---

## Epic 4: Additional Features UI (Phase 4.3)
**Duration**: 2 weeks (10 working days)
**Dependencies**: Backend Epics 2, 5

### Sprint 12: Skills Manager (Days 1-3)

**Goal**: UI for managing workspace and managed skills

#### User Stories
1. **View and Install Skills**
   - AS A user
   - I WANT to browse available skills and install them to my agent
   - SO THAT I can extend my agent's capabilities

   **Acceptance Criteria**:
   - [ ] Skills marketplace tab with searchable skill list
   - [ ] Each skill card shows: name, description, author, install count
   - [ ] Filter by category (workspace, managed, system)
   - [ ] "Install" button for uninstalled skills
   - [ ] Installed skills tab with "Uninstall" button
   - [ ] Skill details modal with full README

#### Tasks
- [ ] Create `src/components/Skills/SkillsManager.tsx`
- [ ] Create `src/components/Skills/SkillCard.tsx`
- [ ] Create `src/api/skillService.ts`
- [ ] Implement `GET /skills/marketplace` endpoint
- [ ] Implement `GET /agents/{agent_id}/skills` endpoint
- [ ] Implement `POST /agents/{agent_id}/skills/{skill_id}/install` endpoint
- [ ] Implement `DELETE /agents/{agent_id}/skills/{skill_id}` endpoint

---

### Sprint 13: Channel Bindings Editor (Days 4-5)

**Goal**: UI for managing agent channel bindings

#### User Stories
1. **Configure Channel Bindings**
   - AS A user
   - I WANT to bind my agent to different communication channels
   - SO THAT I can route messages from WhatsApp, Telegram, etc. to specific agents

   **Acceptance Criteria**:
   - [ ] Table shows bindings: Agent, Channel, Binding Key
   - [ ] Supported channels: WhatsApp, Telegram, Discord, Slack
   - [ ] "Add Binding" button opens modal with channel dropdown and key input
   - [ ] "Delete Binding" with confirmation
   - [ ] Visual indicator if channel is active/inactive

#### Tasks
- [ ] Create `src/components/Channels/ChannelBindings.tsx`
- [ ] Create `src/components/Channels/AddBindingModal.tsx`
- [ ] Create `src/api/channelService.ts`
- [ ] Implement `GET /agents/{agent_id}/channels` endpoint
- [ ] Implement `POST /agents/{agent_id}/channels` endpoint
- [ ] Implement `DELETE /agents/{agent_id}/channels/{channel_id}` endpoint

---

### Sprint 14: Nodes Visualization (Days 6-8)

**Goal**: D3.js graph visualization of P2P network

#### User Stories
1. **View P2P Network Topology**
   - AS A user
   - I WANT to see a graph visualization of the P2P network
   - SO THAT I can understand which agents are connected to which nodes

   **Acceptance Criteria**:
   - [ ] Force-directed graph with nodes (agents/hardware) and edges (connections)
   - [ ] Node color indicates status (online, offline, degraded)
   - [ ] Edge thickness indicates connection quality (latency/bandwidth)
   - [ ] Click node to show details (peer ID, IP, capabilities)
   - [ ] Zoom and pan controls
   - [ ] Real-time updates via WebSocket
   - [ ] Legend explaining colors and symbols

#### Tasks
- [ ] Create `src/components/Network/NodesVisualization.tsx`
- [ ] Integrate D3.js for force-directed graph
- [ ] Create `src/api/networkService.ts`
- [ ] Implement `GET /network/topology` endpoint integration
- [ ] Implement WebSocket subscription to network events
- [ ] Add zoom/pan controls with `d3-zoom`
- [ ] Create node detail panel

---

### Sprint 15: Config Editor & Agent Logs (Days 9-10)

**Goal**: Configuration editor and OpenClaw agent log viewer

#### User Stories
1. **Edit Agent Configuration**
   - AS A user
   - I WANT to edit agent configuration (model, persona, heartbeat interval)
   - SO THAT I can customize agent behavior

   **Acceptance Criteria**:
   - [ ] Config form with fields: Name, Persona, Model, Heartbeat Enabled, Heartbeat Interval
   - [ ] Model dropdown (sonnet, opus, haiku)
   - [ ] Heartbeat interval dropdown (30min, 1h, 4h, 8h, 24h)
   - [ ] Persona textarea with markdown preview
   - [ ] Save button with validation

2. **View OpenClaw Agent Logs**
   - AS A user
   - I WANT to see OpenClaw agent logs (not backend logs)
   - SO THAT I can debug agent behavior

   **Acceptance Criteria**:
   - [ ] Log viewer with timestamp, log level, message
   - [ ] Filter by log level (debug, info, warn, error)
   - [ ] Search logs by message content
   - [ ] Auto-refresh toggle for real-time logs
   - [ ] Download logs as .txt file

#### Tasks
- [ ] Create `src/components/Config/AgentConfigEditor.tsx`
- [ ] Update `PUT /agents/{agent_id}` endpoint integration
- [ ] Create `src/components/Logs/AgentLogsViewer.tsx`
- [ ] Implement `GET /agents/{agent_id}/logs` endpoint integration
- [ ] Add log level filter dropdown
- [ ] Add search functionality
- [ ] Add auto-refresh with interval (5 seconds)
- [ ] Implement log download as .txt

---

## Testing & Quality Assurance

### Testing Strategy
1. **Unit Tests** (Jest + React Testing Library)
   - All components have >= 80% coverage
   - Test user interactions (click, type, submit)
   - Test edge cases and error states

2. **Integration Tests** (MSW + React Testing Library)
   - Test API service integration
   - Mock backend responses
   - Test loading/error states

3. **E2E Tests** (Playwright)
   - Critical user flows:
     - Login → Switch workspace → View conversations → Send message
     - Create agent → Edit workspace files → Save
     - Configure cron job → View execution logs
   - Cross-browser testing (Chrome, Firefox, Safari)

4. **Visual Regression Tests** (Storybook + Chromatic)
   - All components have Storybook stories
   - Automated visual diff testing on PRs

### Accessibility (WCAG 2.1 AA)
- [ ] All interactive elements keyboard accessible
- [ ] Focus indicators visible
- [ ] ARIA labels for icon-only buttons
- [ ] Screen reader tested with NVDA/VoiceOver
- [ ] Color contrast ratio >= 4.5:1

---

## Deployment & CI/CD

### Build Process
```bash
npm run build    # Production build with Vite
npm run preview  # Preview production build locally
```

### Environment Variables
```
REACT_APP_API_URL=http://localhost:8000          # Backend API URL
REACT_APP_WS_URL=ws://localhost:18789            # Gateway WebSocket URL
REACT_APP_ZERODB_PROJECT_ID=<project_id>         # ZeroDB project (via backend proxy)
REACT_APP_SENTRY_DSN=<sentry_dsn>                # Error tracking
REACT_APP_ENV=production|staging|development
```

### CI/CD Pipeline (GitHub Actions)
1. **PR Checks**:
   - Lint (ESLint + Prettier)
   - Type check (TypeScript)
   - Unit tests
   - Build verification

2. **Main Branch**:
   - All PR checks
   - E2E tests
   - Build and deploy to Vercel/Netlify

---

## Migration Plan

### Rename Organization → Workspace (CRITICAL)

**Files to Update**:
```
src/components/
  ├── OrganizationSelector.tsx → WorkspaceSelector.tsx
src/contexts/
  ├── AuthContext.tsx (state: selectedOrganization → selectedWorkspace)
src/pages/
  ├── Dashboard.tsx (props, text references)
src/api/
  ├── organizationService.ts → workspaceService.ts
src/types/
  ├── organization.ts → workspace.ts
src/routes/
  ├── AppRoutes.tsx (paths: /organizations/:id → /workspaces/:id)
```

**Backend API Verification**:
- [ ] Confirm `GET /workspaces` endpoint exists
- [ ] Confirm `GET /workspaces/{workspace_id}` endpoint exists
- [ ] Confirm `GET /workspaces/{workspace_id}/agents` endpoint exists
- [ ] Update API client base paths

**Migration Script**:
```bash
# Automated file rename and find-replace
./scripts/migrate-org-to-workspace.sh
```

---

## Dependencies & Blockers

### Backend Dependencies
- **Epic 1** requires Backend Epic 1 (Conversation API endpoints)
- **Epic 2** requires Backend Epic 3 (Workspace Files API)
- **Epic 3** requires Backend Epic 4 (Cron Jobs API)
- **Epic 4** requires Backend Epic 2 (Agent-Hardware Link) + Epic 5 (Skills & Channels)

### External Dependencies
- **ZeroDB Access**: Requires ZeroDB project provisioned and API key configured
- **WebSocket Gateway**: Requires OpenClaw Gateway running at `ws://localhost:18789`
- **P2P Network**: Requires WireGuard VPN and libp2p bootstrap node for Nodes Visualization

---

## Success Metrics

### Key Performance Indicators (KPIs)
1. **Chat History**:
   - [ ] 100% of conversations persisted across sessions
   - [ ] Semantic search returns relevant results (>80% user satisfaction)
   - [ ] Message load time < 500ms for 100 messages

2. **Workspace Files**:
   - [ ] Users can edit and save all 9 workspace files without errors
   - [ ] Auto-save success rate > 99%
   - [ ] Validation catches 100% of critical errors before save

3. **Cron Jobs**:
   - [ ] Users can create cron jobs without needing cron syntax knowledge
   - [ ] Cron expression builder accuracy 100%
   - [ ] Job execution logs available within 5 seconds of completion

4. **Overall**:
   - [ ] Page load time < 2 seconds
   - [ ] 95th percentile API response time < 1 second
   - [ ] Zero critical accessibility violations (aXe scan)

---

## Risk Mitigation

### Identified Risks
1. **Backend API Delays**: Frontend sprints depend on corresponding backend endpoints
   - **Mitigation**: Use MSW to mock backend APIs and develop UI independently
   - **Mitigation**: Define API contracts upfront with OpenAPI spec

2. **ZeroDB Integration Complexity**: Semantic search may have latency/reliability issues
   - **Mitigation**: Fallback to keyword search if ZeroDB unavailable
   - **Mitigation**: Implement client-side caching with React Query

3. **WebSocket Connection Stability**: Real-time features may fail in unreliable networks
   - **Mitigation**: Implement reconnect logic with exponential backoff
   - **Mitigation**: Show offline indicator and queue messages locally

4. **Scope Creep**: Too many features in one sprint
   - **Mitigation**: Strict sprint boundaries, defer non-critical features to backlog

---

## Appendix: Component Hierarchy

### Chat History (Epic 1)
```
ConversationPage
├── WorkspaceSelector (renamed from OrganizationSelector)
├── ConversationSidebar
│   ├── ConversationList
│   │   └── ConversationListItem (x N)
│   ├── AgentFilter (dropdown)
│   └── SearchBar
├── MessageTranscript
│   ├── Message (x N)
│   │   ├── UserMessage
│   │   └── AssistantMessage
│   └── MessageInput
└── SemanticSearch
    └── SearchResults

```

### Workspace Files (Epic 2)
```
WorkspaceFilesPage
├── FileTree
│   └── FileTreeItem (x 9)
├── MarkdownEditor (Monaco)
├── MarkdownPreview
├── ValidationPanel
└── HelpPanel
```

### Cron Jobs (Epic 3)
```
CronJobsPage
├── CronJobList
│   └── CronJobRow (x N)
├── CronJobModal
│   └── CronExpressionBuilder
└── CronJobLogs
```

### Additional Features (Epic 4)
```
SkillsPage
├── SkillsMarketplace
│   └── SkillCard (x N)
└── InstalledSkills

ChannelsPage
└── ChannelBindings
    └── AddBindingModal

NetworkPage
└── NodesVisualization (D3.js)

ConfigPage
├── AgentConfigEditor
└── AgentLogsViewer
```

---

## Next Steps

1. **Sprint 1 Kickoff** (Organization → Workspace Rename)
   - Create feature branch: `feature/workspace-rename`
   - Update all files per migration plan
   - Verify backend API integration
   - Submit PR with comprehensive tests

2. **Set Up Development Environment**
   - Clone frontend repo: `git clone <agent-swarm-monitor-repo-url>`
   - Install dependencies: `npm install`
   - Configure `.env.local` with backend URLs
   - Start dev server: `npm run dev`

3. **Coordinate with Backend Team**
   - Sync sprint schedules (backend Epic 1 starts simultaneously)
   - Define API contracts (Swagger/OpenAPI)
   - Set up shared MSW mocks for consistent development

4. **Create GitHub Project Board**
   - Create backlog issues from this document
   - Organize into sprints
   - Assign story points and priorities

---

**End of Frontend Implementation Plan**
