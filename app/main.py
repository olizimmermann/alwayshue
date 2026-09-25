import hmac
import ipaddress
import logging
import os
import secrets
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

import auth
import hue
from config import DATA_DIR, Config, ConfigStore, Group, LightSettings, PublicSettings, Room, validate_bridge_host

VERSION = "0.2.0"
STATIC_DIR = Path(__file__).parent / "static"
LOG_PATH = DATA_DIR / "app.log"
COOKIE = "alwayshue_session"
COOKIE_SECURE = os.getenv("cookie_secure", "false").lower() == "true"

# ---------- logging ----------
DATA_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[RotatingFileHandler(LOG_PATH, maxBytes=10 * 1024 * 1024, backupCount=3),
              logging.StreamHandler(sys.stdout)],
)

store = ConfigStore()
sessions = auth.SessionManager()


def _bootstrap_admin_password() -> None:
    if store.get().admin_password_hash:
        return
    pw = os.getenv("admin_password", "").strip()
    if len(pw) < auth.MIN_PASSWORD_LEN:
        pw = secrets.token_urlsafe(12)
        # stdout only (docker logs), deliberately not written to app.log
        print(f"\n*** alwayshue: generated initial admin password: {pw} ***\n"
              f"*** change it in the UI under Security. ***\n", flush=True)
    store.update(admin_password_hash=auth.hash_password(pw))


_bootstrap_admin_password()

