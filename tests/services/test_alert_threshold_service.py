"""
Unit Tests for Alert Threshold Service

Tests for AlertThresholdConfig model validation, AlertThresholdService
CRUD operations, thread safety, and singleton behavior.

Epic E8-S4: Alert Threshold Configuration
Refs: #52
"""

import threading
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from backend.services.alert_threshold_service import (
    AlertThresholdConfig,
    AlertThresholdService,
    get_alert_threshold_service,
)


class TestAlertThresholdConfigModel:
    """Test AlertThresholdConfig Pydantic model validation"""

    def test_defaults_match_hardcoded_values(self):
        """
        GIVEN a new AlertThresholdConfig with no arguments
        WHEN checking default values
        THEN they should match the original hardcoded thresholds
        """
        config = AlertThresholdConfig()

        assert config.buffer_utilization == 80.0
        assert config.crash_count == 3
        assert config.revocation_rate == 50.0
        assert config.ip_pool_utilization == 90.0

    def test_updated_at_is_utc(self):
        """
        GIVEN a new AlertThresholdConfig
        WHEN checking updated_at timezone
        THEN it should be UTC
        """
        config = AlertThresholdConfig()

        assert config.updated_at.tzinfo is not None
        assert config.updated_at.tzinfo == timezone.utc

    def test_validates_buffer_utilization_range(self):
        """
        GIVEN buffer_utilization outside 0-100 range
        WHEN creating AlertThresholdConfig
        THEN it should raise ValidationError
        """
        with pytest.raises(Exception):
            AlertThresholdConfig(buffer_utilization=101.0)

        with pytest.raises(Exception):
            AlertThresholdConfig(buffer_utilization=-1.0)

    def test_validates_crash_count_non_negative(self):
        """
        GIVEN a negative crash_count
        WHEN creating AlertThresholdConfig
        THEN it should raise ValidationError
        """
        with pytest.raises(Exception):
            AlertThresholdConfig(crash_count=-1)

    def test_validates_revocation_rate_range(self):
        """
        GIVEN revocation_rate outside 0-100 range
        WHEN creating AlertThresholdConfig
        THEN it should raise ValidationError
        """
        with pytest.raises(Exception):
            AlertThresholdConfig(revocation_rate=101.0)

        with pytest.raises(Exception):
            AlertThresholdConfig(revocation_rate=-1.0)

    def test_validates_ip_pool_utilization_range(self):
        """
        GIVEN ip_pool_utilization outside 0-100 range
        WHEN creating AlertThresholdConfig
        THEN it should raise ValidationError
        """
        with pytest.raises(Exception):
            AlertThresholdConfig(ip_pool_utilization=101.0)

        with pytest.raises(Exception):
            AlertThresholdConfig(ip_pool_utilization=-1.0)

    def test_accepts_boundary_values(self):
        """
        GIVEN threshold values at exact boundaries (0.0 and 100.0)
        WHEN creating AlertThresholdConfig
        THEN it should succeed
        """
        config = AlertThresholdConfig(
            buffer_utilization=0.0,
            crash_count=0,
            revocation_rate=100.0,
            ip_pool_utilization=100.0,
        )

        assert config.buffer_utilization == 0.0
        assert config.crash_count == 0
        assert config.revocation_rate == 100.0
        assert config.ip_pool_utilization == 100.0


class TestGetThresholds:
    """Test AlertThresholdService.get_thresholds()"""

    def test_returns_defaults(self):
        """
        GIVEN a new AlertThresholdService
        WHEN calling get_thresholds
        THEN it should return default config values
        """
        service = AlertThresholdService()
        thresholds = service.get_thresholds()

        assert thresholds.buffer_utilization == 80.0
        assert thresholds.crash_count == 3
        assert thresholds.revocation_rate == 50.0
        assert thresholds.ip_pool_utilization == 90.0

    def test_returns_copy_not_reference(self):
        """
        GIVEN an AlertThresholdService
        WHEN calling get_thresholds twice
        THEN the returned objects should be different instances
        """
        service = AlertThresholdService()
        t1 = service.get_thresholds()
        t2 = service.get_thresholds()

        assert t1 is not t2
        assert t1.buffer_utilization == t2.buffer_utilization


