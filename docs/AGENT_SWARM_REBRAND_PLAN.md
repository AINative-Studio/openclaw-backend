# Agent Swarm Rebranding Plan
## OpenClaw → Agent Swarm by AINative Studio

**Status**: Planning Phase
**Timeline**: 6 weeks
**Scope**: Branding only (no ZeroDB integration)
**Date**: March 4, 2026

---

## Executive Summary

This plan outlines the systematic rebranding of **OpenClaw** to **Agent Swarm**, focusing exclusively on brand identity, visual assets, naming, and documentation. Technical features and integrations (e.g., ZeroDB) are explicitly excluded from this scope.

### Key Changes

| Element | From | To |
|---------|------|-----|
| **Name** | OpenClaw | Agent Swarm |
| **CLI Binary** | `openclaw` | `agentswarm` |
| **Logo** | 🦞 Lobster | 🐝 Bee |
| **Positioning** | Personal AI assistant | Multi-agent orchestration platform |
| **Package** | `openclaw@npm` | `agentswarm@npm` (future) |

---

## Source Code Locations

### Primary Target: openclaw-source

```
/Users/aideveloper/openclaw-source/
├── 21,047 lines of TypeScript CLI code
├── 146 CLI module files
├── 9,768 "openclaw" references across 1,610 files
└── Complete CLI, banner, taglines, documentation
```

**Action**: This is where 95% of rebranding work happens.

### Secondary Target: openclaw-gateway

```
/Users/aideveloper/openclaw-backend/openclaw-gateway/
├── 300 lines (server.ts + workflows)
├── 19 "openclaw" references
└── WebSocket gateway server
```

**Action**: Minimal changes (naming only).

### Tertiary Target: openclaw-backend

```
/Users/aideveloper/openclaw-backend/backend/
├── Python backend services
├── Already documented in CLAUDE.md
└── API endpoints, orchestration
```

**Action**: Update service names, comments, documentation.

---

## Phase Breakdown (6 Weeks)

### Week 1-2: Core Infrastructure Rename

**Goal**: Change all internal naming without breaking functionality.

#### Tasks

**1.1 Package & Build Configuration**
- [ ] Rename `openclaw.mjs` → `agentswarm.mjs`
- [ ] Update `package.json`:
  ```json
  {
    "name": "agentswarm",
    "bin": {
      "agentswarm": "agentswarm.mjs"
    },
    "repository": "git+https://github.com/ainativestudio/agent-swarm.git",
    "homepage": "https://github.com/ainativestudio/agent-swarm",
    "keywords": ["agent", "swarm", "multi-agent", "ai", "orchestration"]
  }
  ```
- [ ] Update `pnpm-workspace.yaml`, `tsconfig.json`
- [ ] Update all build scripts in `scripts/` directory

**1.2 CLI Core Branding**
- [ ] `src/cli/cli-name.ts`:
  ```typescript
  export const DEFAULT_CLI_NAME = "agentswarm";
  const CLI_PREFIX_RE = /^(?:((?:pnpm|npm|bunx|npx)\s+))?(agentswarm)\b/;
  ```
- [ ] `src/cli/banner.ts`:
  - Replace `LOBSTER_ASCII` with `BEE_ASCII` (see ASCII Art section below)
  - Update title: `"🦞 OpenClaw"` → `"🐝 Agent Swarm"`
  - Update prefix: `"🦞 "` → `"🐝 "`
- [ ] `src/cli/tagline.ts`:
  - Update `DEFAULT_TAGLINE`: `"All your chats, one OpenClaw."` → `"Where AI agents work together like a swarm."`
  - Update relevant taglines (preserve humor/personality)

**1.3 Configuration & State Paths**
- [ ] Default paths: `~/.openclaw/` → `~/.agentswarm/`
- [ ] Environment variables: `OPENCLAW_*` → `AGENTSWARM_*`
- [ ] URL schemes: `openclaw://` → `agentswarm://`

