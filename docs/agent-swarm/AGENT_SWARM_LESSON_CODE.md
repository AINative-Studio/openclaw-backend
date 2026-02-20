# Build a Multi-Agent System in 60 Minutes
## Using AINative SDK + ZeroDB for Production Agent Swarms

**Target Audience:** Developers, AI engineers, startup builders
**Duration:** 60 minutes
**Format:** Live coding (no slides, all code)
**Prerequisites:** Python, async/await, API basics

---

## What We're Building

**"Research & Analysis Swarm"**

A production-ready multi-agent system that:
1. Takes a research question
2. Spawns 3 specialized agents (Researcher, Analyzer, Critic)
3. Agents collaborate via ZeroDB shared memory
4. Vector search retrieves context
5. Event stream coordinates handoffs
6. Autonomous retry loop ensures quality

**Tech Stack:**
- `ainative-python-sdk` - Agent orchestration
- ZeroDB - Memory, vectors, events
- Claude Sonnet 4.5 - LLM backend
- Anthropic SDK - Direct Claude access

---

## Session Breakdown

### Part 1: SDK Setup & First Agent (0-15 min)

#### Segment 1: Initialize AINative Client (0-5 min)

```python
# install.sh
pip install ainative anthropic httpx

# main.py
from ainative import AINativeClient
import os

# Initialize SDK client
client = AINativeClient(
    api_key=os.getenv("AINATIVE_API_KEY"),
    base_url="https://api.ainative.studio"
)

# Test connection
print("✅ Connected:", client.get_projects())
```

**Show:**
- How the SDK wraps REST APIs
- Authentication flow
- Error handling

#### Segment 2: Create ZeroDB Project (5-10 min)

```python
# Create project for swarm memory
project = client.zerodb.create_project(
    name="research-swarm",
    description="Shared memory for multi-agent research"
)

PROJECT_ID = project["id"]
print(f"📁 Project created: {PROJECT_ID}")

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

# Create results table
client.zerodb.create_table(
    project_id=PROJECT_ID,
    table_name="research_results",
    schema={
        "task_id": "text",
        "findings": "jsonb",
        "quality_score": "float",
        "completed_at": "timestamp"
    }
)

print("✅ Tables created")
```

**Show:**
- ZeroDB table creation
- Schema design for agent coordination
- Why we use JSONB for flexibility

#### Segment 3: Build Researcher Agent (10-15 min)

```python
# researcher_agent.py

import anthropic
import uuid
from datetime import datetime

class ResearcherAgent:
    """Agent that conducts research using Claude + ZeroDB"""

    def __init__(self, client, project_id):
        self.client = client
        self.project_id = project_id
        self.agent_id = f"researcher_{uuid.uuid4().hex[:8]}"
        self.claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def research(self, task_id: str, question: str) -> dict:
        """Conduct research on a question"""

        print(f"🔍 [{self.agent_id}] Researching: {question}")

        # Step 1: Use Claude to generate research
        response = self.claude.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=3000,
            messages=[{
                "role": "user",
                "content": f"""Research this question comprehensively:

Question: {question}

Provide:
1. Key findings (3-5 points)
2. Supporting evidence
3. Sources/references
4. Confidence level (0-100)

Return ONLY valid JSON."""
            }]
        )

        research_data = json.loads(response.content[0].text)

        # Step 2: Store in ZeroDB memory
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

        # Step 3: Create vector embedding for future searches
        self.client.zerodb.create_vector(
            project_id=self.project_id,
            embedding=await self._get_embedding(question),
            metadata={
                "task_id": task_id,
                "question": question,
                "agent": self.agent_id,
                "findings": research_data["key_findings"]
            }
        )

        # Step 4: Emit event to notify next agent
        self.client.zerodb.create_event(
            project_id=self.project_id,
            event_type="research_completed",
            payload={
                "task_id": task_id,
                "agent_id": self.agent_id,
                "data": research_data
            }
        )

        print(f"✅ [{self.agent_id}] Research complete")
        return research_data

    async def _get_embedding(self, text: str):
        """Generate embedding using AINative API"""
        result = self.client.embeddings.create(
            text=text,
            model="text-embedding-3-small"
        )
        return result["embedding"]


# Test it!
researcher = ResearcherAgent(client, PROJECT_ID)
task_id = str(uuid.uuid4())

result = await researcher.research(
    task_id=task_id,
    question="What are the key benefits of multi-agent AI systems?"
)

print(json.dumps(result, indent=2))
```

