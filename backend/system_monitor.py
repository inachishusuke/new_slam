"""Hardware and storage monitor with safety action triggers."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HealthState:
    cpu_temp_c: float
    free_disk_gb: float
    smart_ok: bool
    undervoltage: bool


class SystemMonitor:
    def __init__(self, config: dict, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.data_dir = Path(config['data_dir'])
        self.max_cpu_temp_c = float(config['max_cpu_temp_c'])
        self.min_free_disk_gb = float(config['min_free_disk_gb'])

    def collect(self) -> HealthState:
        return HealthState(
            cpu_temp_c=self._read_cpu_temp(),
            free_disk_gb=self._disk_free_gb(),
            smart_ok=self._smart_health_ok(),
            undervoltage=self._read_undervoltage(),
        )

    def evaluate(self, state: HealthState) -> list[str]:
        actions: list[str] = []
        if state.cpu_temp_c > self.max_cpu_temp_c:
            actions.append('overheat_shutdown')
        if not state.smart_ok:
            actions.append('ssd_failure_shutdown')
        if state.free_disk_gb < self.min_free_disk_gb:
            actions.append('disk_full_stop_recording')
        return actions

    def _read_cpu_temp(self) -> float:
        thermal_path = Path('/sys/class/thermal/thermal_zone0/temp')
        if not thermal_path.exists():
            return 0.0
        raw = thermal_path.read_text(encoding='utf-8').strip()
        return float(raw) / 1000.0

    def _disk_free_gb(self) -> float:
        usage = shutil.disk_usage(self.data_dir)
        return usage.free / (1024 ** 3)

    def _smart_health_ok(self) -> bool:
        cmd = ['bash', '-lc', "smartctl -H /dev/nvme0n1 | grep -E 'PASSED|OK'"]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            self.logger.error('SMART check failed: %s', result.stderr.strip())
            return False
        return True

    def _read_undervoltage(self) -> bool:
        cmd = ['bash', '-lc', 'vcgencmd get_throttled']
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            self.logger.warning('Undervoltage monitor unavailable: %s', result.stderr.strip())
            return False
        value = result.stdout.strip().split('=')[-1]
        return value not in {'0x0', '0'}
