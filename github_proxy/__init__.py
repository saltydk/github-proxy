from github_proxy.dependencies import get_tel_collector
from github_proxy.dependencies import inject_tel_collector
from github_proxy.telemetry import TelemetryCollector
from github_proxy.views import blueprint

__all__ = [
    "blueprint",
    "get_tel_collector",
    "inject_tel_collector",
    "TelemetryCollector",
]