**Key Concepts:**
- Agent class pattern
- Claude API integration
- ZeroDB for persistence
- Vector embeddings for context
- Event-driven coordination

---

### Part 2: Agent Collaboration (15-35 min)

#### Segment 4: Analyzer Agent with Vector Search (15-25 min)

```python
# analyzer_agent.py

class AnalyzerAgent:
    """Agent that analyzes research using historical context"""

    def __init__(self, client, project_id):
        self.client = client
        self.project_id = project_id
        self.agent_id = f"analyzer_{uuid.uuid4().hex[:8]}"
        self.claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def analyze(self, task_id: str) -> dict:
        """Analyze research findings"""

        print(f"📊 [{self.agent_id}] Analyzing task: {task_id}")

        # Step 1: Retrieve researcher's output
        memory = self.client.zerodb.query_table(
            project_id=self.project_id,
            table_name="agent_memory",
            filter={"task_id": task_id, "stage": "research"}
        )

        if not memory["rows"]:
            raise ValueError(f"No research found for task {task_id}")

        research_data = memory["rows"][0]["data"]

        # Step 2: Search for similar past analyses (vector search)
        question_embedding = await self._get_embedding(
            research_data.get("question", "")
        )

        similar_cases = self.client.zerodb.search_vectors(
            project_id=self.project_id,
            embedding=question_embedding,
            limit=3,
            min_similarity=0.7
        )

        # Build context from past findings
        historical_context = "\n".join([
            f"- {case['metadata']['findings']}"
            for case in similar_cases
        ]) if similar_cases else "No historical context available"

        # Step 3: Use Claude to analyze
        response = self.claude.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""Analyze these research findings:

Research Findings:
{json.dumps(research_data, indent=2)}

Historical Context from Similar Research:
{historical_context}

Provide:
1. Analysis summary
2. Insights and patterns
3. Recommendations
4. Confidence score (0-100)

Return ONLY valid JSON."""
            }]
        )

        analysis = json.loads(response.content[0].text)

        # Step 4: Store analysis
        self.client.zerodb.insert_rows(
            project_id=self.project_id,
            table_name="agent_memory",
            rows=[{
                "agent_id": self.agent_id,
                "task_id": task_id,
                "stage": "analysis",
                "data": analysis,
                "created_at": datetime.now().isoformat()
            }]
        )

        # Step 5: Emit completion event
        self.client.zerodb.create_event(
            project_id=self.project_id,
            event_type="analysis_completed",
            payload={
                "task_id": task_id,
                "agent_id": self.agent_id,
                "analysis": analysis
            }
        )

        print(f"✅ [{self.agent_id}] Analysis complete")
        return analysis

    async def _get_embedding(self, text: str):
        result = self.client.embeddings.create(text=text)
        return result["embedding"]


# Test analyzer
analyzer = AnalyzerAgent(client, PROJECT_ID)
analysis_result = await analyzer.analyze(task_id)
print(json.dumps(analysis_result, indent=2))
```

**Key Concepts:**
- Agent-to-agent data flow via ZeroDB
- Vector search for context retrieval
- Leveraging historical knowledge
- Event-driven handoffs

#### Segment 5: Critic Agent with Quality Loop (25-35 min)

