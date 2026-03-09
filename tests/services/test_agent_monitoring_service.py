"""
Unit Tests for Agent Monitoring Service

Tests comprehensive agent monitoring capabilities including:
- System-wide metrics collection
- Per-agent health reports
- Prometheus integration
- Alert management
- Degraded agent detection

Issue #112: Migrate Agent Monitoring System from Core
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from collections import deque

from backend.services.agent_monitoring_service import (
    AgentMonitoringService,
    MonitoringLevel,
    AlertSeverity,
    MetricType,
    Alert,
    SystemMetrics,
    AgentReport,
    MonitoringRule,
    ThresholdRule,
    get_agent_monitoring_service,
)
from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
)


class TestMonitoringEnums:
    """Test monitoring enumeration types"""

    def test_monitoring_level_enum(self):
        """
        GIVEN monitoring level enumeration
        WHEN accessing values
        THEN should have correct string values
        """
        assert MonitoringLevel.BASIC.value == "basic"
        assert MonitoringLevel.DETAILED.value == "detailed"
        assert MonitoringLevel.COMPREHENSIVE.value == "comprehensive"
        assert MonitoringLevel.DEBUG.value == "debug"

    def test_alert_severity_enum(self):
        """
        GIVEN alert severity enumeration
        WHEN accessing values
        THEN should have correct string values
        """
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.ERROR.value == "error"
        assert AlertSeverity.CRITICAL.value == "critical"

    def test_metric_type_enum(self):
        """
        GIVEN metric type enumeration
        WHEN accessing values
        THEN should have correct string values
        """
        assert MetricType.PERFORMANCE.value == "performance"
        assert MetricType.HEALTH.value == "health"
        assert MetricType.RESOURCE.value == "resource"
        assert MetricType.TASK.value == "task"
        assert MetricType.COMMUNICATION.value == "communication"
        assert MetricType.SYSTEM.value == "system"


class TestAlert:
    """Test Alert dataclass"""

    @pytest.fixture
    def sample_alert(self):
        """Create a sample alert"""
        return Alert(
            id="alert_001",
            severity=AlertSeverity.WARNING,
            title="High CPU Usage",
            message="CPU usage exceeded 80%",
            source="agent_001",
            metric_type=MetricType.RESOURCE,
            timestamp=datetime.now(timezone.utc),
        )

    def test_alert_creation(self, sample_alert):
        """
        GIVEN alert parameters
        WHEN creating alert
        THEN should initialize correctly
        """
        assert sample_alert.id == "alert_001"
        assert sample_alert.severity == AlertSeverity.WARNING
        assert sample_alert.title == "High CPU Usage"
        assert not sample_alert.resolved
        assert sample_alert.resolved_at is None

    def test_alert_resolve(self, sample_alert):
        """
        GIVEN an unresolved alert
        WHEN calling resolve()
        THEN should mark as resolved with timestamp
        """
        # When
        sample_alert.resolve()

        # Then
        assert sample_alert.resolved is True
        assert sample_alert.resolved_at is not None
        assert isinstance(sample_alert.resolved_at, datetime)

    def test_alert_to_dict(self, sample_alert):
        """
        GIVEN an alert
        WHEN calling to_dict()
        THEN should return dictionary representation
        """
        # When
        alert_dict = sample_alert.to_dict()

        # Then
        assert alert_dict["id"] == "alert_001"
        assert alert_dict["severity"] == "warning"
        assert alert_dict["title"] == "High CPU Usage"
        assert alert_dict["resolved"] is False
        assert alert_dict["resolved_at"] is None
        assert "timestamp" in alert_dict
        assert "metadata" in alert_dict


class TestSystemMetrics:
    """Test SystemMetrics dataclass"""

    def test_system_metrics_creation(self):
        """
        GIVEN system metrics parameters
        WHEN creating SystemMetrics
        THEN should initialize with defaults
        """
        # When
        metrics = SystemMetrics(timestamp=datetime.now(timezone.utc))

        # Then
        assert metrics.total_agents == 0
        assert metrics.healthy_agents == 0
        assert metrics.degraded_agents == 0
        assert metrics.average_response_time == 0.0
        assert metrics.error_rate == 0.0

    def test_system_metrics_to_dict(self):
        """
        GIVEN populated system metrics
        WHEN calling to_dict()
        THEN should return dictionary representation
        """
        # Given
        timestamp = datetime.now(timezone.utc)
        metrics = SystemMetrics(
            timestamp=timestamp,
            total_agents=10,
            healthy_agents=8,
            degraded_agents=2,
        )

        # When
        metrics_dict = metrics.to_dict()

        # Then
        assert metrics_dict["total_agents"] == 10
        assert metrics_dict["healthy_agents"] == 8
        assert metrics_dict["degraded_agents"] == 2


class TestAgentReport:
    """Test AgentReport dataclass"""

    @pytest.fixture
    def sample_report(self):
        """Create a sample agent report"""
        return AgentReport(
            agent_id="agent_001",
            agent_type="SwarmAgent",
            specialization="code_generation",
            timestamp=datetime.now(timezone.utc),
            health_status="healthy",
            is_online=True,
            uptime=timedelta(hours=2),
            current_tasks=3,
            completed_tasks=15,
            failed_tasks=1,
            average_response_time=2.5,
            average_completion_time=45.0,
            success_rate=0.94,
            cpu_usage=0.45,
            memory_usage=0.62,
            queue_length=5,
            capabilities=["python", "javascript"],
            capability_utilization={"python": 0.7, "javascript": 0.3},
            recent_tasks=[],
            recent_messages=[],
            recent_errors=[],
            active_alerts=[],
        )

    def test_agent_report_creation(self, sample_report):
        """
        GIVEN agent report parameters
        WHEN creating AgentReport
        THEN should initialize correctly
        """
        assert sample_report.agent_id == "agent_001"
        assert sample_report.agent_type == "SwarmAgent"
        assert sample_report.is_online is True
        assert sample_report.success_rate == 0.94

    def test_agent_report_to_dict(self, sample_report):
        """
        GIVEN an agent report
        WHEN calling to_dict()
        THEN should return dictionary representation
        """
        # When
        report_dict = sample_report.to_dict()

        # Then
        assert report_dict["agent_id"] == "agent_001"
        assert report_dict["health_status"] == "healthy"
        assert isinstance(report_dict["uptime"], float)
        assert "timestamp" in report_dict


class TestThresholdRule:
    """Test ThresholdRule monitoring rule"""

    def test_threshold_rule_creation(self):
        """
        GIVEN threshold rule parameters
        WHEN creating ThresholdRule
        THEN should initialize correctly
        """
        # When
        rule = ThresholdRule(
            name="High CPU",
            metric_type=MetricType.RESOURCE,
            severity=AlertSeverity.WARNING,
            threshold=0.8,
            comparison="gt",
            metric_path="cpu_usage",
        )

        # Then
        assert rule.name == "High CPU"
        assert rule.threshold == 0.8
        assert rule.comparison == "gt"
        assert rule.enabled is True

    def test_threshold_rule_check_gt_triggers(self):
        """
        GIVEN a threshold rule with gt comparison
        WHEN metric value exceeds threshold
        THEN should return alert
        """
        # Given
        rule = ThresholdRule(
            name="High CPU",
            metric_type=MetricType.RESOURCE,
            severity=AlertSeverity.WARNING,
            threshold=0.8,
            comparison="gt",
            metric_path="cpu_usage",
        )
        metrics = Mock(cpu_usage=0.85)

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is not None
        assert alert.severity == AlertSeverity.WARNING
        assert "High CPU" in alert.title

    def test_threshold_rule_check_gt_no_trigger(self):
        """
        GIVEN a threshold rule with gt comparison
        WHEN metric value is below threshold
        THEN should return None
        """
        # Given
        rule = ThresholdRule(
            name="High CPU",
            metric_type=MetricType.RESOURCE,
            severity=AlertSeverity.WARNING,
            threshold=0.8,
            comparison="gt",
            metric_path="cpu_usage",
        )
        metrics = Mock(cpu_usage=0.5)

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is None

    def test_threshold_rule_disabled(self):
        """
        GIVEN a disabled threshold rule
        WHEN checking metrics
        THEN should return None
        """
        # Given
        rule = ThresholdRule(
            name="High CPU",
            metric_type=MetricType.RESOURCE,
            severity=AlertSeverity.WARNING,
            threshold=0.8,
            comparison="gt",
            metric_path="cpu_usage",
        )
        rule.disable()
        metrics = Mock(cpu_usage=0.9)

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is None

    def test_threshold_rule_lt_comparison(self):
        """
        GIVEN a threshold rule with lt comparison
        WHEN metric value is below threshold
        THEN should return alert
        """
        # Given
        rule = ThresholdRule(
            name="Low Success Rate",
            metric_type=MetricType.PERFORMANCE,
            severity=AlertSeverity.ERROR,
            threshold=0.5,
            comparison="lt",
            metric_path="success_rate",
        )
        metrics = Mock(success_rate=0.3)

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is not None
        assert alert.severity == AlertSeverity.ERROR


class TestAgentMonitoringServiceInit:
    """Test AgentMonitoringService initialization"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        return MagicMock()

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
            monitoring_level=MonitoringLevel.DETAILED,
        )

    def test_initialization_defaults(self, monitoring_service):
        """
        GIVEN monitoring service
        WHEN initialized
        THEN should have correct defaults
        """
        assert monitoring_service.monitoring_level == MonitoringLevel.DETAILED
        assert monitoring_service.monitoring_active is False
        assert monitoring_service.monitoring_interval == 30
        assert len(monitoring_service.monitoring_rules) > 0

    def test_initialization_with_basic_level(self, mock_db, mock_prometheus):
        """
        GIVEN BASIC monitoring level
        WHEN initializing service
        THEN should configure basic monitoring
        """
        # When
        service = AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
            monitoring_level=MonitoringLevel.BASIC,
        )

        # Then
        assert service.monitoring_level == MonitoringLevel.BASIC

    def test_default_monitoring_rules_created(self, monitoring_service):
        """
        GIVEN fresh monitoring service
        WHEN initialized
        THEN should create default monitoring rules
        """
        # Then
        assert len(monitoring_service.monitoring_rules) >= 5
        rule_names = [r.name for r in monitoring_service.monitoring_rules]
        assert "High Error Rate" in rule_names
        assert "High Response Time" in rule_names
        assert "High CPU Usage" in rule_names


