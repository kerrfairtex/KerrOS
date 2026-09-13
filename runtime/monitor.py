"""
runtime/monitor.py
==================
Shim: proposed future path for runtime monitoring.
Current implementation: runtime/health.py and runtime/watchdog/.
"""

from runtime.health import HealthMonitor

__all__ = ["HealthMonitor"]
