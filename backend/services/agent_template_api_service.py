"""
Agent Template API Service

CRUD service for agent templates with idempotent seed logic
for 9 default templates.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.models.agent_template import AgentTemplate, TemplateCategory
from backend.schemas.agent_template import (
    CreateTemplateRequest,
    UpdateTemplateRequest,
)

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {e.value for e in TemplateCategory}

DEFAULT_TEMPLATES = [
    {
        "id": "template-linear",
        "name": "Linear Ticket Solver",
        "description": "Automatically picks up assigned Linear issues, writes the code fix, and opens a pull request for your team to review.",
        "category": "engineering",
        "icons": ["github", "linear", "git"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You are a software engineer that monitors Linear for assigned issues. When a new issue is assigned to you, create a feature branch, implement the solution, push the code, and open a pull request for your team to review.",
        "default_heartbeat_interval": "5m",
        "default_checklist": [
            "Check Linear for newly assigned or in-progress issues",
            "For each issue: create branch, implement fix, push, and open PR",
            "Post PR link to Slack with a summary of changes",
        ],
    },
    {
        "id": "template-pr-review",
        "name": "PR Review Bot",
        "description": "Watches your open pull requests for review comments, addresses feedback automatically, and re-requests reviews.",
        "category": "engineering",
        "icons": ["github"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You are a code reviewer that monitors GitHub PRs. When review comments appear, address the feedback, push fixes, and re-request review.",
        "default_heartbeat_interval": "5m",
        "default_checklist": [
            "Check for new PR review comments",
            "Address feedback and push fixes",
        ],
    },
    {
        "id": "template-incident-responder",
        "name": "Incident Responder",
        "description": "Responds to Grafana alerts by investigating distributed traces, logs, and metrics to deliver a root-cause analysis.",
        "category": "engineering",
        "icons": ["grafana", "pagerduty"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You are an incident responder that monitors Grafana alerts. When an alert fires, investigate distributed traces, logs, and metrics to deliver a root-cause analysis.",
        "default_heartbeat_interval": "5m",
        "default_checklist": [
            "Check for active Grafana alerts",
            "Investigate distributed traces and logs",
        ],
    },
    {
        "id": "template-log-monitor",
        "name": "Log Monitor",
        "description": "Continuously monitors your backend application logs for errors, exceptions, and anomalous patterns before they become incidents.",
        "category": "engineering",
        "icons": ["grafana"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You are a log monitoring agent. Continuously scan application logs for errors, exceptions, and anomalous patterns. Alert the team before issues become incidents.",
        "default_heartbeat_interval": "5m",
        "default_checklist": [
            "Scan application logs for errors",
            "Alert on anomalous patterns",
        ],
    },
    {
        "id": "template-http-error",
        "name": "HTTP Error Monitoring",
        "description": "Monitors HTTP response codes across your services and alerts with root-cause analysis on errors.",
        "category": "devops-infrastructure",
        "icons": ["grafana"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You monitor HTTP endpoints for errors. When 5xx or elevated 4xx rates are detected, perform root-cause analysis and alert the team.",
        "default_heartbeat_interval": "5m",
        "default_checklist": [
            "Check HTTP response codes",
            "Alert on 5xx errors with analysis",
        ],
    },
    {
        "id": "template-slack-engineer",
        "name": "Team Slack Engineer",
        "description": "A virtual AI engineer your team can talk to in Slack. Investigates code, answers technical questions with real codebase context.",
        "category": "engineering",
        "icons": ["slack"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You are a virtual engineer available in Slack. Answer technical questions, investigate code, and help debug issues using real codebase context.",
        "default_heartbeat_interval": "5m",
        "default_checklist": [
            "Monitor Slack channels for questions",
        ],
    },
    {
        "id": "template-on-call",
        "name": "On-Call Companion",
        "description": "You can call assistant when you are away from your laptop. Diagnose production issues, create fix PRs, and manage incidents via phone.",
        "category": "devops-infrastructure",
        "icons": ["pagerduty", "twilio"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You are an on-call companion. Diagnose production issues, create fix PRs, and manage incidents. Available via phone when the engineer is away from their laptop.",
        "default_heartbeat_interval": "15m",
        "default_checklist": [
            "Check for active incidents",
            "Prepare diagnostic reports",
        ],
    },
    {
        "id": "template-sdk-outreach",
        "name": "SDK Outreach Agent",
        "description": "Manages outbound developer outreach campaigns and follow-ups.",
        "category": "sales-outreach",
        "icons": ["linkedin", "email"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You manage developer outreach. Identify targets, craft personalized messages, and handle follow-up sequences for SDK adoption campaigns.",
        "default_heartbeat_interval": "30m",
        "default_checklist": [
            "Check for new outreach targets",
            "Send follow-up messages",
        ],
    },
    {
        "id": "template-customer-support",
        "name": "Customer Support",
        "description": "Prototyping, support, and relationship management.",
        "category": "sales-outreach",
        "icons": ["email", "slack"],
        "default_model": "anthropic/claude-opus-4-5",
        "default_persona": "You handle customer support inquiries. Monitor support channels, respond to tickets, and escalate complex issues to the appropriate team.",
        "default_heartbeat_interval": "15m",
        "default_checklist": [
            "Check for new support tickets",
            "Respond to pending inquiries",
        ],
    },
]


class AgentTemplateApiService:
    """CRUD service for agent template management"""

    def __init__(self, db: Session):
        self.db = db

    def list_templates(
        self,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentTemplate], int]:
        query = self.db.query(AgentTemplate)

        if category and category in VALID_CATEGORIES:
            try:
                cat_enum = TemplateCategory(category)
                query = query.filter(AgentTemplate.category == cat_enum)
            except ValueError:
                pass

        total = query.count()
        templates = (
            query.order_by(AgentTemplate.created_at.asc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return templates, total

    def get_template(self, template_id: str) -> Optional[AgentTemplate]:
        return self.db.query(AgentTemplate).filter(
            AgentTemplate.id == template_id
        ).first()

    def create_template(
        self, user_id: str, request: CreateTemplateRequest
    ) -> AgentTemplate:
        category_value = request.category
        if category_value in VALID_CATEGORIES:
            category_value = TemplateCategory(category_value)

        template = AgentTemplate(
            id=str(uuid4()),
            name=request.name,
            description=request.description,
            category=category_value,
            icons=request.icons,
            default_model=request.default_model,
            default_persona=request.default_persona,
            default_heartbeat_interval=request.default_heartbeat_interval,
            default_checklist=request.default_checklist,
            user_id=user_id,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def update_template(
        self, template_id: str, request: UpdateTemplateRequest
    ) -> Optional[AgentTemplate]:
        template = self.get_template(template_id)
        if not template:
            return None

        if request.name is not None:
            template.name = request.name
        if request.description is not None:
            template.description = request.description
        if request.category is not None and request.category in VALID_CATEGORIES:
            template.category = TemplateCategory(request.category)
        if request.icons is not None:
            template.icons = request.icons
        if request.default_model is not None:
            template.default_model = request.default_model
        if request.default_persona is not None:
            template.default_persona = request.default_persona
        if request.default_heartbeat_interval is not None:
            template.default_heartbeat_interval = request.default_heartbeat_interval
        if request.default_checklist is not None:
            template.default_checklist = request.default_checklist

        template.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: str) -> Optional[AgentTemplate]:
        template = self.get_template(template_id)
        if not template:
            return None

        self.db.delete(template)
        self.db.commit()
        return template

    def seed_templates(self, user_id: str) -> list[AgentTemplate]:
        """Idempotent seed of default templates. Checks by name to avoid duplicates."""
        seeded = []
        for tpl_data in DEFAULT_TEMPLATES:
            existing = self.db.query(AgentTemplate).filter(
                AgentTemplate.name == tpl_data["name"]
            ).first()
            if existing:
                continue

            template = AgentTemplate(
                id=tpl_data["id"],
                name=tpl_data["name"],
                description=tpl_data["description"],
                category=TemplateCategory(tpl_data["category"]),
                icons=tpl_data["icons"],
                default_model=tpl_data["default_model"],
                default_persona=tpl_data["default_persona"],
                default_heartbeat_interval=tpl_data["default_heartbeat_interval"],
                default_checklist=tpl_data["default_checklist"],
                user_id=user_id,
            )
            self.db.add(template)
            seeded.append(template)

        if seeded:
            self.db.commit()
            for t in seeded:
                self.db.refresh(t)

        return seeded
