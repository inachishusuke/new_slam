"""Hardware and storage monitor with safety action triggers."""

from __future__ import annotations

import logging
import re
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
        self.smart_device = self._validate_smart_device(str(config.get('smart_device', '/dev/nvme0n1')))


    @staticmethod
    def _validate_smart_device(device: str) -> str:
        if not re.fullmatch(r"/dev/[A-Za-z0-9._:-]+", device):
            raise ValueError(f'Invalid smart_device path: {device}')
        return device

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
        result = subprocess.run(['smartctl', '-H', self.smart_device], check=False, capture_output=True, text=True)

        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()
        output_upper = stdout.upper()

        if result.returncode != 0 and not any(token in output_upper for token in ('PASSED', 'OK', 'FAILED')):
            self.logger.warning(
                'SMART health check unavailable for %s (rc=%s): %s',
                self.smart_device,
                result.returncode,
                stderr or stdout,
            )
            return True

        if 'FAILED' in output_upper:
            self.logger.error(
                'SMART reports failing health for %s: %s',
                self.smart_device,
                stdout or stderr,
            )
            return False

        if 'PASSED' in output_upper or 'OK' in output_upper:
            return True

        self.logger.warning(
            'SMART health status unknown for %s: %s',
            self.smart_device,
            stdout or stderr,
        )
        return True

    def _read_undervoltage(self) -> bool:
        result = subprocess.run(['vcgencmd', 'get_throttled'], check=False, capture_output=True, text=True)
        if result.returncode != 0:
            self.logger.warning('Undervoltage monitor unavailable: %s', result.stderr.strip())
            return False
        value = result.stdout.strip().split('=')[-1]
        return value not in {'0x0', '0'}