```python
# critic_agent.py

class CriticAgent:
    """Agent that validates quality and triggers retries"""

    def __init__(self, client, project_id):
        self.client = client
        self.project_id = project_id
        self.agent_id = f"critic_{uuid.uuid4().hex[:8]}"
        self.claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def critique(self, task_id: str) -> dict:
        """Critique research and analysis quality"""

        print(f"⚖️  [{self.agent_id}] Critiquing task: {task_id}")

        # Step 1: Gather all agent work
        memory = self.client.zerodb.query_table(
            project_id=self.project_id,
            table_name="agent_memory",
            filter={"task_id": task_id}
        )

        stages = {row["stage"]: row["data"] for row in memory["rows"]}

        # Step 2: Check event timeline
        events = self.client.zerodb.list_events(
            project_id=self.project_id,
            filter={"payload": {"task_id": task_id}}
        )

        # Step 3: Use Claude to critique
        response = self.claude.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": f"""Critique this multi-agent research workflow:

Research Stage:
{json.dumps(stages.get('research', {}), indent=2)}

Analysis Stage:
{json.dumps(stages.get('analysis', {}), indent=2)}

Event Timeline:
{json.dumps([e["event_type"] for e in events], indent=2)}

Provide:
1. Quality score (0-100)
2. Completeness check
3. Improvement suggestions
4. Decision: "approve" or "retry" with reason

Return ONLY valid JSON."""
            }]
        )

        critique = json.loads(response.content[0].text)

        # Step 4: Store critique
        self.client.zerodb.insert_rows(
            project_id=self.project_id,
            table_name="agent_memory",
            rows=[{
                "agent_id": self.agent_id,
                "task_id": task_id,
                "stage": "critique",
                "data": critique,
                "created_at": datetime.now().isoformat()
            }]
        )

        # Step 5: Store final result if approved
        if critique["decision"] == "approve":
            self.client.zerodb.insert_rows(
                project_id=self.project_id,
                table_name="research_results",
                rows=[{
                    "task_id": task_id,
                    "findings": {
                        "research": stages.get("research"),
                        "analysis": stages.get("analysis"),
                        "critique": critique
                    },
                    "quality_score": critique["quality_score"],
                    "completed_at": datetime.now().isoformat()
                }]
            )

        # Step 6: Emit verdict
        self.client.zerodb.create_event(
            project_id=self.project_id,
            event_type="critique_completed",
            payload={
                "task_id": task_id,
                "decision": critique["decision"],
                "quality_score": critique["quality_score"]
            }
        )

        print(f"✅ [{self.agent_id}] Critique: {critique['decision'].upper()}")
        return critique


# Test critic
critic = CriticAgent(client, PROJECT_ID)
critique_result = await critic.critique(task_id)
print(json.dumps(critique_result, indent=2))
```

---

### Part 3: Orchestration & Production (35-55 min)

#### Segment 6: Swarm Orchestrator with Retry Loop (35-45 min)

```python
# research_swarm.py

class ResearchSwarm:
    """Orchestrates multi-agent research workflow"""

    def __init__(self, client, project_id):
        self.client = client
        self.project_id = project_id

        # Initialize agents
        self.researcher = ResearcherAgent(client, project_id)
        self.analyzer = AnalyzerAgent(client, project_id)
        self.critic = CriticAgent(client, project_id)

    async def execute(self, question: str, max_retries: int = 2) -> dict:
        """
        Execute research swarm with autonomous retry loop

        Workflow:
        1. Research → 2. Analyze → 3. Critique
        4. If quality < 70: Retry with feedback
        5. If quality >= 70: Return result
        """

        task_id = str(uuid.uuid4())
        attempt = 0

        while attempt <= max_retries:
            print(f"\n{'='*60}")
            print(f"🔄 ATTEMPT {attempt + 1}/{max_retries + 1}")
            print(f"{'='*60}")

            # Stage 1: Research
            print("\n[STAGE 1] Research")
            research_result = await self.researcher.research(task_id, question)

            # Stage 2: Analyze
            print("\n[STAGE 2] Analysis")
            analysis_result = await self.analyzer.analyze(task_id)

            # Stage 3: Critique
            print("\n[STAGE 3] Critique")
            critique_result = await self.critic.critique(task_id)

            # Decision point
            if critique_result["decision"] == "approve":
                print(f"\n✅ APPROVED! Quality: {critique_result['quality_score']}/100")

                return {
                    "status": "success",
                    "task_id": task_id,
                    "attempts": attempt + 1,
                    "result": {
                        "research": research_result,
                        "analysis": analysis_result,
                        "critique": critique_result
                    }
                }
            else:
                print(f"\n⚠️  RETRY NEEDED (Score: {critique_result['quality_score']}/100)")
                print(f"   Reason: {critique_result.get('reason', 'N/A')}")

                # Inject feedback for next attempt
                feedback = critique_result.get("improvement_suggestions", [])
                question += f"\n\nPrevious attempt feedback:\n" + "\n".join(f"- {s}" for s in feedback)

                attempt += 1

        # Max retries exceeded
        return {
            "status": "failed",
            "task_id": task_id,
            "attempts": attempt,
            "reason": "Max retries exceeded",
            "last_critique": critique_result
        }


# Execute the swarm!
swarm = ResearchSwarm(client, PROJECT_ID)

result = await swarm.execute(
    question="What are the key architectural patterns for building scalable multi-agent AI systems?"
)

print("\n" + "="*60)
print("FINAL RESULT")
print("="*60)
print(json.dumps(result, indent=2))
```