class TestUpdateThresholds:
    """Test AlertThresholdService.update_thresholds()"""

    def test_update_single_field(self):
        """
        GIVEN an AlertThresholdService
        WHEN updating a single threshold field
        THEN only that field should change
        """
        service = AlertThresholdService()
        result = service.update_thresholds({"buffer_utilization": 95.0})

        assert result.buffer_utilization == 95.0
        assert result.crash_count == 3  # unchanged
        assert result.revocation_rate == 50.0  # unchanged
        assert result.ip_pool_utilization == 90.0  # unchanged

    def test_update_multiple_fields(self):
        """
        GIVEN an AlertThresholdService
        WHEN updating multiple threshold fields
        THEN all specified fields should change
        """
        service = AlertThresholdService()
        result = service.update_thresholds({
            "buffer_utilization": 70.0,
            "crash_count": 5,
        })

        assert result.buffer_utilization == 70.0
        assert result.crash_count == 5
        assert result.revocation_rate == 50.0  # unchanged
        assert result.ip_pool_utilization == 90.0  # unchanged

    def test_update_all_fields(self):
        """
        GIVEN an AlertThresholdService
        WHEN updating all threshold fields
        THEN all fields should change
        """
        service = AlertThresholdService()
        result = service.update_thresholds({
            "buffer_utilization": 60.0,
            "crash_count": 10,
            "revocation_rate": 30.0,
            "ip_pool_utilization": 85.0,
        })

        assert result.buffer_utilization == 60.0
        assert result.crash_count == 10
        assert result.revocation_rate == 30.0
        assert result.ip_pool_utilization == 85.0

    def test_update_refreshes_updated_at(self):
        """
        GIVEN an AlertThresholdService
        WHEN updating thresholds
        THEN updated_at should be refreshed to a newer timestamp
        """
        service = AlertThresholdService()
        before = service.get_thresholds().updated_at

        result = service.update_thresholds({"buffer_utilization": 75.0})

        assert result.updated_at >= before

    def test_update_ignores_unknown_fields(self):
        """
        GIVEN an AlertThresholdService
        WHEN updating with unknown field names
        THEN unknown fields should be silently ignored
        """
        service = AlertThresholdService()
        result = service.update_thresholds({
            "buffer_utilization": 75.0,
            "nonexistent_field": 999,
        })

        assert result.buffer_utilization == 75.0
        assert not hasattr(result, "nonexistent_field")

    def test_update_ignores_updated_at_override(self):
        """
        GIVEN an AlertThresholdService
        WHEN trying to set updated_at directly
        THEN the override should be ignored
        """
        service = AlertThresholdService()
        old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        result = service.update_thresholds({
            "buffer_utilization": 75.0,
            "updated_at": old_time,
        })

        assert result.updated_at != old_time
        assert result.updated_at.year >= 2026

    def test_update_rejects_invalid_value(self):
        """
        GIVEN an AlertThresholdService
        WHEN updating with an out-of-range value
        THEN it should raise a ValueError
        """
        service = AlertThresholdService()

        with pytest.raises(ValueError):
            service.update_thresholds({"buffer_utilization": 150.0})


class TestResetToDefaults:
    """Test AlertThresholdService.reset_to_defaults()"""

    def test_restores_defaults_after_modification(self):
        """
        GIVEN an AlertThresholdService with modified thresholds
        WHEN resetting to defaults
        THEN all values should return to original defaults
        """
        service = AlertThresholdService()
        service.update_thresholds({
            "buffer_utilization": 60.0,
            "crash_count": 10,
            "revocation_rate": 30.0,
            "ip_pool_utilization": 85.0,
        })

        result = service.reset_to_defaults()

        assert result.buffer_utilization == 80.0
        assert result.crash_count == 3
        assert result.revocation_rate == 50.0
        assert result.ip_pool_utilization == 90.0


class TestThreadSafety:
    """Test thread safety of AlertThresholdService"""

    def test_concurrent_updates_from_multiple_threads(self):
        """
        GIVEN an AlertThresholdService
        WHEN 10 threads update thresholds concurrently
        THEN no exceptions should be raised and final state should be valid
        """
        service = AlertThresholdService()
        errors = []

        def update_threshold(value):
            try:
                service.update_thresholds({"buffer_utilization": float(value)})
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=update_threshold, args=(i * 10,))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        result = service.get_thresholds()
        assert 0.0 <= result.buffer_utilization <= 100.0


class TestSingleton:
    """Test get_alert_threshold_service() singleton behavior"""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before and after each test"""
        import backend.services.alert_threshold_service as mod
        mod._alert_threshold_service_instance = None
        yield
        mod._alert_threshold_service_instance = None

    def test_returns_same_instance(self):
        """
        GIVEN get_alert_threshold_service called multiple times
        WHEN comparing returned instances
        THEN should return the same instance
        """
        service1 = get_alert_threshold_service()
        service2 = get_alert_threshold_service()

        assert service1 is service2

    def test_returns_correct_type(self):
        """
        GIVEN get_alert_threshold_service called
        WHEN checking return type
        THEN should return AlertThresholdService instance
        """
        service = get_alert_threshold_service()

        assert isinstance(service, AlertThresholdService)
