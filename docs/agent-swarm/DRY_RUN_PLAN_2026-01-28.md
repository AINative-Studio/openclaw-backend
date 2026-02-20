# 45-Minute Dry Run Plan: Agent Swarm Live Build Session

**Event Date:** January 28, 2026 at 4:00 PM Pacific Time
**Event Link:** https://luma.com/n6zugudn

## Event Overview

- **When:** January 28, 2026 @ 4:00 PM PT
- **Duration:** 1 hour (event), 45 min (dry run core content)
- **Format:** Live coding, no slides
- **Audience:** Builders, AI startup founders, automation engineers

---

## Dry Run Timeline

| Time | Duration | Segment | Description |
|------|----------|---------|-------------|
| 0:00 | 5 min | **Setup & Welcome** | Attendee environment setup check |
| 0:05 | 5 min | **SDK Init** | Initialize AINative client, test connection |
| 0:10 | 5 min | **ZeroDB Project** | Create project + tables for memory |
| 0:15 | 8 min | **Researcher Agent** | Build first agent with Claude + storage |
| 0:23 | 7 min | **Analyzer Agent** | Vector search + context retrieval |
| 0:30 | 5 min | **Critic Agent** | Quality validation + decision loop |
| 0:35 | 7 min | **Orchestrator** | Wire agents together, run full swarm |
| 0:42 | 3 min | **Wrap-up & Q&A** | Key takeaways, resources |

---

## Detailed Breakdown

### 0:00-0:05 — Setup & Welcome (5 min)

**Talking Points:**
- "Welcome to Agent Swarm Live Build - we're coding, not presenting"
- Quick poll: "How many have used Claude Code or Gemini CLI?"

**Attendee Setup Check:**
```bash
# Have attendees verify their setup (send 30 min before event)
python --version   # Should be 3.10+
pip install ainative anthropic httpx

# Set API keys
export AINATIVE_API_KEY="your_key"
export ANTHROPIC_API_KEY="your_key"

# Quick test
python -c "from ainative import AINativeClient; print('Ready!')"
```

**For Claude Code users:**
```bash
# In Claude Code terminal
pip install ainative anthropic
```

**For Gemini CLI users:**
```bash
# Same install, just using gemini instead of claude for LLM calls
pip install ainative google-generativeai
```

---

### 0:05-0:10 — Initialize AINative SDK (5 min)

**Live Code:**
```python
# main.py
from ainative import AINativeClient
import os

client = AINativeClient(
    api_key=os.getenv("AINATIVE_API_KEY"),
    base_url="https://api.ainative.studio"
)

# Verify connection
print("Connected:", client.get_projects())
```

**Key Point:** "The SDK wraps our REST APIs - no HTTP boilerplate"

---

### 0:10-0:15 — Create ZeroDB Project (5 min)

**Live Code:**
```python
# Create swarm memory project
project = client.zerodb.create_project(
    name="research-swarm-demo",
    description="Live demo - multi-agent memory"
)
PROJECT_ID = project["id"]

# Create memory table
client.zerodb.create_table(
    project_id=PROJECT_ID,
    table_name="agent_memory",
    schema={
        "agent_id": "text",
        "task_id": "text",
        "stage": "text",
        "data": "jsonb",
        "created_at": "timestamp"
    }
)
print(f"Project ready: {PROJECT_ID}")
```

**Key Point:** "ZeroDB is how agents share memory - like a whiteboard they all write to"

---

### 0:15-0:23 — Build Researcher Agent (8 min)

**Live Code:**
```python
# researcher_agent.py
import anthropic
import uuid
import json
from datetime import datetime

class ResearcherAgent:
    def __init__(self, client, project_id):
        self.client = client
        self.project_id = project_id
        self.agent_id = f"researcher_{uuid.uuid4().hex[:8]}"
        self.claude = anthropic.Anthropic()

    async def research(self, task_id: str, question: str) -> dict:
        print(f"🔍 [{self.agent_id}] Researching: {question}")

        # Call Claude
        response = self.claude.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[{"role": "user", "content": f"""Research: {question}
Return JSON with: key_findings (list), confidence (0-100)"""}]
        )

        research_data = json.loads(response.content[0].text)

        # Store in ZeroDB
        self.client.zerodb.insert_rows(
            project_id=self.project_id,
            table_name="agent_memory",
            rows=[{
                "agent_id": self.agent_id,
                "task_id": task_id,
                "stage": "research",
                "data": research_data,
                "created_at": datetime.now().isoformat()
            }]
        )

        # Emit event for next agent
        self.client.zerodb.create_event(
            project_id=self.project_id,
            event_type="research_completed",
            payload={"task_id": task_id, "data": research_data}
        )

        return research_data

# Test it!
researcher = ResearcherAgent(client, PROJECT_ID)
result = await researcher.research(
    str(uuid.uuid4()),
    "What makes multi-agent systems powerful?"
)
print(json.dumps(result, indent=2))
```

**Key Points:**
- "Agent = Claude + ZeroDB storage + event emission"
- "Events are how agents trigger each other"

---

### 0:23-0:30 — Build Analyzer Agent (7 min)