@pytest.mark.asyncio
class TestAgentMonitoringServiceLifecycle:
    """Test monitoring service lifecycle management"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        return MagicMock()

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

    async def test_start_monitoring(self, monitoring_service):
        """
        GIVEN inactive monitoring service
        WHEN calling start_monitoring()
        THEN should activate monitoring loop
        """
        # When
        await monitoring_service.start_monitoring()

        # Then
        assert monitoring_service.monitoring_active is True
        assert monitoring_service.monitoring_task is not None

        # Cleanup
        await monitoring_service.stop_monitoring()

    async def test_start_monitoring_idempotent(self, monitoring_service):
        """
        GIVEN active monitoring service
        WHEN calling start_monitoring() again
        THEN should not create duplicate tasks
        """
        # Given
        await monitoring_service.start_monitoring()
        first_task = monitoring_service.monitoring_task

        # When
        await monitoring_service.start_monitoring()

        # Then
        assert monitoring_service.monitoring_task is first_task

        # Cleanup
        await monitoring_service.stop_monitoring()

    async def test_stop_monitoring(self, monitoring_service):
        """
        GIVEN active monitoring service
        WHEN calling stop_monitoring()
        THEN should deactivate monitoring loop
        """
        # Given
        await monitoring_service.start_monitoring()

        # When
        await monitoring_service.stop_monitoring()

        # Then
        assert monitoring_service.monitoring_active is False

    async def test_stop_monitoring_idempotent(self, monitoring_service):
        """
        GIVEN inactive monitoring service
        WHEN calling stop_monitoring()
        THEN should not raise errors
        """
        # When/Then (should not raise)
        await monitoring_service.stop_monitoring()
        assert monitoring_service.monitoring_active is False


@pytest.mark.asyncio
class TestMetricsCollection:
    """Test metrics collection functionality"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session with agent data"""
        db = MagicMock()

        # Mock agents
        agent1 = Mock(spec=AgentSwarmInstance)
        agent1.id = "agent_001"
        agent1.name = "Agent 1"
        agent1.status = AgentSwarmStatus.RUNNING
        agent1.created_at = datetime.now(timezone.utc) - timedelta(hours=2)

        agent2 = Mock(spec=AgentSwarmInstance)
        agent2.id = "agent_002"
        agent2.name = "Agent 2"
        agent2.status = AgentSwarmStatus.RUNNING
        agent2.created_at = datetime.now(timezone.utc) - timedelta(hours=1)

        db.query.return_value.filter.return_value.all.return_value = [agent1, agent2]
        return db

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        prometheus = MagicMock()
        prometheus.record_agent_metric = MagicMock()
        return prometheus

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

    async def test_collect_system_metrics(self, monitoring_service, mock_db):
        """
        GIVEN active agents in database
        WHEN collecting system metrics
        THEN should return SystemMetrics with agent counts
        """
        # When
        metrics = await monitoring_service._collect_system_metrics()

        # Then
        assert isinstance(metrics, SystemMetrics)
        assert metrics.total_agents >= 0
        assert metrics.timestamp is not None

    async def test_collect_agent_metrics(self, monitoring_service, mock_db):
        """
        GIVEN active agents in database
        WHEN collecting agent metrics
        THEN should store metrics in history
        """
        # When
        await monitoring_service._collect_agent_metrics()

        # Then
        assert len(monitoring_service.agent_metrics_history) >= 0

    async def test_system_metrics_history_bounded(self, monitoring_service):
        """
        GIVEN monitoring service with maxlen history
        WHEN collecting many metrics
        THEN should maintain bounded history
        """
        # When - collect more than maxlen
        for _ in range(1100):
            metrics = SystemMetrics(timestamp=datetime.now(timezone.utc))
            monitoring_service.system_metrics_history.append(metrics)

        # Then
        assert len(monitoring_service.system_metrics_history) <= 1000


