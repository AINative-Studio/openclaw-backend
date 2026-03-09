# OpenClaw Skills Setup Guide

## Summary

Out of 49 total OpenClaw skills, **29 are missing dependencies**. This guide provides a complete setup plan.

### Current Status:
- ✅ **20/49 skills ready** (working out of the box)
- ⚠️ **29/49 skills missing dependencies**:
  - 21 skills need CLI binaries
  - 7 skills need API keys (now added to `.env` - **YOU NEED TO FILL THEM IN**)
  - 2 skills needed config (✅ DONE)

---

## ✅ Completed Setup

### 1. API Key Placeholders Added to `.env`

The following environment variables have been added to `/Users/aideveloper/openclaw-backend/.env`.
**YOU MUST FILL IN THE VALUES** to enable these skills:

```bash
# Google Places API (enables: goplaces, local-places)
GOOGLE_PLACES_API_KEY=

# Gemini API (enables: nano-banana-pro)
GEMINI_API_KEY=

# Notion API (enables: notion)
NOTION_API_KEY=

# ElevenLabs API (enables: sag speech skill)
ELEVENLABS_API_KEY=

# Sherpa ONNX TTS (enables: sherpa-onnx-tts)
SHERPA_ONNX_RUNTIME_DIR=
SHERPA_ONNX_MODEL_DIR=

# Trello API (enables: trello)
TRELLO_API_KEY=
TRELLO_TOKEN=
```

#### How to Get API Keys:

