import time
from unittest.mock import patch, MagicMock

from tools.system_metrics import (
    get_cpu_usage,
    get_memory_usage,
    get_memory_total,
    get_disk_total,
    get_uptime,
    get_status,
    get_all_metrics,
    _SKIP_FSTYPES,
)


class TestGetCpuUsage:
    @patch("tools.system_metrics.psutil")
    def test_returns_percentage(self, mock_psutil):
        mock_psutil.cpu_percent.return_value = 25.5

        assert get_cpu_usage() == 25.5
        mock_psutil.cpu_percent.assert_called_with(interval=None)


class TestGetMemoryUsage:
    @patch("tools.system_metrics.psutil")
    def test_returns_gb(self, mock_psutil):
        mock_psutil.virtual_memory.return_value = MagicMock(
            used=2 * 1024 * 1024 * 1024  # 2 GB
        )

        assert get_memory_usage() == 2.0


class TestGetMemoryTotal:
    def test_returns_cached_value(self):
        """Returns the module-level cached total."""
        result = get_memory_total()
        assert isinstance(result, float)
        assert result > 0


class TestGetDiskTotal:
    def test_returns_cached_value(self):
        """Returns the module-level cached total."""
        result = get_disk_total()
        assert isinstance(result, float)
        assert result >= 0


class TestGetUptime:
    def test_returns_positive_int(self):
        """Uptime is a positive integer."""
        result = get_uptime()
        assert isinstance(result, int)
        assert result >= 0

    def test_increases_over_time(self):
        """Uptime increases between calls."""
        t1 = get_uptime()
        time.sleep(0.01)
        t2 = get_uptime()
        assert t2 >= t1


class TestGetStatus:
    def test_returns_active(self):
        assert get_status() == "active"


class TestGetAllMetrics:
    @patch("tools.system_metrics.get_cpu_usage", return_value=10.0)
    @patch("tools.system_metrics.get_memory_usage", return_value=2.0)
    @patch("tools.system_metrics.get_memory_total", return_value=8.0)
    @patch("tools.system_metrics.get_disk_usage", return_value=20.0)
    @patch("tools.system_metrics.get_disk_total", return_value=100.0)
    @patch("tools.system_metrics.get_uptime", return_value=3600)
    @patch("tools.system_metrics.get_status", return_value="active")
    def test_returns_all_fields(self, *_mocks):
        result = get_all_metrics()

        assert result == {
            "cpu_usage": 10.0,
            "memory_usage": 2.0,
            "memory_total": 8.0,
            "disk_usage": 20.0,
            "disk_total": 100.0,
            "uptime": 3600,
            "status": "active",
        }

    def test_returns_correct_keys(self):
        """Real call returns all expected keys."""
        result = get_all_metrics()

        expected_keys = {
            "cpu_usage", "memory_usage", "memory_total",
            "disk_usage", "disk_total", "uptime", "status",
        }
        assert set(result.keys()) == expected_keys


class TestSkipFstypes:
    def test_contains_common_virtual_fstypes(self):
        """Verify common virtual fstypes are in the skip list."""
        assert "tmpfs" in _SKIP_FSTYPES
        assert "overlay" in _SKIP_FSTYPES
        assert "proc" in _SKIP_FSTYPES
        assert "sysfs" in _SKIP_FSTYPES