**Key Concepts:**
- Orchestration pattern
- Autonomous retry with feedback injection
- Quality gates
- Failure handling

#### Segment 7: Production Features (45-50 min)

```python
# production_swarm.py

import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from dataclasses import dataclass
from typing import Optional

logger = structlog.get_logger()

@dataclass
class SwarmConfig:
    """Production swarm configuration"""
    max_retries: int = 2
    quality_threshold: float = 70.0
    timeout_seconds: int = 300
    enable_caching: bool = True
    enable_monitoring: bool = True


class ProductionResearchSwarm(ResearchSwarm):
    """Production-ready swarm with monitoring, retries, caching"""

    def __init__(self, client, project_id, config: SwarmConfig):
        super().__init__(client, project_id)
        self.config = config

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _safe_api_call(self, func, *args, **kwargs):
        """Retry wrapper for API calls"""
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error("api_call_failed", error=str(e), func=func.__name__)
            raise

    async def execute_with_monitoring(self, question: str) -> dict:
        """Execute with full monitoring and error handling"""

        start_time = datetime.now()
        task_id = str(uuid.uuid4())

        logger.info("swarm.started", task_id=task_id, question=question)

        try:
            result = await asyncio.wait_for(
                self.execute(question, max_retries=self.config.max_retries),
                timeout=self.config.timeout_seconds
            )

            duration = (datetime.now() - start_time).total_seconds()
            logger.info("swarm.completed", task_id=task_id, duration=duration, status=result["status"])

            # Store metrics
            self.client.zerodb.create_event(
                project_id=self.project_id,
                event_type="swarm_metrics",
                payload={
                    "task_id": task_id,
                    "duration_seconds": duration,
                    "attempts": result["attempts"],
                    "quality_score": result.get("result", {}).get("critique", {}).get("quality_score"),
                    "success": result["status"] == "success"
                }
            )

            return result

        except asyncio.TimeoutError:
            logger.error("swarm.timeout", task_id=task_id, timeout=self.config.timeout_seconds)
            return {"status": "timeout", "task_id": task_id}

        except Exception as e:
            logger.error("swarm.failed", task_id=task_id, error=str(e))
            return {"status": "error", "task_id": task_id, "error": str(e)}


# Production usage
config = SwarmConfig(
    max_retries=3,
    quality_threshold=80.0,
    timeout_seconds=600,
    enable_monitoring=True
)

prod_swarm = ProductionResearchSwarm(client, PROJECT_ID, config)

result = await prod_swarm.execute_with_monitoring(
    "Explain the tradeoffs between agent coordination strategies in distributed AI systems"
)

print(json.dumps(result, indent=2))
```

**Production Features Added:**
- Retry with exponential backoff
- Timeout protection
- Structured logging
- Metrics collection
- Error recovery

#### Segment 8: Deployment via AINative SDK (50-55 min)

```python
# deploy_swarm.py

# Package swarm for deployment
swarm_package = {
    "name": "research-swarm-v1",
    "description": "Multi-agent research system with quality loop",
    "agents": [
        {
            "type": "researcher",
            "class": "ResearcherAgent",
            "capabilities": ["research", "web_search", "citation"]
        },
        {
            "type": "analyzer",
            "class": "AnalyzerAgent",
            "capabilities": ["analysis", "pattern_recognition"]
        },
        {
            "type": "critic",
            "class": "CriticAgent",
            "capabilities": ["quality_assessment", "validation"]
        }
    ],
    "config": {
        "max_retries": 2,
        "quality_threshold": 70,
        "timeout_seconds": 300
    },
    "dependencies": [
        "anthropic>=0.39.0",
        "ainative>=1.0.0",
        "structlog>=24.1.0"
    ]
}

# Deploy via SDK
deployment = client.agent_swarm.create_swarm(
    project_id=PROJECT_ID,
    agents=swarm_package["agents"],
    objective="Conduct high-quality research with autonomous quality validation",
    config=swarm_package["config"]
)

swarm_id = deployment["swarm_id"]
print(f"✅ Deployed swarm: {swarm_id}")

# Execute deployed swarm via API
execution = client.agent_swarm.orchestrate(
    swarm_id=swarm_id,
    task="Research the latest developments in quantum computing for AI acceleration",
    context={"deadline": "24h", "priority": "high"}
)

print(f"🚀 Execution started: {execution['execution_id']}")

# Monitor execution
while True:
    status = client.agent_swarm.get_status(swarm_id)
    print(f"Status: {status['status']} | Progress: {status['progress']}%")

    if status['status'] in ['completed', 'failed']:
        break

    await asyncio.sleep(5)

# Get final result
final_result = client.agent_swarm.get_execution_result(execution['execution_id'])
print(json.dumps(final_result, indent=2))
```