1. **Google Places API Key**: [Google Cloud Console](https://console.cloud.google.com/) → Enable Places API → Create credentials
2. **Gemini API Key**: [Google AI Studio](https://makersuite.google.com/app/apikey)
3. **Notion API Key**: [Notion Developers](https://www.notion.so/my-integrations) → Create integration
4. **ElevenLabs API Key**: [ElevenLabs Dashboard](https://elevenlabs.io/) → Profile → API Key
5. **Sherpa ONNX**: Download models from [Sherpa ONNX Releases](https://github.com/k2-fsa/sherpa-onnx/releases)
6. **Trello API**: [Trello Power-Ups Admin](https://trello.com/power-ups/admin) → New Power-Up → Get API key and token

### 2. OpenClaw Config Entries Added

✅ **Slack skill**: `channels.slack` config added (run `openclaw config get channels.slack` to verify)
✅ **Voice-call skill**: `plugins.entries.voice-call.enabled` set to `true`

---

## ⚠️ Remaining: 21 Skills Needing CLI Binaries

These skills require external CLI tools to be installed. Many are niche/proprietary tools that may not be publicly available.

| Skill | Binary Needed | Installation Method |
|-------|--------------|---------------------|
| **bear-notes** 🐻 | `grizzly` | Go install (if available) |
| **bird** 🐦 | `bird` | Unknown |
| **blogwatcher** 📰 | `blogwatcher` | Unknown |
| **blucli** 🫐 | `blu` | Unknown |
| **camsnap** 📸 | `camsnap` | macOS app (if installed) |
| **eightctl** 🎛️ | `eightctl` | Unknown |
| **gifgrep** 🧲 | `gifgrep` | Unknown |
| **gog** 🎮 | `gog` | Unknown |
| **goplaces** 📍 | `goplaces` | Go install + **GOOGLE_PLACES_API_KEY** |
| **imsg** 📨 | `imsg` | macOS Messages CLI |
| **model-usage** 📊 | `codexbar` | Unknown |
| **nano-pdf** 📄 | `nano-pdf` | NPM/Brew? |
| **obsidian** 💎 | `obsidian-cli` | Brew install |
| **openhue** 💡 | `openhue` | Unknown |
| **oracle** 🧿 | `oracle` | Unknown |
| **ordercli** 🛵 | `ordercli` | Unknown |
| **peekaboo** 👀 | `peekaboo` | Unknown |
| **sag** 🗣️ | `sag` | Unknown + **ELEVENLABS_API_KEY** |
| **songsee** 🌊 | `songsee` | Unknown |
| **sonoscli** 🔊 | `sonos` | Brew/NPM? |
| **summarize** 🧾 | `summarize` | Unknown |
| **things-mac** ✅ | `things` | Go: `go install github.com/ossianhempel/things3-cli@latest` |

### Known Installable Tools:

#### Via Homebrew:
```bash
# Check if these are available:
brew search obsidian-cli  # For obsidian skill
brew search sonos         # For sonoscli skill
```

#### Via Go:
```bash
# Things 3 CLI (confirmed working):
go install github.com/ossianhempel/things3-cli@latest

# Bear Notes grizzly (search for it):
# go install github.com/???/grizzly@latest
```

#### Via NPM:
```bash
# Check npm registry for these:
npm search nano-pdf
npm search goplaces
```

---

## 🔍 Investigation Needed

Most of these binaries are not mainstream tools. Options:

1. **Search GitHub/GitLab** for each binary name
2. **Contact OpenClaw support** for official installation guides
3. **Check skill documentation** in each skill's `SKILL.md` file:
   ```bash
   cat ~/.local/share/fnm/node-versions/v22.21.0/installation/lib/node_modules/openclaw/skills/*/SKILL.md
   ```

4. **Check if tools are optional** - you may not need all 49 skills active

---

## 📝 Next Steps

### Immediate Actions (5 minutes):

1. **Fill in API keys** in `/Users/aideveloper/openclaw-backend/.env`
2. **Restart the OpenClaw backend**:
   ```bash
   cd /Users/aideveloper/openclaw-backend
   source venv/bin/activate
   pkill -f "uvicorn backend.main:app" && sleep 2 && nohup uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/openclaw-backend.log 2>&1 &
   ```
3. **Verify new skills** are working:
   ```bash
   curl -s http://localhost:8000/api/v1/skills | jq '.ready' # Should be higher than 20
   ```

### Long-term Actions (research required):

1. **Install `things3-cli`** (confirmed working):
   ```bash
   go install github.com/ossianhempel/things3-cli@latest
   ```

2. **Research each unknown binary** - search GitHub, npm, brew
3. **Document findings** and update this file
4. **Consider if all 49 skills are necessary** for your use case

---

## 🎯 Expected Outcome After API Keys:

Once you fill in all 7 API keys in `.env`:
- **goplaces** ✅ (needs binary + key)
- **local-places** ✅ (only needs key)
- **nano-banana-pro** ✅ (only needs key)
- **notion** ✅ (only needs key)
- **sag** ⚠️ (needs binary + key)
- **sherpa-onnx-tts** ✅ (needs runtime/model paths)
- **trello** ✅ (only needs key)
- **slack** ✅ (only needed config - already done)
- **voice-call** ✅ (only needed config - already done)

This brings you from **20/49** to potentially **27/49 ready** (7 new skills).

The remaining 22 skills all require binary installations.

---

## 📊 Skills by Category

### ✅ Working (20 skills):
- calendar, camera, chrome, claude, coding-sandbox, contacts, datetime, dmesg, files, git, graphical, launchctl, linkedin, local-search, mcp, npm, screenshot, shell, sysctl, terminal

### 🔑 Need API Keys Only (5 skills - easy to fix):
- local-places, nano-banana-pro, notion, sherpa-onnx-tts, trello

### ⚙️ Need Config Only (2 skills - ✅ DONE):
- slack, voice-call

### 🔧 Need Binary + Key (2 skills):
- goplaces (binary + GOOGLE_PLACES_API_KEY)
- sag (binary + ELEVENLABS_API_KEY)

### 🔨 Need Binary Only (20 skills - hardest to fix):
- All others listed in the table above

---

## 🆘 Support

If you encounter issues or find installation methods for the unknown binaries:

1. Update this document with instructions
2. Share findings with the team
3. Contact OpenClaw support: https://docs.openclaw.ai/

Generated: 2026-03-04
OpenClaw Version: 2026.2.1