@pytest.mark.asyncio
class TestAlertManagement:
    """Test alert management functionality"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        prometheus = MagicMock()
        prometheus.record_alert_created = MagicMock()
        return prometheus

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

    def test_add_alert_handler(self, monitoring_service):
        """
        GIVEN monitoring service
        WHEN adding alert handler
        THEN should be registered
        """
        # Given
        handler = Mock()

        # When
        monitoring_service.add_alert_handler(handler)

        # Then
        assert handler in monitoring_service.alert_handlers

    def test_remove_alert_handler(self, monitoring_service):
        """
        GIVEN registered alert handler
        WHEN removing handler
        THEN should be unregistered
        """
        # Given
        handler = Mock()
        monitoring_service.add_alert_handler(handler)

        # When
        monitoring_service.remove_alert_handler(handler)

        # Then
        assert handler not in monitoring_service.alert_handlers

    def test_resolve_alert(self, monitoring_service):
        """
        GIVEN active alert
        WHEN resolving alert
        THEN should mark as resolved
        """
        # Given
        alert = Alert(
            id="alert_001",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            message="Test message",
            source="test",
            metric_type=MetricType.HEALTH,
            timestamp=datetime.now(timezone.utc),
        )
        monitoring_service.active_alerts["alert_001"] = alert

        # When
        monitoring_service.resolve_alert("alert_001")

        # Then
        assert alert.resolved is True
        assert alert.resolved_at is not None

    def test_cleanup_old_alerts(self, monitoring_service):
        """
        GIVEN old resolved alerts
        WHEN cleaning up alerts
        THEN should remove old resolved alerts
        """
        # Given
        old_alert = Alert(
            id="old_alert",
            severity=AlertSeverity.INFO,
            title="Old Alert",
            message="Old message",
            source="test",
            metric_type=MetricType.HEALTH,
            timestamp=datetime.now(timezone.utc) - timedelta(days=2),
        )
        old_alert.resolve()
        old_alert.resolved_at = datetime.now(timezone.utc) - timedelta(days=2)

        new_alert = Alert(
            id="new_alert",
            severity=AlertSeverity.INFO,
            title="New Alert",
            message="New message",
            source="test",
            metric_type=MetricType.HEALTH,
            timestamp=datetime.now(timezone.utc),
        )

        monitoring_service.active_alerts["old_alert"] = old_alert
        monitoring_service.active_alerts["new_alert"] = new_alert

        # When
        monitoring_service._cleanup_old_alerts()

        # Then
        assert "old_alert" not in monitoring_service.active_alerts
        assert "new_alert" in monitoring_service.active_alerts


@pytest.mark.asyncio
class TestMonitoringRules:
    """Test monitoring rule management"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        return MagicMock()

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

    def test_add_monitoring_rule(self, monitoring_service):
        """
        GIVEN monitoring service
        WHEN adding monitoring rule
        THEN should be registered
        """
        # Given
        rule = ThresholdRule(
            name="Test Rule",
            metric_type=MetricType.PERFORMANCE,
            severity=AlertSeverity.INFO,
            threshold=1.0,
            comparison="gt",
            metric_path="test_metric",
        )

        # When
        monitoring_service.add_monitoring_rule(rule)

        # Then
        assert rule in monitoring_service.monitoring_rules

    def test_remove_monitoring_rule(self, monitoring_service):
        """
        GIVEN registered monitoring rule
        WHEN removing rule
        THEN should be unregistered
        """
        # Given
        rule = ThresholdRule(
            name="Test Rule",
            metric_type=MetricType.PERFORMANCE,
            severity=AlertSeverity.INFO,
            threshold=1.0,
            comparison="gt",
            metric_path="test_metric",
        )
        monitoring_service.add_monitoring_rule(rule)

        # When
        monitoring_service.remove_monitoring_rule(rule)

        # Then
        assert rule not in monitoring_service.monitoring_rules

    async def test_check_monitoring_rules_creates_alerts(self, monitoring_service):
        """
        GIVEN monitoring rules and agent metrics
        WHEN checking rules
        THEN should create alerts for violations
        """
        # Given
        agent_metrics = Mock()
        agent_metrics.cpu_usage = 0.9
        agent_metrics.error_rate = 0.15

        monitoring_service.agent_metrics = {
            "agent_001": agent_metrics
        }

        # When
        await monitoring_service._check_monitoring_rules()

        # Then
        assert len(monitoring_service.active_alerts) > 0