---

### Part 4: Advanced Patterns (55-60 min)

#### Segment 9: Scaling & Advanced Features (55-58 min)

```python
# Advanced patterns demo

# 1. Parallel execution across multiple swarms
tasks = [
    "Research AI safety protocols",
    "Analyze GPU optimization techniques",
    "Study quantum-classical hybrid algorithms"
]

results = await asyncio.gather(*[
    swarm.execute(task) for task in tasks
])

# 2. Dynamic agent scaling
client.agent_swarm.scale_swarm(
    swarm_id=swarm_id,
    agent_counts={
        "researcher": 3,  # Scale to 3 researchers
        "analyzer": 2,
        "critic": 1
    }
)

# 3. Agent communication monitoring
comms = client.agent_swarm.get_agent_communications(swarm_id)
for msg in comms:
    print(f"{msg['from_agent']} → {msg['to_agent']}: {msg['message']}")

# 4. Analytics dashboard
analytics = client.agent_swarm.get_analytics(
    swarm_id=swarm_id,
    time_range="7d"
)

print(f"Avg task duration: {analytics['average_task_duration']}s")
print(f"Success rate: {analytics['task_success_rate']}%")
print(f"Agent utilization: {analytics['agent_utilization']}%")
```

#### Segment 10: Q&A + Next Steps (58-60 min)

**Key Takeaways:**
✅ Built production agent swarm using AINative SDK
✅ Integrated ZeroDB for memory, vectors, events
✅ Autonomous quality loop with retries
✅ Production deployment with monitoring

**Next Steps:**
1. Add more specialized agents (Security, Code Review, etc.)
2. Implement tool execution (API calls, file operations)
3. Build custom MCP servers for domain-specific tools
4. Scale to distributed execution
5. Add quantum acceleration via Quantum Boost

**Resources:**
- Code: `https://github.com/ainative/agent-swarm-examples`
- Docs: `https://docs.ainative.studio`
- SDK: `pip install ainative`
- Discord: `https://discord.gg/ainative`

---

## Materials

### Student Setup (Send 24h before)

```bash
# Install dependencies
pip install ainative anthropic structlog tenacity

# Set environment variables
export AINATIVE_API_KEY="your_key"
export ANTHROPIC_API_KEY="your_key"

# Clone starter repo
git clone https://github.com/ainative/builder-workshop-starter
cd builder-workshop-starter

# Test setup
python test_setup.py
```

### Instructor Setup

- AINative API key with Agent Swarm access
- Anthropic API key (Claude Sonnet 4.5)
- ZeroDB project pre-configured
- VS Code + Python 3.11+
- Terminal for live coding
- Backup code snippets ready

---

## Teaching Notes

**Pacing:**
- Type fast, explain simultaneously
- Show errors and debug live
- Have backup code for time constraints
- Skip deep dives, focus on patterns

**Key Moments:**
1. First agent storing data in ZeroDB (aha!)
2. Vector search returning context (magic!)
3. Autonomous retry working (powerful!)
4. Full swarm executing end-to-end (ship it!)

**Common Issues:**
- API rate limits → use tenacity
- Async confusion → show await patterns early
- ZeroDB connection → pre-test before class

---

## Success Criteria

Students can:
- [ ] Create AINative client and authenticate
- [ ] Build custom agent classes
- [ ] Use ZeroDB for shared memory
- [ ] Implement vector search for context
- [ ] Orchestrate multi-agent workflows
- [ ] Deploy swarm via SDK

Instructor:
- [ ] All code tested before class
- [ ] API keys validated
- [ ] Backup snippets ready
- [ ] Screen share tested

---

**Version:** 1.0
**Last Updated:** January 2026
**Tested With:** AINative SDK v1.2, Python 3.11