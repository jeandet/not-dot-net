import pytest
from not_dot_net.config import DashboardConfig


async def test_dashboard_config_defaults():
    cfg = DashboardConfig()
    assert cfg.urgency_fresh_days == 2
    assert cfg.urgency_aging_days == 7