app = FastAPI(title="alwayshue", version=VERSION, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/api/"):
        h["Cache-Control"] = "no-store"
    return response


# ---------- helpers ----------
def _norm_ip(value: str) -> str:
    """Canonical IP string ('::ffff:1.2.3.4' -> '1.2.3.4'); non-IPs are returned truncated."""
    value = value.strip()
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return value[:64]
    return str(ip.ipv4_mapped or ip) if ip.version == 6 else str(ip)


def _host_allowed(src_ip: str, allowed: List[str]) -> bool:
    if "*" in allowed:
        return True
    try:
        ip = ipaddress.ip_address(src_ip)
    except ValueError:
        return False
    return any(ip in ipaddress.ip_network(net) for net in allowed)


def _peer_ip(request: Request) -> str:
    return _norm_ip(request.client.host if request.client else "")


def client_ip(request: Request, trusted: Optional[List[str]] = None) -> str:
    """Real client IP. Forwarded headers are honoured only if the TCP peer is a trusted proxy.

    X-Forwarded-For is walked right-to-left, skipping trusted proxies; the first untrusted hop
    is the client. Entries left of it may be forged by the client and are ignored.
    """
    trusted = store.get().trusted_proxies if trusted is None else trusted
    peer = _peer_ip(request)
    if not trusted or not _host_allowed(peer, trusted):
        return peer
    xff = request.headers.get("x-forwarded-for", "")
    hops = [h for h in (x.strip() for x in xff[:2048].split(",")) if h][-20:]
    if not hops:
        real = request.headers.get("x-real-ip", "").strip()
        return _norm_ip(real) if real else peer
    for hop in reversed(hops):
        hop = _norm_ip(hop)
        if not _host_allowed(hop, trusted):
            return hop
    return _norm_ip(hops[0])


def _is_https(request: Request) -> bool:
    if COOKIE_SECURE or request.url.scheme == "https":
        return True
    trusted = store.get().trusted_proxies
    return bool(trusted) and _host_allowed(_peer_ip(request), trusted) and \
        request.headers.get("x-forwarded-proto", "").lower() == "https"


def _check_host(request: Request, allowed: List[str]) -> str:
    src_ip = client_ip(request)
    if not _host_allowed(src_ip, allowed):
        logging.warning("Unauthorized access attempt from %s to %s", src_ip, request.url.path)
        raise HTTPException(status_code=403, detail="Forbidden - Host not allowed")
    return src_ip


def _parse_state(state: Optional[str]) -> Optional[bool]:
    return {None: None, "toggle": None, "on": True, "off": False}[state]


def _light_kwargs(s: LightSettings) -> dict:
    return dict(bri=s.bri, use_color=s.use_color, hue=s.hue, sat=s.sat, transition_ms=s.transition_ms)


def _run(fn):
    try:
        return fn()
    except hue.BridgeError as e:
        logging.error("Bridge error: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


def _validation_error(e: Exception) -> HTTPException:
    if isinstance(e, ValidationError):
        detail = [{"loc": list(err["loc"]), "msg": err["msg"]} for err in e.errors(include_url=False)]
    else:
        detail = str(e)
    return HTTPException(status_code=422, detail=detail)


def _bridge(cfg: Config) -> hue.Bridge:
    return _run(lambda: hue.Bridge(cfg.bridge_ip, cfg.api_key))


# ---------- switch endpoints (called by Shelly relays) ----------
StateParam = Query(None, pattern="^(on|off|toggle)$")


def _switch_guard(request: Request, key: Optional[str]) -> str:
    cfg = store.get()
    src_ip = _check_host(request, cfg.allowed_hosts)
    if cfg.switch_token and not hmac.compare_digest((key or "").encode(), cfg.switch_token.encode()):
        logging.warning("Invalid switch key from %s", src_ip)
        raise HTTPException(status_code=403, detail="Forbidden - invalid key")
    return src_ip


@app.get("/room/{room_id}")
def control_room(room_id: int, request: Request, state: Optional[str] = StateParam, key: Optional[str] = None):
    src_ip = _switch_guard(request, key)
    cfg = store.get()
    room = next((r for r in cfg.rooms if r.id == room_id), None)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    logging.info("Room %s (%s) triggered by %s [%s]", room_id, room.name, src_ip, state or "toggle")
    action = _run(lambda: hue.HueAction(cfg.bridge_ip, cfg.api_key, lamps=room.lamps,
                                            step_delay_ms=room.step_delay_ms, reverse_off=room.reverse_off,
                                            **_light_kwargs(room)))
    return _run(lambda: action.trigger_lamps(_parse_state(state)))


@app.get("/group/{group_id}")
def control_group(group_id: int, request: Request, state: Optional[str] = StateParam, key: Optional[str] = None):
    src_ip = _switch_guard(request, key)
    cfg = store.get()
    group = next((g for g in cfg.groups if g.id == group_id), None)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    logging.info("Group %s (%s) triggered by %s [%s]", group_id, group.name, src_ip, state or "toggle")
    action = _run(lambda: hue.HueAction(cfg.bridge_ip, cfg.api_key, group=group.group, **_light_kwargs(group)))
    return _run(lambda: action.trigger_group(_parse_state(state)))


# ---------- admin auth ----------
def require_admin(request: Request) -> None:
    _check_host(request, store.get().admin_allowed_hosts)
    csrf = sessions.get(request.cookies.get(COOKIE))
    if not csrf:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if request.method not in ("GET", "HEAD"):
        sent = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(sent.encode(), csrf.encode()):
            raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def _set_session_cookie(request: Request, response: Response) -> str:
    token, csrf = sessions.create()
    response.set_cookie(COOKIE, token, max_age=auth.SESSION_TTL, httponly=True,
                        samesite="strict", secure=_is_https(request), path="/")
    return csrf


class LoginBody(BaseModel):
    password: str = Field(max_length=256)


class PasswordBody(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(min_length=auth.MIN_PASSWORD_LEN, max_length=256)


@app.get("/api/session")
def session_info(request: Request):
    src_ip = _check_host(request, store.get().admin_allowed_hosts)
    csrf = sessions.get(request.cookies.get(COOKIE))
    return {"authenticated": bool(csrf), "csrf": csrf, "version": VERSION, "client_ip": src_ip,
            "peer_ip": _peer_ip(request)}


@app.post("/api/login")
def login(body: LoginBody, request: Request, response: Response):
    src_ip = _check_host(request, store.get().admin_allowed_hosts)
    wait = sessions.locked_for(src_ip)
    if wait:
        raise HTTPException(status_code=429, detail=f"Too many failed attempts, retry in {wait}s")
    if not auth.verify_password(body.password, store.get().admin_password_hash):
        sessions.record_failure(src_ip)
        logging.warning("Failed admin login from %s", src_ip)
        raise HTTPException(status_code=401, detail="Wrong password")
    sessions.record_success(src_ip)
    logging.info("Admin login from %s", src_ip)
    return {"authenticated": True, "csrf": _set_session_cookie(request, response)}


@app.post("/api/logout", dependencies=[Depends(require_admin)])
def logout(request: Request, response: Response):
    sessions.destroy(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/", secure=_is_https(request), httponly=True, samesite="strict")
    return {"authenticated": False}


@app.post("/api/password", dependencies=[Depends(require_admin)])
def change_password(body: PasswordBody, request: Request, response: Response):
    if not auth.verify_password(body.current, store.get().admin_password_hash):
        raise HTTPException(status_code=400, detail="Current password is wrong")
    store.update(admin_password_hash=auth.hash_password(body.new))
    sessions.destroy_all()  # log out every other session
    logging.info("Admin password changed from %s", client_ip(request))
    return {"csrf": _set_session_cookie(request, response)}


# ---------- admin config ----------
class ConfigUpdate(PublicSettings):
    api_key: Optional[str] = Field(None, max_length=64)  # None = keep current


def _public(cfg: Config) -> dict:
    data = PublicSettings.model_validate(cfg.model_dump()).model_dump()
    data["api_key_set"] = bool(cfg.api_key)
    return data


@app.get("/api/config", dependencies=[Depends(require_admin)])
def get_config():
    return _public(store.get())


@app.put("/api/config", dependencies=[Depends(require_admin)])
def put_config(body: ConfigUpdate, request: Request):
    # Evaluate with the *new* proxy settings: removing the proxy changes which IP you appear as.
    new_ip = client_ip(request, body.trusted_proxies)
    if not _host_allowed(new_ip, body.admin_allowed_hosts):
        raise HTTPException(status_code=422, detail=f"Admin allowed hosts must include your own IP "
                                                    f"({new_ip}), otherwise you lock yourself out")
    changes = body.model_dump(exclude={"api_key"})
    if body.api_key is not None:
        changes["api_key"] = body.api_key
    try:
        cfg = store.update(**changes)
    except ValueError as e:
        raise _validation_error(e)
    logging.info("Configuration saved by %s", client_ip(request))
    return _public(cfg)


# ---------- admin bridge helpers ----------
@app.get("/api/bridge/info", dependencies=[Depends(require_admin)])
def bridge_info():
    return _run(lambda: _bridge(store.get()).info())


@app.get("/api/bridge/lights", dependencies=[Depends(require_admin)])
def bridge_lights():
    lights = _run(lambda: _bridge(store.get()).lights())
    return [{"id": int(k), "name": v.get("name", ""), "type": v.get("type", ""),
             "on": v.get("state", {}).get("on", False), "reachable": v.get("state", {}).get("reachable", True),
             "color": "hue" in v.get("state", {})}
            for k, v in lights.items() if k.isdigit()]


@app.get("/api/bridge/groups", dependencies=[Depends(require_admin)])
def bridge_groups():
    groups = _run(lambda: _bridge(store.get()).groups())
    return [{"id": int(k), "name": v.get("name", ""), "type": v.get("type", ""),
             "lights": [int(x) for x in v.get("lights", []) if str(x).isdigit()],
             "any_on": v.get("state", {}).get("any_on", False)}
            for k, v in groups.items() if k.isdigit()]


class PairBody(BaseModel):
    bridge_ip: str = Field(max_length=253)


@app.post("/api/bridge/pair", dependencies=[Depends(require_admin)])
def bridge_pair(body: PairBody, request: Request):
    try:
        ip = validate_bridge_host(body.bridge_ip)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not ip:
        raise HTTPException(status_code=422, detail="Bridge IP required")
    key = _run(lambda: hue.pair(ip))
    cfg = store.update(bridge_ip=ip, api_key=key)
    logging.info("Paired with bridge %s (by %s)", ip, client_ip(request))
    return _public(cfg)


class ApplyBody(BaseModel):
    kind: Literal["room", "group"]
    target: dict
    state: Optional[Literal["on", "off", "toggle"]] = None


@app.post("/api/bridge/apply", dependencies=[Depends(require_admin)])
def bridge_apply(body: ApplyBody):
    """Test unsaved room/group settings straight from the UI."""
    cfg = store.get()
    model = Room if body.kind == "room" else Group
    try:
        target = model.model_validate({**body.target, "id": 1})
    except ValueError as e:
        raise _validation_error(e)
    if body.kind == "room":
        room = target
        action = _run(lambda: hue.HueAction(cfg.bridge_ip, cfg.api_key, lamps=room.lamps,
                                            step_delay_ms=room.step_delay_ms, reverse_off=room.reverse_off,
                                            **_light_kwargs(room)))
        return _run(lambda: action.trigger_lamps(_parse_state(body.state)))
    group = target
    action = _run(lambda: hue.HueAction(cfg.bridge_ip, cfg.api_key, group=group.group, **_light_kwargs(group)))
    return _run(lambda: action.trigger_group(_parse_state(body.state)))


@app.get("/api/logs", dependencies=[Depends(require_admin)])
def get_logs(lines: int = Query(200, ge=1, le=2000)):
    if not LOG_PATH.exists():
        return {"lines": []}
    with open(LOG_PATH, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 256 * 1024))
        tail = f.read().decode("utf-8", errors="replace").splitlines()
    return {"lines": tail[-lines:]}


# ---------- UI ----------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/")


@app.get("/ui", include_in_schema=False)
@app.get("/ui/", include_in_schema=False)
def ui(request: Request):
    _check_host(request, store.get().admin_allowed_hosts)
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/ui/static", StaticFiles(directory=STATIC_DIR), name="static")
