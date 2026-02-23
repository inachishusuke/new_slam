"""FastAPI backend for industrial LiDAR SLAM control."""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ros_manager import RosManager
from system_monitor import HealthState, SystemMonitor
from watchdog_monitor import WatchdogMonitor

CONFIG_FILE = Path(__file__).with_name('config.yaml')


def setup_logger(log_dir: Path) -> logging.Logger:
    logger = logging.getLogger('lio_backend')
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / 'backend.log')
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
    handler.setFormatter(formatter)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(handler)
    logger.addHandler(stream)
    return logger


class Runtime:
    def __init__(self, config: dict[str, Any], logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.ros = RosManager(config, logger)
        self.monitor = SystemMonitor(config, logger)
        self.watchdog = WatchdogMonitor(config, self.ros, logger, self.on_watchdog_fault)
        self._stop_event = threading.Event()
        self._monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.last_state: HealthState | None = None

    def start(self) -> None:
        self.ros.start_ros()
        self.watchdog.start()
        self._monitor_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self.watchdog.stop()
        self.safe_shutdown_sequence()

    def monitor_loop(self) -> None:
        interval = float(self.config['monitor_interval_sec'])
        while not self._stop_event.is_set():
            try:
                self.last_state = self.monitor.collect()
                actions = self.monitor.evaluate(self.last_state)
                for action in actions:
                    self._handle_safety_action(action)
            except Exception as exc:
                self.logger.exception('Monitor loop failed: %s', exc)
            self._stop_event.wait(interval)

    def _handle_safety_action(self, action: str) -> None:
        if action == 'overheat_shutdown':
            self.logger.critical('Overheat detected. Triggering fail-safe shutdown.')
            self.ros.stop_recording()
            self.ros.save_map()
            self.ros.stop_ros()
            self._shutdown_os()
        elif action == 'ssd_failure_shutdown':
            self.logger.critical('SSD SMART failure detected. Triggering shutdown.')
            self.ros.stop_recording()
            self._shutdown_os()
        elif action == 'disk_full_stop_recording':
            self.logger.error('Disk free space below threshold. Stopping recording.')
            self.ros.stop_recording()

    def on_watchdog_fault(self, reason: str) -> None:
        self.logger.error('Watchdog fault: %s', reason)
        self.ros.restart_ros()

    def safe_shutdown_sequence(self) -> None:
        self.logger.info('Executing shutdown sequence')
        self.ros.stop_recording()
        self.ros.save_map()
        self.ros.stop_ros()

    def _shutdown_os(self) -> None:
        subprocess.run(['bash', '-lc', 'sudo shutdown -h now'], check=False)


def load_config() -> dict[str, Any]:
    with CONFIG_FILE.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


config = load_config()
logger = setup_logger(Path(config['logs_dir']))
runtime = Runtime(config, logger)

app = FastAPI(title='Industrial LIO System API', openapi_url='/api/openapi.json')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.mount('/ui', StaticFiles(directory=config['frontend_dir'], html=True), name='frontend')


@app.on_event('startup')
def startup() -> None:
    runtime.start()


@app.on_event('shutdown')
def shutdown() -> None:
    runtime.stop()


@app.get('/')
def root() -> FileResponse:
    return FileResponse(Path(config['frontend_dir']) / 'index.html')


@app.get('/api/status')
def status() -> dict[str, Any]:
    state = runtime.last_state or runtime.monitor.collect()
    return {
        'ros_running': runtime.ros.is_ros_running(),
        'recording': runtime.ros.record_process is not None and runtime.ros.record_process.poll() is None,
        'cpu_temp_c': state.cpu_temp_c,
        'free_disk_gb': state.free_disk_gb,
        'smart_ok': state.smart_ok,
        'undervoltage': state.undervoltage,
    }


@app.post('/api/record/start')
def record_start() -> dict[str, str]:
    success, message = runtime.ros.start_recording()
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {'message': message}


@app.post('/api/record/stop')
def record_stop() -> dict[str, str]:
    success, message = runtime.ros.stop_recording()
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {'message': message}


@app.post('/api/map/save')
def map_save() -> dict[str, str]:
    success, message = runtime.ros.save_map()
    if not success:
        raise HTTPException(status_code=500, detail=message)
    return {'message': message}


@app.get('/api/files')
def files() -> dict[str, list[str]]:
    maps = sorted(p.name for p in Path(config['maps_dir']).glob('*'))
    bags = sorted(p.name for p in Path(config['rosbag_dir']).glob('*'))
    logs = sorted(p.name for p in Path(config['logs_dir']).glob('*'))
    return {'maps': maps, 'rosbag': bags, 'logs': logs}


@app.post('/api/usb/transfer')
def usb_transfer() -> dict[str, str]:
    cmd = 'mkdir -p /media/usb_backup && rsync -a /opt/lio_system/data/ /media/usb_backup/'
    result = subprocess.run(['bash', '-lc', cmd], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip())
    return {'message': 'Transfer completed'}


@app.post('/api/system/shutdown')
def system_shutdown() -> dict[str, str]:
    runtime.safe_shutdown_sequence()
    runtime._shutdown_os()
    return {'message': 'Shutdown initiated'}


if __name__ == '__main__':
    uvicorn.run('main:app', host='0.0.0.0', port=8080, reload=False)