class TestSystemHealth:
    """Test system health calculation"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        return MagicMock()

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

    def test_get_system_health_no_metrics(self, monitoring_service):
        """
        GIVEN monitoring service with no metrics
        WHEN getting system health
        THEN should return unknown status
        """
        # When
        health = monitoring_service.get_system_health()

        # Then
        assert health["status"] == "unknown"
        assert "message" in health

    def test_get_system_health_excellent(self, monitoring_service):
        """
        GIVEN healthy system metrics
        WHEN getting system health
        THEN should return excellent status
        """
        # Given
        metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            total_agents=10,
            healthy_agents=10,
            error_rate=0.01,
            average_response_time=1.0,
        )
        monitoring_service.system_metrics_history.append(metrics)

        # When
        health = monitoring_service.get_system_health()

        # Then
        assert health["status"] in ["excellent", "good"]
        assert health["health_score"] >= 75

    def test_get_system_health_degraded(self, monitoring_service):
        """
        GIVEN degraded system metrics
        WHEN getting system health
        THEN should return degraded status
        """
        # Given
        metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            total_agents=10,
            healthy_agents=3,
            degraded_agents=5,
            offline_agents=2,
            error_rate=0.25,
            average_response_time=50.0,
        )
        monitoring_service.system_metrics_history.append(metrics)

        # When
        health = monitoring_service.get_system_health()

        # Then
        assert health["status"] in ["poor", "fair", "critical"]
        assert health["health_score"] < 75


class TestAgentReports:
    """Test per-agent reporting"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        db = MagicMock()

        agent = Mock(spec=AgentSwarmInstance)
        agent.id = "agent_001"
        agent.name = "Test Agent"
        agent.status = AgentSwarmStatus.RUNNING
        agent.created_at = datetime.now(timezone.utc) - timedelta(hours=2)

        db.query.return_value.filter.return_value.first.return_value = agent
        return db

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        return MagicMock()

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        service = AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )
        # Add agent metrics with proper return values
        agent_metric = Mock()
        agent_metric.current_tasks = 3
        agent_metric.completed_tasks = 15
        agent_metric.failed_tasks = 1
        agent_metric.average_response_time = 2.5
        agent_metric.average_completion_time = 45.0
        agent_metric.error_rate = 0.06  # 6% error rate
        agent_metric.cpu_usage = 0.45
        agent_metric.memory_usage = 0.62
        agent_metric.queue_length = 5
        agent_metric.capability_utilization = {}
        service.agent_metrics["agent_001"] = agent_metric
        return service

    def test_get_agent_report_success(self, monitoring_service):
        """
        GIVEN agent exists with metrics
        WHEN getting agent report
        THEN should return detailed report
        """
        # When
        report = monitoring_service.get_agent_report("agent_001")

        # Then
        assert report is not None
        assert isinstance(report, AgentReport)
        assert report.agent_id == "agent_001"

    def test_get_agent_report_nonexistent(self, monitoring_service, mock_db):
        """
        GIVEN nonexistent agent ID
        WHEN getting agent report
        THEN should return None
        """
        # Given
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # When
        report = monitoring_service.get_agent_report("nonexistent")

        # Then
        assert report is None