**Live Code:**
```python
# analyzer_agent.py
class AnalyzerAgent:
    def __init__(self, client, project_id):
        self.client = client
        self.project_id = project_id
        self.agent_id = f"analyzer_{uuid.uuid4().hex[:8]}"
        self.claude = anthropic.Anthropic()

    async def analyze(self, task_id: str) -> dict:
        print(f"📊 [{self.agent_id}] Analyzing task: {task_id}")

        # Get researcher's output from ZeroDB
        memory = self.client.zerodb.query_table(
            project_id=self.project_id,
            table_name="agent_memory",
            filter={"task_id": task_id, "stage": "research"}
        )
        research_data = memory["rows"][0]["data"]

        # Vector search for historical context
        similar = self.client.zerodb.search_vectors(
            project_id=self.project_id,
            embedding=await self._embed(str(research_data)),
            limit=3
        )

        # Analyze with context
        response = self.claude.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            messages=[{"role": "user", "content": f"""Analyze:
{json.dumps(research_data)}

Historical context: {similar}

Return JSON: insights (list), recommendations (list), confidence (0-100)"""}]
        )

        analysis = json.loads(response.content[0].text)

        # Store and emit
        self.client.zerodb.insert_rows(
            project_id=self.project_id,
            table_name="agent_memory",
            rows=[{"agent_id": self.agent_id, "task_id": task_id,
                   "stage": "analysis", "data": analysis,
                   "created_at": datetime.now().isoformat()}]
        )

        return analysis
```

**Key Point:** "Vector search gives agents memory of past work - they get smarter over time"

---

### 0:30-0:35 — Build Critic Agent (5 min)

**Live Code (condensed):**
```python
# critic_agent.py
class CriticAgent:
    def __init__(self, client, project_id):
        self.client = client
        self.project_id = project_id
        self.claude = anthropic.Anthropic()

    async def critique(self, task_id: str) -> dict:
        # Get all stages
        memory = self.client.zerodb.query_table(
            project_id=self.project_id,
            table_name="agent_memory",
            filter={"task_id": task_id}
        )
        stages = {row["stage"]: row["data"] for row in memory["rows"]}

        # Quality check
        response = self.claude.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            messages=[{"role": "user", "content": f"""Critique this work:
Research: {stages.get('research')}
Analysis: {stages.get('analysis')}

Return JSON: quality_score (0-100), decision ("approve"/"retry"), suggestions (list)"""}]
        )

        return json.loads(response.content[0].text)
```

**Key Point:** "Critic is the quality gate - this is what makes swarms autonomous"

---

### 0:35-0:42 — Wire Up the Orchestrator (7 min)

**Live Code:**
```python
# research_swarm.py
class ResearchSwarm:
    def __init__(self, client, project_id):
        self.researcher = ResearcherAgent(client, project_id)
        self.analyzer = AnalyzerAgent(client, project_id)
        self.critic = CriticAgent(client, project_id)

    async def execute(self, question: str, max_retries: int = 2):
        task_id = str(uuid.uuid4())

        for attempt in range(max_retries + 1):
            print(f"\n{'='*40}\n🔄 ATTEMPT {attempt + 1}\n{'='*40}")

            # Pipeline: Research → Analyze → Critique
            await self.researcher.research(task_id, question)
            await self.analyzer.analyze(task_id)
            critique = await self.critic.critique(task_id)

            if critique["decision"] == "approve":
                print(f"✅ APPROVED! Score: {critique['quality_score']}/100")
                return {"status": "success", "task_id": task_id}

            print(f"⚠️ RETRY - Score: {critique['quality_score']}/100")
            question += f"\nFeedback: {critique['suggestions']}"

        return {"status": "failed", "task_id": task_id}

# DEMO TIME!
swarm = ResearchSwarm(client, PROJECT_ID)
result = await swarm.execute(
    "What are the key patterns for building scalable multi-agent AI systems?"
)
```

**Key Point:** "This is the magic - autonomous retry with feedback injection"

---

### 0:42-0:45 — Wrap-up & Resources (3 min)

**What We Built:**
- 3 specialized agents (Researcher, Analyzer, Critic)
- Shared memory via ZeroDB
- Vector search for context
- Autonomous quality loop with retry

**Next Steps:**
- Add more agents (Security, Executor, etc.)
- Scale with `client.agent_swarm.orchestrate()`
- Check docs: https://docs.ainative.studio

**Resources to Share:**
```
SDK: pip install ainative
Docs: https://docs.ainative.studio
Code: Share gist/repo link post-event
```

---

## Pre-Event Checklist

### Send to attendees 24h before:
```bash
# Setup instructions
pip install ainative anthropic httpx
export AINATIVE_API_KEY="get_from_ainative_studio"
export ANTHROPIC_API_KEY="get_from_anthropic"

# Test
python -c "import ainative, anthropic; print('Ready!')"
```

### Instructor prep:
- [ ] All code tested end-to-end
- [ ] API keys validated (AINative + Anthropic)
- [ ] ZeroDB project pre-created as backup
- [ ] Code snippets ready for copy-paste if typing falls behind
- [ ] Screen share tested
- [ ] Backup connection ready

---

## Timing Buffer Notes

- The lesson material is 60 min; this dry run is 45 min
- Event is 60 min total - extra 15 min for Q&A/overflow
- If running behind: skip the Critic deep dive, show pre-built orchestrator
- If running ahead: demonstrate `client.agent_swarm.orchestrate()` API

---

## Related Files

- Pre-event email: `docs/agent-swarm/PRE_EVENT_EMAIL_2026-01-28.txt`
- Full lesson code: `docs/agent-swarm/AGENT_SWARM_LESSON_CODE.md`
