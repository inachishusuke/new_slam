"""Insta360 X4/X5 camera API manager."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class CameraProfile:
    model: str
    api_base_url: str
    timeout_sec: int


class CameraManager:
    """Wrapper around Insta360 HTTP API for X4/X5 cameras."""

    def __init__(self, config: dict[str, Any], logger: logging.Logger) -> None:
        self.logger = logger
        camera_cfg = config.get('insta360', {})
        self.enabled = bool(camera_cfg.get('enabled', False))
        self.default_model = str(camera_cfg.get('default_model', 'x4'))
        self.profiles = self._parse_profiles(camera_cfg.get('models', {}))

    @staticmethod
    def _parse_profiles(models: dict[str, Any]) -> dict[str, CameraProfile]:
        profiles: dict[str, CameraProfile] = {}
        for model, spec in models.items():
            profiles[model] = CameraProfile(
                model=model,
                api_base_url=str(spec['api_base_url']).rstrip('/'),
                timeout_sec=int(spec.get('timeout_sec', 5)),
            )
        return profiles

    def camera_status(self, model: str | None = None) -> dict[str, Any]:
        profile = self._get_profile(model)
        response = self._post(profile, '/osc/state', payload={})
        return {'model': profile.model, 'connected': True, 'state': response}

    def start_recording(self, model: str | None = None) -> dict[str, Any]:
        profile = self._get_profile(model)
        payload = {'name': 'camera.startCapture', 'parameters': {}}
        response = self._post(profile, '/osc/commands/execute', payload)
        return {'model': profile.model, 'result': response}

    def stop_recording(self, model: str | None = None) -> dict[str, Any]:
        profile = self._get_profile(model)
        payload = {'name': 'camera.stopCapture', 'parameters': {}}
        response = self._post(profile, '/osc/commands/execute', payload)
        return {'model': profile.model, 'result': response}

    def take_photo(self, model: str | None = None) -> dict[str, Any]:
        profile = self._get_profile(model)
        payload = {'name': 'camera.takePicture', 'parameters': {}}
        response = self._post(profile, '/osc/commands/execute', payload)
        return {'model': profile.model, 'result': response}

    def _get_profile(self, model: str | None) -> CameraProfile:
        if not self.enabled:
            raise RuntimeError('Insta360 integration is disabled')
        target = model or self.default_model
        if target not in self.profiles:
            raise ValueError(f'Unsupported Insta360 model: {target}')
        return self.profiles[target]

    def _post(self, profile: CameraProfile, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f'{profile.api_base_url}{endpoint}'
        try:
            response = requests.post(url, json=payload, timeout=profile.timeout_sec)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            self.logger.error('Insta360 API request failed model=%s url=%s error=%s', profile.model, url, exc)
            raise RuntimeError(f'Insta360 API request failed: {exc}') from exc