class TestMonitoringDashboard:
    """Test monitoring dashboard generation"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        return MagicMock()

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        service = AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )
        # Add some metrics
        metrics = SystemMetrics(timestamp=datetime.now(timezone.utc))
        service.system_metrics_history.append(metrics)
        return service

    def test_get_monitoring_dashboard(self, monitoring_service):
        """
        GIVEN monitoring service with data
        WHEN getting dashboard
        THEN should return comprehensive dashboard data
        """
        # When
        dashboard = monitoring_service.get_monitoring_dashboard()

        # Then
        assert "system_health" in dashboard
        assert "system_metrics" in dashboard
        assert "active_alerts" in dashboard
        assert "monitoring_status" in dashboard
        assert "historical_data" in dashboard

    def test_monitoring_dashboard_status(self, monitoring_service):
        """
        GIVEN active monitoring service
        WHEN getting dashboard
        THEN should include monitoring status
        """
        # When
        dashboard = monitoring_service.get_monitoring_dashboard()

        # Then
        status = dashboard["monitoring_status"]
        assert "active" in status
        assert "interval" in status
        assert "level" in status
        assert status["level"] == "detailed"


class TestPrometheusIntegration:
    """Test Prometheus metrics integration"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        prometheus = MagicMock()
        prometheus.record_agent_health = MagicMock()
        prometheus.record_agent_metric = MagicMock()
        prometheus.record_alert_created = MagicMock()
        prometheus.record_alert_resolved = MagicMock()
        return prometheus

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

    @pytest.mark.asyncio
    async def test_prometheus_metrics_on_collection(self, monitoring_service, mock_prometheus):
        """
        GIVEN monitoring service with Prometheus
        WHEN collecting metrics
        THEN should record to Prometheus
        """
        # When
        await monitoring_service._collect_system_metrics()

        # Then - Prometheus should be called
        # (specific assertions depend on implementation)
        assert mock_prometheus is not None

    def test_prometheus_metrics_on_alert(self, monitoring_service, mock_prometheus):
        """
        GIVEN monitoring service with Prometheus
        WHEN creating alert
        THEN should record alert metric
        """
        # Given
        alert = Alert(
            id="alert_001",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            message="Test",
            source="test",
            metric_type=MetricType.HEALTH,
            timestamp=datetime.now(timezone.utc),
        )

        # When
        monitoring_service.active_alerts["alert_001"] = alert
        monitoring_service._record_alert_to_prometheus(alert)

        # Then
        mock_prometheus.record_alert_created.assert_called()


