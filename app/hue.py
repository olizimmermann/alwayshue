#!/usr/bin/env python
"""Minimal Philips Hue v1 API client."""
import ipaddress
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import requests

TIMEOUT = 4  # seconds; without a timeout a dead bridge hangs the worker forever


class BridgeError(Exception):
    """Raised for unreachable bridges or Hue API errors. Never contains the API key."""


def _base_url(ip: str) -> str:
    try:
        if ipaddress.ip_address(ip).version == 6:
            ip = f"[{ip}]"
    except ValueError:
        pass  # hostname
    return f"http://{ip}/api"


def _parse(r: requests.Response):
    if not r.ok:
        raise BridgeError(f"bridge returned HTTP {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        raise BridgeError("bridge returned invalid JSON") from None
    if isinstance(data, list) and data and isinstance(data[0], dict) and "error" in data[0]:
        err = data[0]["error"]
        raise BridgeError(f"{err.get('description', 'bridge error')} (type {err.get('type')})")
    return data


def _request(method: str, url: str, **kw):
    try:
        return _parse(requests.request(method, url, timeout=TIMEOUT, **kw))
    except requests.RequestException as e:
        # str(e) would contain the URL including the API key -> only log the type
        raise BridgeError(f"cannot reach bridge ({type(e).__name__})") from None


def pair(ip: str, devicetype: str = "alwayshue#server") -> str:
    """Create a new API user. The bridge link button must be pressed first."""
    data = _request("POST", _base_url(ip), json={"devicetype": devicetype})
    try:
        return data[0]["success"]["username"]
    except (KeyError, IndexError, TypeError):
        raise BridgeError("unexpected pairing response") from None


class Bridge:
    def __init__(self, ip: str, token: str):
        if not ip or not token:
            raise BridgeError("bridge IP and API key must be configured")
        self.base = f"{_base_url(ip)}/{token}"

    def get(self, path: str):
        return _request("GET", f"{self.base}/{path}")

    def put(self, path: str, payload: dict):
        return _request("PUT", f"{self.base}/{path}", json=payload)

    def info(self) -> dict:
        cfg = self.get("config")
        return {k: cfg.get(k) for k in ("name", "modelid", "swversion", "apiversion", "bridgeid")}

    def lights(self) -> dict:
        return self.get("lights")

    def groups(self) -> dict:
        return self.get("groups")


def _on_payload(bri: int, use_color: bool, hue: int, sat: int) -> dict:
    payload = {"on": True, "bri": bri}
    if use_color:
        payload.update(hue=hue, sat=sat)
    return payload


class HueAction:
    def __init__(self, ip: str, token: str, lamps: Optional[List[int]] = None, group: Optional[int] = None,
                 bri: int = 254, use_color: bool = True, hue: int = 8895, sat: int = 89,
                 step_delay_ms: int = 0, reverse_off: bool = False):
        self.bridge = Bridge(ip, token)
        self.LAMPS = lamps or []
        self.step_delay = step_delay_ms / 1000
        self.reverse_off = reverse_off
        self.GROUP = group
        self.on_payload = _on_payload(bri, use_color, hue, sat)

    def _set_lamp(self, lamp: int, state: bool) -> bool:
        try:
            self.bridge.put(f"lights/{lamp}/state", self.on_payload if state else {"on": False})
            return True
        except BridgeError as e:
            logging.error("Lamp %s: %s", lamp, e)
            return False

    def trigger_lamps(self, state: Optional[bool] = None) -> dict:
        """Toggle (state=None) or explicitly switch all lamps of the room.

        Toggle logic: if any lamp of the room is on -> all off, else all on.
        Lamps are switched in list order (reversed when turning off and reverse_off is set),
        one every step_delay seconds; requests run in parallel so bridge latency doesn't add up.
        """
        if not self.LAMPS:
            return {"error": "No lamps defined"}
        all_lights = self.bridge.lights()  # one request instead of one per lamp
        any_on = any(all_lights.get(str(l), {}).get("state", {}).get("on") for l in self.LAMPS)
        new_state = (not any_on) if state is None else state
        order = self.LAMPS[::-1] if (not new_state and self.reverse_off) else self.LAMPS

        with ThreadPoolExecutor(max_workers=min(16, len(order))) as pool:
            futures = []
            for i, lamp in enumerate(order):
                if i and self.step_delay:
                    time.sleep(self.step_delay)
                futures.append(pool.submit(self._set_lamp, lamp, new_state))
            results = [f.result() for f in futures]
        failed = [l for l, ok in zip(order, results) if not ok]
        return {"state_old": any_on, "state_new": new_state, "lamps": order, "failed": failed}

    def trigger_group(self, state: Optional[bool] = None) -> dict:
        """Toggle (state=None) or explicitly switch a bridge group."""
        grp = self.bridge.get(f"groups/{self.GROUP}")
        current = grp.get("state", {}).get("any_on", grp.get("action", {}).get("on", False))
        new_state = (not current) if state is None else state
        self.bridge.put(f"groups/{self.GROUP}/action", self.on_payload if new_state else {"on": False})
        return {"state_old": current, "state_new": new_state, "group": self.GROUP}
