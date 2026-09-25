"""Persistent, validated configuration for alwayshue.

All settings live in DATA_DIR/config.json (written atomically, mode 0600).
On first start the file is seeded from the legacy environment variables
(apikey, ip, allowed_hosts) so existing deployments keep working.
"""
import ipaddress
import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

DATA_DIR = Path(os.getenv("ALWAYSHUE_DATA", "data"))
CONFIG_PATH = DATA_DIR / "config.json"

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
# Hue usernames are alphanumeric (plus '-'); anything else could inject into the URL path.
_API_KEY_RE = re.compile(r"^[A-Za-z0-9-]{0,64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{0,128}$")


def validate_bridge_host(value: str) -> str:
    """Accept only a bare IP address or hostname (no scheme, port, path)."""
    value = value.strip()
    if not value:
        return value
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if _HOSTNAME_RE.match(value):
        return value
    raise ValueError("must be a plain IP address or hostname")


def validate_host_entry(value: str) -> str:
    """Accept '*', a single IP or a CIDR network."""
    value = value.strip()
    if value == "*":
        return value
    try:
        return str(ipaddress.ip_network(value, strict=False))
    except ValueError:
        raise ValueError(f"'{value}' is not an IP address, CIDR network or '*'")


class LightSettings(BaseModel):
    bri: int = Field(254, ge=1, le=254)
    use_color: bool = True
    hue: int = Field(8895, ge=0, le=65535)
    sat: int = Field(89, ge=0, le=254)
    transition_ms: int = Field(400, ge=0, le=10000)  # fade time, 0 = instant (bridge default 400)


class Room(LightSettings):
    id: int = Field(ge=1, le=9999)
    name: str = Field("", max_length=64)
    lamps: List[int] = Field(default_factory=list, max_length=128)  # order = switching sequence
    step_delay_ms: int = Field(0, ge=0, le=1000)  # pause between lamps, 0 = all at once
    reverse_off: bool = False  # switch off in reverse order

    @field_validator("lamps")
    @classmethod
    def _lamps(cls, v: List[int]) -> List[int]:
        if any(not 1 <= lamp <= 9999 for lamp in v):
            raise ValueError("lamp ids must be between 1 and 9999")
        return list(dict.fromkeys(v))  # dedupe, keep order


class Group(LightSettings):
    id: int = Field(ge=1, le=9999)
    name: str = Field("", max_length=64)
    group: int = Field(0, ge=0, le=9999)
    use_color: bool = False


def _host_list(v: List[str]) -> List[str]:
    entries = [validate_host_entry(x) for x in v if x.strip()]
    if not entries:
        raise ValueError("at least one entry required ('*' allows everyone)")
    return ["*"] if "*" in entries else list(dict.fromkeys(entries))


class PublicSettings(BaseModel):
    """Settings editable via the UI (secrets handled separately)."""
    bridge_ip: str = ""
    allowed_hosts: List[str] = Field(default_factory=lambda: ["*"], max_length=64)
    admin_allowed_hosts: List[str] = Field(default_factory=lambda: ["*"], max_length=64)
    switch_token: str = ""
    rooms: List[Room] = Field(default_factory=list, max_length=256)
    groups: List[Group] = Field(default_factory=list, max_length=256)

    @field_validator("bridge_ip")
    @classmethod
    def _bridge(cls, v: str) -> str:
        return validate_bridge_host(v)

    @field_validator("allowed_hosts", "admin_allowed_hosts")
    @classmethod
    def _hosts(cls, v: List[str]) -> List[str]:
        return _host_list(v)

    @field_validator("switch_token")
    @classmethod
    def _switch_token(cls, v: str) -> str:
        v = v.strip()
        if not _TOKEN_RE.match(v):
            raise ValueError("only letters, digits, '-' and '_' allowed")
        if v and len(v) < 16:
            raise ValueError("must be empty or at least 16 characters")
        return v

    @model_validator(mode="after")
    def _unique_ids(self):
        for kind, items in (("room", self.rooms), ("group", self.groups)):
            ids = [i.id for i in items]
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {kind} id")
        return self


class Config(PublicSettings):
    api_key: str = ""
    admin_password_hash: str = ""

    @field_validator("api_key")
    @classmethod
    def _api_key(cls, v: str) -> str:
        v = v.strip()
        if not _API_KEY_RE.match(v):
            raise ValueError("invalid Hue API key format")
        return v


def _strip_comment(value: Optional[str]) -> str:
    # example.env style "value # comment" is not stripped by docker env_file
    return (value or "").split("#", 1)[0].strip()


def _seed_from_env() -> Config:
    hosts = [h for h in _strip_comment(os.getenv("allowed_hosts", "*")).split(",") if h.strip()] or ["*"]
    return Config(
        bridge_ip=_strip_comment(os.getenv("ip")),
        api_key=_strip_comment(os.getenv("apikey")),
        allowed_hosts=hosts,
        # Legacy hardcoded setup from earlier versions, kept so upgrades are seamless.
        rooms=[
            Room(id=1, name="Room 1", lamps=[22, 29, 27, 28, 17, 20, 18, 19, 16, 30, 15, 21, 24, 23], reverse_off=True),
            Room(id=2, name="Room 2", lamps=list(range(1, 15)), reverse_off=True),
        ],
        groups=[Group(id=1, name="Group 1", group=1)],
    )


class ConfigStore:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._config = self._load()

    def _load(self) -> Config:
        if self.path.exists():
            return Config.model_validate(json.loads(self.path.read_text()))
        cfg = _seed_from_env()
        self._write(cfg)
        logging.info("Created %s from environment defaults", self.path)
        return cfg

    def _write(self, cfg: Config) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(cfg.model_dump_json(indent=2))
        os.replace(tmp, self.path)

    def get(self) -> Config:
        return self._config

    def update(self, **changes) -> Config:
        with self._lock:
            data = self._config.model_dump()
            data.update(changes)
            cfg = Config.model_validate(data)
            self._write(cfg)
            self._config = cfg
            return cfg