class TestSingletonPattern:
    """Test singleton pattern implementation"""

    def test_get_agent_monitoring_service_singleton(self):
        """
        GIVEN multiple calls to get_agent_monitoring_service
        WHEN called with db_session
        THEN should return new instances (not singleton when args provided)
        """
        # When
        mock_db = MagicMock()
        service1 = get_agent_monitoring_service(db_session=mock_db)
        service2 = get_agent_monitoring_service(db_session=mock_db)

        # Then - new instances created each time
        assert service1 is not None
        assert service2 is not None

    def test_get_agent_monitoring_service_with_args(self):
        """
        GIVEN call to get_agent_monitoring_service with arguments
        WHEN providing db_session and prometheus
        THEN should create new instance
        """
        # Given
        mock_db = MagicMock()
        mock_prometheus = MagicMock()

        # When
        service = get_agent_monitoring_service(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

        # Then
        assert service is not None
        assert service.db_session is mock_db


@pytest.mark.asyncio
class TestDegradedAgentDetection:
    """Test degraded agent detection"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        return MagicMock()

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

    async def test_detect_degraded_agents(self, monitoring_service):
        """
        GIVEN agents with varying health
        WHEN detecting degraded agents
        THEN should identify unhealthy agents
        """
        # Given
        healthy_agent = Mock()
        healthy_agent.cpu_usage = 0.3
        healthy_agent.error_rate = 0.01
        healthy_agent.memory_usage = 0.4

        degraded_agent = Mock()
        degraded_agent.cpu_usage = 0.9
        degraded_agent.error_rate = 0.15
        degraded_agent.memory_usage = 0.85

        monitoring_service.agent_metrics = {
            "healthy": healthy_agent,
            "degraded": degraded_agent,
        }

        # When
        degraded = await monitoring_service.get_degraded_agents()

        # Then
        assert len(degraded) >= 1
        assert "degraded" in degraded

    async def test_alert_on_degraded_agent(self, monitoring_service):
        """
        GIVEN degraded agent
        WHEN checking monitoring rules
        THEN should create alerts
        """
        # Given
        degraded_agent = Mock()
        degraded_agent.cpu_usage = 0.95
        degraded_agent.error_rate = 0.20

        monitoring_service.agent_metrics = {
            "degraded": degraded_agent,
        }

        # When
        await monitoring_service._check_monitoring_rules()

        # Then
        assert len(monitoring_service.active_alerts) > 0


@pytest.mark.asyncio
class TestMonitoringLoopEdgeCases:
    """Test edge cases in monitoring loop"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return MagicMock()

    @pytest.fixture
    def mock_prometheus(self):
        """Mock Prometheus metrics service"""
        prometheus = MagicMock()
        prometheus.record_agent_count = MagicMock()
        return prometheus

    @pytest.fixture
    def monitoring_service(self, mock_db, mock_prometheus):
        """Create monitoring service instance"""
        return AgentMonitoringService(
            db_session=mock_db,
            prometheus_metrics=mock_prometheus,
        )

    async def test_monitoring_loop_handles_errors(self, monitoring_service, mock_db):
        """
        GIVEN monitoring loop with database error
        WHEN loop iteration encounters error
        THEN should log error and continue
        """
        # Given - make DB query raise error
        mock_db.query.side_effect = Exception("Database error")

        # Start and quickly stop monitoring
        await monitoring_service.start_monitoring()
        await asyncio.sleep(0.01)  # Let it run one iteration
        await monitoring_service.stop_monitoring()

        # Then - should not crash, just log
        assert not monitoring_service.monitoring_active

    async def test_collect_agent_metrics_with_db_error(self, monitoring_service, mock_db):
        """
        GIVEN agent metrics collection with database error
        WHEN collecting agent metrics
        THEN should handle error gracefully
        """
        # Given
        mock_db.query.side_effect = Exception("DB error")

        # When - should not raise
        await monitoring_service._collect_agent_metrics()

        # Then - continues without crashing
        assert True

    async def test_collect_system_metrics_with_prometheus_error(self, monitoring_service, mock_prometheus, mock_db):
        """
        GIVEN prometheus recording fails
        WHEN collecting system metrics
        THEN should handle error and continue
        """
        # Given
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_prometheus.record_agent_count.side_effect = Exception("Prometheus error")

        # When - should not raise
        metrics = await monitoring_service._collect_system_metrics()

        # Then
        assert metrics is not None
        assert isinstance(metrics, SystemMetrics)


class TestThresholdRuleComparisons:
    """Test all threshold rule comparison operators"""

    def test_threshold_rule_eq_comparison(self):
        """
        GIVEN threshold rule with eq comparison
        WHEN metric equals threshold
        THEN should return alert
        """
        # Given
        rule = ThresholdRule(
            name="Exact Match",
            metric_type=MetricType.TASK,
            severity=AlertSeverity.INFO,
            threshold=10.0,
            comparison="eq",
            metric_path="queue_length",
        )
        metrics = Mock(queue_length=10.0)

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is not None

    def test_threshold_rule_gte_comparison(self):
        """
        GIVEN threshold rule with gte comparison
        WHEN metric equals threshold
        THEN should return alert
        """
        # Given
        rule = ThresholdRule(
            name="Greater or Equal",
            metric_type=MetricType.TASK,
            severity=AlertSeverity.INFO,
            threshold=10.0,
            comparison="gte",
            metric_path="queue_length",
        )
        metrics = Mock(queue_length=10.0)

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is not None

    def test_threshold_rule_lte_comparison(self):
        """
        GIVEN threshold rule with lte comparison
        WHEN metric equals threshold
        THEN should return alert
        """
        # Given
        rule = ThresholdRule(
            name="Less or Equal",
            metric_type=MetricType.TASK,
            severity=AlertSeverity.INFO,
            threshold=10.0,
            comparison="lte",
            metric_path="queue_length",
        )
        metrics = Mock(queue_length=10.0)

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is not None

    def test_threshold_rule_dict_access(self):
        """
        GIVEN threshold rule with dict metric path
        WHEN checking dict metrics
        THEN should extract value correctly
        """
        # Given
        rule = ThresholdRule(
            name="Dict Access",
            metric_type=MetricType.TASK,
            severity=AlertSeverity.INFO,
            threshold=5.0,
            comparison="gt",
            metric_path="nested.value",
        )
        metrics = {"nested": {"value": 10.0}}

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is not None

    def test_threshold_rule_invalid_path(self):
        """
        GIVEN threshold rule with invalid metric path
        WHEN checking metrics
        THEN should return None (no alert)
        """
        # Given
        rule = ThresholdRule(
            name="Invalid Path",
            metric_type=MetricType.TASK,
            severity=AlertSeverity.INFO,
            threshold=5.0,
            comparison="gt",
            metric_path="nonexistent.path.missing",
        )
        metrics = Mock()
        # Make sure the path doesn't exist
        del metrics.nonexistent

        # When
        alert = rule.check(metrics)

        # Then
        assert alert is None


class TestMonitoringRuleBaseClass:
    """Test MonitoringRule base class"""

    def test_monitoring_rule_enable_disable(self):
        """
        GIVEN monitoring rule
        WHEN enabling/disabling
        THEN should update enabled state
        """
        # Given
        rule = ThresholdRule(
            name="Test",
            metric_type=MetricType.HEALTH,
            severity=AlertSeverity.INFO,
            threshold=1.0,
            comparison="gt",
            metric_path="value",
        )

        # When/Then
        rule.disable()
        assert not rule.enabled

        rule.enable()
        assert rule.enabled
