"""
Agent Monitoring Service

Comprehensive monitoring system for multi-agent swarms providing:
- System-wide agent metrics collection
- Per-agent health reports
- Integration with PrometheusMetricsService
- Alert management and threshold rules
- Degraded agent detection

Migrated from core repository monitoring.py

Issue #112: Migrate Agent Monitoring System from Core
"""

import asyncio
import logging
import threading
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
import statistics

from sqlalchemy.orm import Session

from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
)

logger = logging.getLogger(__name__)

# Singleton instance
_monitoring_service_instance: Optional["AgentMonitoringService"] = None
_singleton_lock = threading.Lock()


class MonitoringLevel(Enum):
    """Monitoring detail levels"""
    BASIC = "basic"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"
    DEBUG = "debug"


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class MetricType(Enum):
    """Types of metrics to monitor"""
    PERFORMANCE = "performance"
    HEALTH = "health"
    RESOURCE = "resource"
    TASK = "task"
    COMMUNICATION = "communication"
    SYSTEM = "system"


@dataclass
class Alert:
    """System alert"""
    id: str
    severity: AlertSeverity
    title: str
    message: str
    source: str
    metric_type: MetricType
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def resolve(self):
        """Mark alert as resolved"""
        self.resolved = True
        self.resolved_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary"""
        return {
            'id': self.id,
            'severity': self.severity.value,
            'title': self.title,
            'message': self.message,
            'source': self.source,
            'metric_type': self.metric_type.value,
            'timestamp': self.timestamp.isoformat(),
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'metadata': self.metadata
        }


@dataclass
class SystemMetrics:
    """System-wide metrics"""
    timestamp: datetime

    # Agent metrics
    total_agents: int = 0
    healthy_agents: int = 0
    degraded_agents: int = 0
    overloaded_agents: int = 0
    offline_agents: int = 0

    # Task metrics
    total_tasks: int = 0
    pending_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    # Performance metrics
    average_response_time: float = 0.0
    average_completion_time: float = 0.0
    system_throughput: float = 0.0
    error_rate: float = 0.0

    # Resource metrics
    average_cpu_usage: float = 0.0
    average_memory_usage: float = 0.0
    total_queue_length: int = 0

    # Communication metrics
    messages_sent: int = 0
    messages_received: int = 0
    message_delivery_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result


@dataclass
class AgentReport:
    """Detailed agent report"""
    agent_id: str
    agent_type: str
    specialization: str
    timestamp: datetime

    # Status
    health_status: str
    is_online: bool
    uptime: timedelta

    # Performance
    current_tasks: int
    completed_tasks: int
    failed_tasks: int
    average_response_time: float
    average_completion_time: float
    success_rate: float

    # Resource utilization
    cpu_usage: float
    memory_usage: float
    queue_length: int

    # Capabilities
    capabilities: List[str]
    capability_utilization: Dict[str, float]

    # Recent activity
    recent_tasks: List[Dict[str, Any]]
    recent_messages: List[Dict[str, Any]]
    recent_errors: List[Dict[str, Any]]

    # Alerts
    active_alerts: List[Alert]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['uptime'] = self.uptime.total_seconds()
        data['active_alerts'] = [alert.to_dict() for alert in self.active_alerts]
        return data


class MonitoringRule:
    """Base class for monitoring rules"""

    def __init__(self, name: str, metric_type: MetricType, severity: AlertSeverity):
        self.name = name
        self.metric_type = metric_type
        self.severity = severity
        self.enabled = True

    def check(self, metrics: Any) -> Optional[Alert]:
        """Check if rule conditions are met"""
        raise NotImplementedError

    def enable(self):
        """Enable rule"""
        self.enabled = True

    def disable(self):
        """Disable rule"""
        self.enabled = False


class ThresholdRule(MonitoringRule):
    """Threshold-based monitoring rule"""

    def __init__(self, name: str, metric_type: MetricType, severity: AlertSeverity,
                 threshold: float, comparison: str, metric_path: str):
        super().__init__(name, metric_type, severity)
        self.threshold = threshold
        self.comparison = comparison  # 'gt', 'lt', 'eq', 'gte', 'lte'
        self.metric_path = metric_path

    def check(self, metrics: Any) -> Optional[Alert]:
        """Check threshold condition"""
        if not self.enabled:
            return None

        # Extract metric value
        try:
            value = self._get_metric_value(metrics, self.metric_path)
        except (KeyError, AttributeError):
            return None

        # Check condition
        condition_met = False
        if self.comparison == 'gt':
            condition_met = value > self.threshold
        elif self.comparison == 'lt':
            condition_met = value < self.threshold
        elif self.comparison == 'eq':
            condition_met = value == self.threshold
        elif self.comparison == 'gte':
            condition_met = value >= self.threshold
        elif self.comparison == 'lte':
            condition_met = value <= self.threshold

        if condition_met:
            return Alert(
                id=f"{self.name}_{datetime.now(timezone.utc).timestamp()}",
                severity=self.severity,
                title=f"{self.name} Threshold Exceeded",
                message=f"Metric {self.metric_path} = {value} {self.comparison} {self.threshold}",
                source="monitoring_rule",
                metric_type=self.metric_type,
                timestamp=datetime.now(timezone.utc),
                metadata={
                    'rule_name': self.name,
                    'metric_path': self.metric_path,
                    'value': value,
                    'threshold': self.threshold,
                    'comparison': self.comparison
                }
            )

        return None

    def _get_metric_value(self, metrics: Any, path: str) -> float:
        """Extract metric value from path"""
        parts = path.split('.')
        value = metrics
        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            elif isinstance(value, dict):
                value = value[part]
            else:
                raise KeyError(f"Path {path} not found in metrics")
        return float(value)


class AgentMonitoringService:
    """
    Comprehensive monitoring system for multi-agent swarms

    Provides real-time health monitoring, performance analytics,
    alerting, and detailed reporting capabilities.
    """

    def __init__(
        self,
        db_session: Session,
        prometheus_metrics: Optional[Any] = None,
        monitoring_level: MonitoringLevel = MonitoringLevel.DETAILED
    ):
        self.db_session = db_session
        self.prometheus_metrics = prometheus_metrics
        self.monitoring_level = monitoring_level

        # Monitoring state
        self.monitoring_active = False
        self.monitoring_interval = 30  # seconds
        self.monitoring_task: Optional[asyncio.Task] = None

        # Historical data
        self.system_metrics_history: deque = deque(maxlen=1000)
        self.agent_metrics_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self.alert_history: deque = deque(maxlen=1000)

        # Active alerts
        self.active_alerts: Dict[str, Alert] = {}

        # Monitoring rules
        self.monitoring_rules: List[MonitoringRule] = []
        self._setup_default_rules()

        # Event handlers
        self.alert_handlers: List[Callable[[Alert], None]] = []

        # Agent metrics cache (in-memory cache of computed metrics)
        self.agent_metrics: Dict[str, Any] = {}

        # Performance tracking
        self.start_time = datetime.now(timezone.utc)
        self.last_metrics_collection = datetime.now(timezone.utc)

        logger.info(f"Initialized AgentMonitoringService with level: {monitoring_level.value}")

    def _setup_default_rules(self):
        """Setup default monitoring rules"""
        # Agent health rules
        self.monitoring_rules.extend([
            ThresholdRule(
                name="High Error Rate",
                metric_type=MetricType.HEALTH,
                severity=AlertSeverity.ERROR,
                threshold=0.1,
                comparison='gt',
                metric_path='error_rate'
            ),
            ThresholdRule(
                name="High Response Time",
                metric_type=MetricType.PERFORMANCE,
                severity=AlertSeverity.WARNING,
                threshold=30.0,
                comparison='gt',
                metric_path='average_response_time'
            ),
            ThresholdRule(
                name="High CPU Usage",
                metric_type=MetricType.RESOURCE,
                severity=AlertSeverity.WARNING,
                threshold=0.8,
                comparison='gt',
                metric_path='cpu_usage'
            ),
            ThresholdRule(
                name="High Memory Usage",
                metric_type=MetricType.RESOURCE,
                severity=AlertSeverity.WARNING,
                threshold=0.8,
                comparison='gt',
                metric_path='memory_usage'
            ),
            ThresholdRule(
                name="Large Queue Length",
                metric_type=MetricType.TASK,
                severity=AlertSeverity.WARNING,
                threshold=20,
                comparison='gt',
                metric_path='queue_length'
            )
        ])

    async def start_monitoring(self):
        """Start the monitoring system"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())

        logger.info("Started agent monitoring")

    async def stop_monitoring(self):
        """Stop the monitoring system"""
        if not self.monitoring_active:
            return

        self.monitoring_active = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped agent monitoring")

    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                # Collect system metrics
                system_metrics = await self._collect_system_metrics()
                self.system_metrics_history.append(system_metrics)

                # Collect agent metrics
                await self._collect_agent_metrics()

                # Check monitoring rules
                await self._check_monitoring_rules()

                # Clean up old alerts
                self._cleanup_old_alerts()

                # Update last collection time
                self.last_metrics_collection = datetime.now(timezone.utc)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)

            # Wait for next interval
            await asyncio.sleep(self.monitoring_interval)

    async def _collect_system_metrics(self) -> SystemMetrics:
        """Collect system-wide metrics"""
        metrics = SystemMetrics(timestamp=datetime.now(timezone.utc))

        try:
            # Query all agents
            agents = self.db_session.query(AgentSwarmInstance).filter(
                AgentSwarmInstance.status.in_([
                    AgentSwarmStatus.RUNNING,
                    AgentSwarmStatus.PAUSED,
                    AgentSwarmStatus.PROVISIONING,
                ])
            ).all()

            metrics.total_agents = len(agents)

            # Count agents by status
            for agent in agents:
                if agent.status == AgentSwarmStatus.RUNNING:
                    metrics.healthy_agents += 1
                elif agent.status == AgentSwarmStatus.PAUSED:
                    metrics.degraded_agents += 1
                elif agent.status == AgentSwarmStatus.PROVISIONING:
                    metrics.overloaded_agents += 1

            # Calculate average metrics from cached agent metrics
            if self.agent_metrics:
                response_times = []
                completion_times = []
                error_rates = []
                cpu_usages = []
                memory_usages = []
                queue_lengths = []

                for agent_metric in self.agent_metrics.values():
                    if hasattr(agent_metric, 'average_response_time'):
                        response_times.append(agent_metric.average_response_time)
                    if hasattr(agent_metric, 'average_completion_time'):
                        completion_times.append(agent_metric.average_completion_time)
                    if hasattr(agent_metric, 'error_rate'):
                        error_rates.append(agent_metric.error_rate)
                    if hasattr(agent_metric, 'cpu_usage'):
                        cpu_usages.append(agent_metric.cpu_usage)
                    if hasattr(agent_metric, 'memory_usage'):
                        memory_usages.append(agent_metric.memory_usage)
                    if hasattr(agent_metric, 'queue_length'):
                        queue_lengths.append(agent_metric.queue_length)

                if response_times:
                    metrics.average_response_time = statistics.mean(response_times)
                if completion_times:
                    metrics.average_completion_time = statistics.mean(completion_times)
                if error_rates:
                    metrics.error_rate = statistics.mean(error_rates)
                if cpu_usages:
                    metrics.average_cpu_usage = statistics.mean(cpu_usages)
                if memory_usages:
                    metrics.average_memory_usage = statistics.mean(memory_usages)
                if queue_lengths:
                    metrics.total_queue_length = sum(queue_lengths)

            # Record to Prometheus
            if self.prometheus_metrics:
                try:
                    # Record agent counts
                    if hasattr(self.prometheus_metrics, 'record_agent_count'):
                        self.prometheus_metrics.record_agent_count(
                            status="healthy",
                            count=metrics.healthy_agents
                        )
                        self.prometheus_metrics.record_agent_count(
                            status="degraded",
                            count=metrics.degraded_agents
                        )
                except Exception as e:
                    logger.warning(f"Failed to record Prometheus metrics: {e}")

        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}", exc_info=True)

        return metrics

    async def _collect_agent_metrics(self):
        """Collect individual agent metrics"""
        try:
            agents = self.db_session.query(AgentSwarmInstance).filter(
                AgentSwarmInstance.status == AgentSwarmStatus.RUNNING
            ).all()

            for agent in agents:
                try:
                    # Store metric snapshot in history
                    if str(agent.id) in self.agent_metrics:
                        self.agent_metrics_history[str(agent.id)].append({
                            'timestamp': datetime.now(timezone.utc),
                            'metrics': self.agent_metrics[str(agent.id)]
                        })

                except Exception as e:
                    logger.warning(f"Failed to collect metrics for agent {agent.id}: {e}")

        except Exception as e:
            logger.error(f"Error in agent metrics collection: {e}", exc_info=True)

    async def _check_monitoring_rules(self):
        """Check all monitoring rules against current metrics"""
        for rule in self.monitoring_rules:
            if not rule.enabled:
                continue

            # Check rule against each agent
            for agent_id, agent_metrics in self.agent_metrics.items():
                try:
                    alert = rule.check(agent_metrics)
                    if alert:
                        # Enhance alert with agent info
                        alert.source = f"agent_{agent_id}"
                        alert.metadata['agent_id'] = agent_id

                        # Add to active alerts
                        self.active_alerts[alert.id] = alert
                        self.alert_history.append(alert)

                        # Record to Prometheus
                        self._record_alert_to_prometheus(alert)

                        # Notify handlers
                        for handler in self.alert_handlers:
                            try:
                                handler(alert)
                            except Exception as e:
                                logger.error(f"Error in alert handler: {e}")

                        logger.warning(f"Alert raised: {alert.title} for agent {agent_id}")

                except Exception as e:
                    logger.error(f"Error checking rule {rule.name} for agent {agent_id}: {e}")

    def _cleanup_old_alerts(self):
        """Clean up old resolved alerts"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

        # Remove old resolved alerts
        to_remove = []
        for alert_id, alert in self.active_alerts.items():
            if alert.resolved and alert.resolved_at and alert.resolved_at < cutoff_time:
                to_remove.append(alert_id)

        for alert_id in to_remove:
            del self.active_alerts[alert_id]

    def _record_alert_to_prometheus(self, alert: Alert):
        """Record alert creation to Prometheus"""
        if self.prometheus_metrics and hasattr(self.prometheus_metrics, 'record_alert_created'):
            try:
                self.prometheus_metrics.record_alert_created(
                    severity=alert.severity.value,
                    metric_type=alert.metric_type.value
                )
            except Exception as e:
                logger.warning(f"Failed to record alert to Prometheus: {e}")

    def add_alert_handler(self, handler: Callable[[Alert], None]):
        """Add alert handler"""
        self.alert_handlers.append(handler)

    def remove_alert_handler(self, handler: Callable[[Alert], None]):
        """Remove alert handler"""
        if handler in self.alert_handlers:
            self.alert_handlers.remove(handler)

    def add_monitoring_rule(self, rule: MonitoringRule):
        """Add monitoring rule"""
        self.monitoring_rules.append(rule)

    def remove_monitoring_rule(self, rule: MonitoringRule):
        """Remove monitoring rule"""
        if rule in self.monitoring_rules:
            self.monitoring_rules.remove(rule)

    def resolve_alert(self, alert_id: str):
        """Resolve an alert"""
        alert = self.active_alerts.get(alert_id)
        if alert:
            alert.resolve()

            # Record to Prometheus
            if self.prometheus_metrics and hasattr(self.prometheus_metrics, 'record_alert_resolved'):
                try:
                    self.prometheus_metrics.record_alert_resolved(
                        severity=alert.severity.value
                    )
                except Exception as e:
                    logger.warning(f"Failed to record alert resolution to Prometheus: {e}")

            logger.info(f"Resolved alert: {alert_id}")

    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status"""
        if not self.system_metrics_history:
            return {'status': 'unknown', 'message': 'No metrics available'}

        latest_metrics = self.system_metrics_history[-1]

        # Calculate health score
        health_score = 100.0

        # Penalize based on unhealthy agents
        if latest_metrics.total_agents > 0:
            unhealthy_ratio = (latest_metrics.degraded_agents + latest_metrics.overloaded_agents +
                             latest_metrics.offline_agents) / latest_metrics.total_agents
            health_score -= unhealthy_ratio * 30

        # Penalize based on error rate
        health_score -= latest_metrics.error_rate * 20

        # Penalize based on response time
        if latest_metrics.average_response_time > 0:
            response_penalty = min(latest_metrics.average_response_time / 10, 20)
            health_score -= response_penalty

        # Penalize based on active critical alerts
        critical_alerts = len([a for a in self.active_alerts.values()
                             if a.severity == AlertSeverity.CRITICAL and not a.resolved])
        health_score -= critical_alerts * 15

        health_score = max(health_score, 0.0)

        # Determine status
        if health_score >= 90:
            status = 'excellent'
        elif health_score >= 75:
            status = 'good'
        elif health_score >= 50:
            status = 'fair'
        elif health_score >= 25:
            status = 'poor'
        else:
            status = 'critical'

        return {
            'status': status,
            'health_score': health_score,
            'timestamp': latest_metrics.timestamp.isoformat(),
            'healthy_agents': latest_metrics.healthy_agents,
            'total_agents': latest_metrics.total_agents,
            'active_alerts': len([a for a in self.active_alerts.values() if not a.resolved]),
            'critical_alerts': critical_alerts,
            'system_throughput': latest_metrics.system_throughput,
            'average_response_time': latest_metrics.average_response_time,
            'error_rate': latest_metrics.error_rate
        }

    def get_agent_report(self, agent_id: str) -> Optional[AgentReport]:
        """Get detailed report for specific agent"""
        # Query agent from database
        agent = self.db_session.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            return None

        # Get cached metrics
        agent_metrics = self.agent_metrics.get(agent_id)
        if not agent_metrics:
            return None

        # Calculate uptime
        uptime = datetime.now(timezone.utc) - agent.created_at

        # Get active alerts for this agent
        active_alerts = [
            alert for alert in self.active_alerts.values()
            if alert.metadata.get('agent_id') == agent_id and not alert.resolved
        ]

        # Build report
        return AgentReport(
            agent_id=agent_id,
            agent_type=type(agent).__name__,
            specialization=getattr(agent, 'specialization', 'general'),
            timestamp=datetime.now(timezone.utc),
            health_status=agent.status.value,
            is_online=(agent.status == AgentSwarmStatus.RUNNING),
            uptime=uptime,
            current_tasks=getattr(agent_metrics, 'current_tasks', 0),
            completed_tasks=getattr(agent_metrics, 'completed_tasks', 0),
            failed_tasks=getattr(agent_metrics, 'failed_tasks', 0),
            average_response_time=getattr(agent_metrics, 'average_response_time', 0.0),
            average_completion_time=getattr(agent_metrics, 'average_completion_time', 0.0),
            success_rate=1.0 - getattr(agent_metrics, 'error_rate', 0.0),
            cpu_usage=getattr(agent_metrics, 'cpu_usage', 0.0),
            memory_usage=getattr(agent_metrics, 'memory_usage', 0.0),
            queue_length=getattr(agent_metrics, 'queue_length', 0),
            capabilities=getattr(agent, 'capabilities', []),
            capability_utilization=getattr(agent_metrics, 'capability_utilization', {}),
            recent_tasks=[],
            recent_messages=[],
            recent_errors=[],
            active_alerts=active_alerts
        )

    def get_monitoring_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive monitoring dashboard data"""
        return {
            'system_health': self.get_system_health(),
            'system_metrics': self.system_metrics_history[-1].to_dict() if self.system_metrics_history else {},
            'active_alerts': [alert.to_dict() for alert in self.active_alerts.values() if not alert.resolved],
            'monitoring_status': {
                'active': self.monitoring_active,
                'interval': self.monitoring_interval,
                'level': self.monitoring_level.value,
                'last_collection': self.last_metrics_collection.isoformat(),
                'uptime': (datetime.now(timezone.utc) - self.start_time).total_seconds(),
                'rules_count': len(self.monitoring_rules),
                'active_rules': len([r for r in self.monitoring_rules if r.enabled])
            },
            'historical_data': {
                'system_metrics_count': len(self.system_metrics_history),
                'agent_metrics_count': sum(len(history) for history in self.agent_metrics_history.values()),
                'alerts_count': len(self.alert_history)
            }
        }

    async def get_degraded_agents(self) -> List[str]:
        """Get list of degraded agent IDs"""
        degraded = []

        for agent_id, metrics in self.agent_metrics.items():
            # Check if agent is degraded based on thresholds
            if hasattr(metrics, 'cpu_usage') and metrics.cpu_usage > 0.8:
                degraded.append(agent_id)
            elif hasattr(metrics, 'error_rate') and metrics.error_rate > 0.1:
                degraded.append(agent_id)
            elif hasattr(metrics, 'memory_usage') and metrics.memory_usage > 0.8:
                degraded.append(agent_id)

        return degraded


def get_agent_monitoring_service(
    db_session: Optional[Session] = None,
    prometheus_metrics: Optional[Any] = None,
    monitoring_level: MonitoringLevel = MonitoringLevel.DETAILED,
) -> AgentMonitoringService:
    """
    Get the singleton AgentMonitoringService instance.

    Args:
        db_session: Database session (required for first initialization)
        prometheus_metrics: Prometheus metrics service
        monitoring_level: Monitoring detail level

    Returns:
        The shared AgentMonitoringService instance
    """
    global _monitoring_service_instance

    # If arguments provided, create new instance
    if db_session is not None:
        return AgentMonitoringService(
            db_session=db_session,
            prometheus_metrics=prometheus_metrics,
            monitoring_level=monitoring_level,
        )

    # Otherwise return singleton
    if _monitoring_service_instance is None:
        with _singleton_lock:
            if _monitoring_service_instance is None:
                # Cannot create without db_session
                raise ValueError("db_session required for first initialization")

    return _monitoring_service_instance