**Automation Script**:
```bash
#!/bin/bash
# bulk-rename.sh - Automated find/replace

cd /Users/aideveloper/openclaw-source

# Create backup branch
git checkout -b rebrand-backup
git checkout -b rebrand-agentswarm

# Lowercase (openclaw → agentswarm)
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.json" -o -name "*.md" \) \
  -not -path "./node_modules/*" \
  -not -path "./.git/*" \
  -exec sed -i '' 's/openclaw/agentswarm/g' {} +

# TitleCase (OpenClaw → AgentSwarm)
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.json" -o -name "*.md" \) \
  -not -path "./node_modules/*" \
  -not -path "./.git/*" \
  -exec sed -i '' 's/OpenClaw/AgentSwarm/g' {} +

# UPPERCASE (OPENCLAW → AGENTSWARM)
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.json" -o -name "*.md" \) \
  -not -path "./node_modules/*" \
  -not -path "./.git/*" \
  -exec sed -i '' 's/OPENCLAW/AGENTSWARM/g' {} +

# Emoji replacement (🦞 → 🐝)
find . -type f \( -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.md" \) \
  -not -path "./node_modules/*" \
  -not -path "./.git/*" \
  -exec sed -i '' 's/🦞/🐝/g' {} +

echo "✓ Bulk rename complete. Review changes with: git diff"
```

**Manual Review Required**:
- User-facing strings (preserve original capitalization if contextual)
- URLs (update to new GitHub org)
- File paths that reference old structure
- Comments that explain "openclaw" as historical context

---

### Week 2: Visual Assets & Logo Design

**Goal**: Replace all lobster branding with bee branding.

#### Logo Deliverables

**2.1 Pixel Bee SVG** ✅ **DONE**
- Location: `/Users/aideveloper/openclaw-source/docs/assets/pixel-bee.svg`
- Style: 16×16 pixel grid, amber/golden palette
- Already created with proper styling

**2.2 PNG Logo Variants**
Generate from pixel-bee.svg using design tool or script:

```bash
# Using ImageMagick or similar
# Install: brew install imagemagick

# Generate high-res versions
convert docs/assets/pixel-bee.svg -resize 512x512 docs/assets/agentswarm-icon-512.png
convert docs/assets/pixel-bee.svg -resize 256x256 docs/assets/agentswarm-icon-256.png
convert docs/assets/pixel-bee.svg -resize 128x128 docs/assets/agentswarm-icon-128.png
convert docs/assets/pixel-bee.svg -resize 64x64 docs/assets/agentswarm-icon-64.png
convert docs/assets/pixel-bee.svg -resize 48x48 docs/assets/agentswarm-icon-48.png
convert docs/assets/pixel-bee.svg -resize 32x32 docs/assets/agentswarm-icon-32.png
convert docs/assets/pixel-bee.svg -resize 16x16 docs/assets/agentswarm-icon-16.png
```

**2.3 Text + Icon Logos**
Create composite logos (text "Agent Swarm" + bee icon):
- `agentswarm-logo-text.png` (light mode, ~500px width)
- `agentswarm-logo-text-dark.png` (dark mode)

**Design Spec**:
- Font: Bold sans-serif (Inter, SF Pro, Helvetica Neue)
- Layout: Bee icon on left, "Agent Swarm" text on right
- Color: Amber (#FFA500) bee, dark gray (#1a1a1a) text
- Vertical alignment: Center-aligned

**2.4 Chrome Extension Icons**
- [ ] Replace `assets/chrome-extension/icons/icon16.png`
- [ ] Replace `assets/chrome-extension/icons/icon32.png`
- [ ] Replace `assets/chrome-extension/icons/icon48.png`
- [ ] Replace `assets/chrome-extension/icons/icon128.png`
- [ ] Update `assets/chrome-extension/manifest.json` (name, description)

**2.5 Other Assets**
- [ ] Replace `assets/dmg-background.png` (macOS installer)
- [ ] Replace `assets/dmg-background-small.png`
- [ ] Create `assets/agentswarm-social-card.png` (1200×630 for GitHub/social)

---

### Week 3: ASCII Art & Terminal Banner

**Goal**: Create bee ASCII art for terminal display.

#### Bee ASCII Art Design

**Option 1: Compact Bee (5 lines)**
```
     ▄██▄        🐝 AGENT SWARM 🐝
    ███████      by AINative Studio
   █▀█████▀█
   ▀███████▀     Multi-agent orchestration
    ▀▀▀▀▀▀▀
```

**Option 2: Detailed Bee (7 lines, recommended)**
```
▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄
       ▄▀▀▄     ▄▀▀▄       🐝 AGENT SWARM 🐝
     ▄███████████████▄           by AINative Studio
    ███▀▀███████▀▀███
    ███░░███████░░███    Multi-agent orchestration
     ▀▀███████████▀▀     Where agents work together
       ▀▀▀▀▀▀▀▀▀
▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
```

**Option 3: Minimal Bee (3 lines)**
```
    ▄█████▄      🐝 Agent Swarm 🐝
   █▀█████▀█     Multi-agent platform by AINative
    ▀▀▀▀▀▀▀
```

**Implementation**:
```typescript
// src/cli/banner.ts (lines 68-76)
const BEE_ASCII = [
  "▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄",
  "       ▄▀▀▄     ▄▀▀▄       🐝 AGENT SWARM 🐝",
  "     ▄███████████████▄           by AINative Studio",
  "    ███▀▀███████▀▀███",
  "    ███░░███████░░███    Multi-agent orchestration",
  "     ▀▀███████████▀▀     Where agents work together",
  "       ▀▀▀▀▀▀▀▀▀",
  "▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀",
  " ",
];

// Update colorChar function
const colorChar = (ch: string) => {
  if (ch === "█" || ch === "▄" || ch === "▀") {
    return theme.accentBright(ch); // Amber/golden
  }
  if (ch === "░") {
    return theme.accentDim(ch);
  }
  return theme.muted(ch);
};

// Update text coloring
if (line.includes("AGENT SWARM")) {
  return (
    theme.muted("       ▄▀▀▄     ▄▀▀▄       ") +
    theme.accent("🐝") +
    theme.info(" AGENT SWARM ") +
    theme.accent("🐝")
  );
}
```

**Testing**:
```bash
# Test banner in different terminal widths
agentswarm --help
# Expected: Bee banner displays correctly in 80, 120, 160 column terminals
```

---

### Week 4: Documentation Update

**Goal**: Update all documentation with new branding.

#### Documentation Files (Priority Order)

**4.1 Core Documentation** (High Priority)
- [ ] `README.md` (146 mentions, logo references)
  - Replace logo URLs
  - Update all command examples
  - Update GitHub links
  - Update website URLs
- [ ] `CLAUDE.md` / `AGENTS.md` (symlink)
- [ ] `CHANGELOG.md`
- [ ] `VISION.md`
- [ ] `CONTRIBUTING.md`
- [ ] `SECURITY.md`

**4.2 Documentation Directory** (46+ files)
```bash
# Bulk update docs/
cd /Users/aideveloper/openclaw-source/docs
find . -type f -name "*.md" -o -name "*.mdx" | while read file; do
  sed -i '' 's/openclaw/agentswarm/g' "$file"
  sed -i '' 's/OpenClaw/AgentSwarm/g' "$file"
  sed -i '' 's/OPENCLAW/AGENTSWARM/g' "$file"
  sed -i '' 's/🦞/🐝/g' "$file"
done
```

**4.3 URL Migration**
- GitHub: `github.com/openclaw/openclaw` → `github.com/ainativestudio/agent-swarm`
- Website: `openclaw.ai` → `agentswarm.ai` (or maintain openclaw.ai with redirect)
- Docs: `docs.openclaw.ai` → `docs.agentswarm.ai`

**4.4 Badge Updates**
```markdown
<!-- Old -->
![CI](https://img.shields.io/github/actions/workflow/status/openclaw/openclaw/ci.yml)
![Release](https://img.shields.io/github/v/release/openclaw/openclaw)

<!-- New -->
![CI](https://img.shields.io/github/actions/workflow/status/ainativestudio/agent-swarm/ci.yml)
![Release](https://img.shields.io/github/v/release/ainativestudio/agent-swarm)
```

---

### Week 5: Gateway & Backend Services

**Goal**: Update gateway and backend naming.

#### 5.1 OpenClaw Gateway Rebrand

**Location**: `/Users/aideveloper/openclaw-backend/openclaw-gateway/`

**Changes**:
```json
// package.json
{
  "name": "agentswarm-gateway",
  "description": "DBOS-powered durable workflow gateway for Agent Swarm orchestration"
}
```

```typescript
// src/server.ts (19 references)
/**
 * Agent Swarm Gateway Server
 *
 * WebSocket gateway with DBOS durable workflows for agent orchestration.
 */

app.get('/', (req, res) => {
  res.json({
    service: 'Agent Swarm Gateway',
    version: '1.0.0',
    description: 'DBOS-powered durable workflow gateway',
    // ...
  });
});

console.log('Starting Agent Swarm Gateway with DBOS...');
```

**Automation**:
```bash
cd /Users/aideveloper/openclaw-backend/openclaw-gateway
find . -type f \( -name "*.ts" -o -name "*.js" -o -name "*.json" \) \
  -not -path "./node_modules/*" \
  -exec sed -i '' 's/OpenClaw/AgentSwarm/g' {} +
```

#### 5.2 Backend Services Rebrand

**Location**: `/Users/aideveloper/openclaw-backend/backend/`

**Changes**:
- Update `CLAUDE.md` → `AGENT_SWARM.md` (or keep CLAUDE.md as-is for historical reference)
- Update service names in API endpoints comments
- Update Python module docstrings
- Update environment variable names (optional, can maintain backward compatibility)

**Example**:
```python
# backend/main.py
"""
Agent Swarm Backend

Backend infrastructure for AgentClaw — an autonomous multi-agent development
platform by AINative Studio.
"""

# Update OpenClaw references
OPENCLAW_GATEWAY_URL → AGENTSWARM_GATEWAY_URL  # Or keep for compat
```

**Backward Compatibility**:
```python
# Support both old and new env vars
GATEWAY_URL = os.getenv('AGENTSWARM_GATEWAY_URL') or os.getenv('OPENCLAW_GATEWAY_URL')
```

---

### Week 6: Testing, Migration Tools & Rollout Preparation

**Goal**: Ensure everything works, provide migration path.

#### 6.1 Functional Testing

**Test Matrix**:
- [ ] CLI commands work: `agentswarm --help`, `agentswarm agent`, etc.
- [ ] Banner displays correctly (80, 120, 160 columns)
- [ ] Configuration paths work: `~/.agentswarm/`
- [ ] Gateway starts and responds
- [ ] Backend services connect to gateway
- [ ] All documentation links valid (no 404s)

**Test Script**:
```bash
#!/bin/bash
# test-rebrand.sh

echo "Testing Agent Swarm rebrand..."

# Build from source
cd /Users/aideveloper/openclaw-source
pnpm install
pnpm build

# Test CLI
./agentswarm.mjs --version
./agentswarm.mjs --help
./agentswarm.mjs doctor

# Test gateway
cd /Users/aideveloper/openclaw-backend/openclaw-gateway
npm run build
npm start &
GATEWAY_PID=$!
sleep 3
curl http://localhost:8080/health
kill $GATEWAY_PID

echo "✓ Tests complete"
```

#### 6.2 Migration Tools

**For Existing OpenClaw Users**:

Create migration script: `scripts/migrate-from-openclaw.sh`

```bash
#!/bin/bash
# migrate-from-openclaw.sh
# Migrates OpenClaw config to Agent Swarm

set -e

echo "🐝 Agent Swarm Migration Tool"
echo "================================"

OLD_DIR="$HOME/.openclaw"
NEW_DIR="$HOME/.agentswarm"

if [ ! -d "$OLD_DIR" ]; then
  echo "✓ No OpenClaw config found. You're all set!"
  exit 0
fi

if [ -d "$NEW_DIR" ]; then
  echo "⚠️  Agent Swarm config already exists at $NEW_DIR"
  read -p "Overwrite? (y/N) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
  rm -rf "$NEW_DIR"
fi

echo "Copying config from $OLD_DIR to $NEW_DIR..."
cp -R "$OLD_DIR" "$NEW_DIR"

# Update config files
if [ -f "$NEW_DIR/config.json" ]; then
  sed -i '' 's/openclaw/agentswarm/g' "$NEW_DIR/config.json"
fi

# Update daemon service files
if [ -f "$HOME/Library/LaunchAgents/ai.openclaw.gateway.plist" ]; then
  echo "Updating macOS LaunchAgent..."
  launchctl unload "$HOME/Library/LaunchAgents/ai.openclaw.gateway.plist" 2>/dev/null || true
  sed 's/openclaw/agentswarm/g' "$HOME/Library/LaunchAgents/ai.openclaw.gateway.plist" > "$HOME/Library/LaunchAgents/ai.agentswarm.gateway.plist"
  launchctl load "$HOME/Library/LaunchAgents/ai.agentswarm.gateway.plist"
fi

# Backup old directory
echo "Backing up old config to $OLD_DIR.backup..."
mv "$OLD_DIR" "$OLD_DIR.backup"

echo "✓ Migration complete!"
echo ""
echo "Old config preserved at: $OLD_DIR.backup"
echo "New config location: $NEW_DIR"
echo ""
echo "Run 'agentswarm doctor' to verify setup."
```

**Add to CLI**:
```typescript
// src/cli/program/register.maintenance.ts
program
  .command('migrate-from-openclaw')
  .description('Migrate OpenClaw config to Agent Swarm')
  .action(async () => {
    execSync('bash scripts/migrate-from-openclaw.sh', { stdio: 'inherit' });
  });
```

#### 6.3 Deprecation Plan

**For NPM Package** (when published):

```json
// Old package: openclaw@npm
{
  "deprecated": "This package has been renamed to 'agentswarm'. Please install 'agentswarm' instead: npm install -g agentswarm"
}
```

**CLI Alias** (optional, for backward compat):
```bash
# During transition period, create symlink:
ln -s /usr/local/bin/agentswarm /usr/local/bin/openclaw

# With deprecation warning on first use
```

---

## File Checklist

### Critical Files (Must Change)

- [x] `/Users/aideveloper/openclaw-source/package.json`
- [x] `/Users/aideveloper/openclaw-source/openclaw.mjs` → `agentswarm.mjs`
- [x] `/Users/aideveloper/openclaw-source/src/cli/cli-name.ts`
- [x] `/Users/aideveloper/openclaw-source/src/cli/banner.ts`
- [x] `/Users/aideveloper/openclaw-source/src/cli/tagline.ts`
- [x] `/Users/aideveloper/openclaw-source/README.md`
- [x] `/Users/aideveloper/openclaw-source/docs/assets/pixel-bee.svg` (created)

### Gateway Files

- [ ] `/Users/aideveloper/openclaw-backend/openclaw-gateway/package.json`
- [ ] `/Users/aideveloper/openclaw-backend/openclaw-gateway/src/server.ts`

### Backend Files

- [ ] `/Users/aideveloper/openclaw-backend/CLAUDE.md` (optional)
- [ ] Python service docstrings

---

## NPM Publishing Timeline

### Internal Development (Weeks 1-6)
**No NPM needed!** Work directly in source:
```bash
cd /Users/aideveloper/openclaw-source
pnpm install
pnpm build
node dist/entry.js  # or ./agentswarm.mjs
```

### Internal Testing (Week 7)
Still no NPM. Run from source:
```bash
# Team members test by cloning repo
git clone https://github.com/ainativestudio/agent-swarm.git
cd agent-swarm
pnpm install && pnpm build
./agentswarm.mjs --help
```

### External Distribution (Week 8+)
**NOW publish to NPM**:
```bash
# Update version
npm version 1.0.0

# Publish
npm login  # AINative account
npm publish --access public

# Users can now:
npm install -g agentswarm
agentswarm --help
```

**Deprecate Old Package**:
```bash
npm deprecate openclaw@* "Renamed to 'agentswarm'. Install with: npm install -g agentswarm"
```

---

## Risk Mitigation

### Breaking Changes

| Risk | Mitigation |
|------|------------|
| **CLI command change** | Provide symlink `openclaw` → `agentswarm` for 6 months |
| **Config path change** | Auto-migration script detects `~/.openclaw/`, copies to `~/.agentswarm/` |
| **GitHub repo change** | GitHub org redirect, archive old repo with notice |
| **URL scheme change** | Support both `openclaw://` and `agentswarm://` for 6 months |

### Rollback Plan

```bash
# Emergency rollback
git checkout rebrand-backup
pnpm build
# Old "openclaw" CLI works immediately
```

---

## Communication Plan

### Pre-Launch (Week 5-6)

1. **Blog Post** (draft): "Why We're Becoming Agent Swarm"
   - Explain multi-agent focus
   - Highlight new bee branding
   - Show migration path
2. **Discord Announcement**: 2 weeks notice, Q&A session
3. **GitHub Issue**: Community feedback thread

### Launch Day (Week 8)

1. **GitHub Release**: v1.0.0 "Agent Swarm"
2. **Social Media**: Twitter, LinkedIn (coordinated)
3. **Documentation Site**: Update openclaw.ai → redirect to agentswarm.ai
4. **Discord**: Announcement + support channel

### Post-Launch (Weeks 9-12)

1. **Weekly Updates**: Migration stats, issue resolution
2. **Support**: Dedicated Discord channel for migration help
3. **Blog Series**: Feature highlights, use cases

---

## Success Metrics

### Week 8 (Launch)
- [ ] Zero critical bugs (P0/P1)
- [ ] <10 migration issues reported
- [ ] Documentation site fully updated
- [ ] All links working (no 404s)

### Month 3
- [ ] 80%+ active users migrated
- [ ] Positive community sentiment (>70%)
- [ ] NPM downloads maintain/exceed pre-rebrand
- [ ] "Agent Swarm" search volume increasing

---

## Team & Timeline

### Required Team
- **2× Full-Stack Engineers** (TypeScript, Node.js, Python)
- **1× Designer** (logo, visual assets)
- **1× Technical Writer** (documentation)
- **1× DevOps** (CI/CD, deployment)

### Timeline Summary

| Week | Phase | Owner | Status |
|------|-------|-------|--------|
| 1-2 | Core infrastructure rename | Dev Team | Planning |
| 2 | Visual assets & logo | Designer | Planning |
| 3 | ASCII art & banner | Dev + Designer | Planning |
| 4 | Documentation update | Tech Writer | Planning |
| 5 | Gateway & backend | Dev Team | Planning |
| 6 | Testing & migration tools | QA + Dev | Planning |
| 7 | Internal beta testing | All | Planning |
| 8+ | NPM publish & launch | DevOps | Planning |

**Total**: 6 weeks core work + 2 weeks testing/launch

---

## Next Steps

1. **Get Stakeholder Approval**: Review this plan with AINative leadership
2. **Assign Team**: Allocate engineers, designer, tech writer
3. **Create GitHub Milestone**: "Agent Swarm Rebrand v1.0"
4. **Set Launch Date**: Target 6 weeks from kickoff
5. **Begin Work**: Start with Week 1 tasks (core rename)

---

## Excluded from This Plan

❌ **ZeroDB Integration** - Separate project, tracked independently
❌ **New Features** - Focus on branding only
❌ **Architecture Changes** - Keep current structure
❌ **Performance Optimization** - Separate initiative

---

**Document Status**: Ready for Review
**Last Updated**: March 4, 2026
**Prepared By**: Claude (Sonnet 4.5) for AINative Studio
