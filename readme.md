# Smart Light Switch Integration

This project enables you to control your Philips Hue lamps using traditional wall switches without cutting power to the bulbs. By integrating devices like Shelly relays, your switches send commands to a server, which then controls the lights via the Hue API.

## Features

- **Preserve Smart Bulb Functionality**: Keep your Hue lamps continuously powered to maintain smart features.
- **Use Existing Switches**: Operate your lights with traditional wall switches.
- **Seamless Integration**: Switches send requests to a server, which manages the lights without interrupting power.
- **Web UI**: Configure bridge, rooms, groups, colors and access control in the browser. No code edits needed.

## Prerequisites

Before setting up, ensure you have:

- **Philips Hue Bridge**: Manages your Hue lamps.
- **Shelly Relay (or similar)**: Installed behind your wall switches to send HTTP requests.
- **Docker** with Compose v2.24+: To run the server application.

## Setup Guide

Follow these steps to set up the system:

### 1. Clone the Repository

Download the project files to your local machine:

```bash
git clone https://github.com/olizimmermann/alwayshue.git
cd alwayshue
```

### 2. (Optional) Seed values via `.env`

Everything can be configured in the web UI. If you want to pre-seed values, copy `app/example.env` to `app/.env`:

```env
apikey=YOUR_HUE_API_KEY
ip=YOUR_HUE_BRIDGE_IP
allowed_hosts=*
admin_password=a-long-admin-password
```

These values are **only read on the very first start** to create `data/config.json`. After that, the web UI is the source of truth.

### 3. Build and Run the Docker Container

```bash
docker compose up --build -d
```

If you did not set `admin_password`, a random initial password is printed once:

```bash
docker compose logs webserver | grep "initial admin password"
```

### 4. Open the Web UI

Browse to `http://SERVER_IP:8000/ui/` and log in.

| Tab | What you configure |
|-----|--------------------|
| **Switches** | Rooms (set of lamps, picked from the bridge's light list) and groups (bridge group/zone). Per room/group: brightness, hue, saturation, or white only. On/Off/Toggle buttons test **unsaved** settings live. The switch URL can be copied from each card. |
| **Bridge** | Bridge IP, API key, *Pair new key* (press the link button on the bridge first), connection test, list of all lights. |
| **Security** | Allowed switch hosts (IP/CIDR), optional switch key, allowed admin hosts, admin password. |
| **Logs** | Live view of the activity log. |

Settings are stored in the `alwayshue-data` Docker volume (`/app/data/config.json`, mode 0600) and survive rebuilds.

### 5. Configure Shelly Relay

Point the Shelly action to the URL shown on the room/group card, e.g.:

- `http://SERVER_IP:8000/room/1`: toggle
- `http://SERVER_IP:8000/room/1?state=on` / `?state=off`: fixed action (recommended for detached switch inputs with separate on/off actions, so the state never gets out of sync)
- If a switch key is set: `http://SERVER_IP:8000/room/1?key=YOUR_KEY&state=on`

Toggle logic for rooms: if **any** lamp of the room is on, all are switched off, otherwise all are switched on.

**Sweep effect:** lamps are switched in the room's sequence order (reorder it under *Switching sequence*; chips show each lamp's position). Set *Delay (ms)* to switch one lamp every N ms (e.g. 100–200 ms to have the light run through the room). Enable *turn off in reverse order* to have it run back when switching off. With a delay of 0, all commands are sent at once and the bridge processes them in sequence order (~10 per second).

## Speed: getting minimal switch delay

1. **Use `?state=on` / `?state=off` URLs** where the Shelly can send separate on/off actions. alwayshue then sends lamp commands immediately (~3 ms) without reading the current state first. A plain toggle needs one small state read of the first lamp in the sequence (~30 ms).
2. **Set *Fade (ms)* to 0** for instant switching. The Hue default is a 400 ms fade.
3. **Delay 0** in the room's *Effect* section (no sweep).
4. **Big rooms: use a group instead.** The bridge processes only ~10 individual light commands per second, so in a 14-lamp room the last lamp reacts ~1.3 s after the first. A `/group/<id>` endpoint sends **one** Zigbee group command and all lamps switch at the same moment.

The server keeps a keep-alive connection pool to the bridge and a shared worker pool, so there is no connection or thread start-up cost per switch press.

## Behind a reverse proxy (Nginx Proxy Manager)

Behind a proxy, every request arrives from the proxy's IP. To have allowlists, login throttling and logs use the **real client IP**, add the proxy under *Security → Reverse proxy → Trusted proxies*. The panel shows which IP the connection comes from (`This connection comes from …`), which is the address to enter.

- Only when the direct TCP peer is a trusted proxy is `X-Forwarded-For` evaluated, right to left, skipping trusted proxies. Entries a client puts into the header itself are ignored, so the IP can't be spoofed through the proxy. `X-Real-IP` is used as a fallback.
- **Trust exactly the NPM container IP**, not a whole Docker range. Tip: give NPM a static IP in a shared Docker network. If the port is also published on the LAN and Docker's userland proxy is active, direct LAN connections can appear with the Docker gateway IP (e.g. `172.17.0.1`). Never trust that address, because anyone reaching the published port could then forge the header.
- If the proxy terminates HTTPS and sends `X-Forwarded-Proto: https`, the session cookie is automatically marked `Secure`.
- Shelly relays can keep calling the server directly on port 8000. Direct connections are unaffected.

### Troubleshooting: still a Docker IP (172.x)?

Open *Security → Reverse proxy*. The diagnostics box shows what the proxy sends and suggests the fix.

1. **Detected IP = "Connection from" IP** → the proxy isn't trusted yet. Add exactly that IP to *Trusted proxies* and click **Save**.
2. **X-Forwarded-For itself contains a 172.x address** → Nginx Proxy Manager **itself** never sees the real client. Check NPM's own access log (`/data/logs/proxy-host-*_access.log` in the NPM container). If it shows 172.x too, this is confirmed, and no setting in alwayshue can recover the IP. Typical causes and fixes:
   - **Client connects via IPv6, Docker has no IPv6 for NPM** → Docker's `docker-proxy` accepts the connection and forwards it with the gateway IP as source. Fix: enable IPv6 for Docker/NPM's network (`/etc/docker/daemon.json`: `"ipv6": true, "ip6tables": true`, plus `enable_ipv6: true` on the network), or run NPM with `network_mode: host`. Quick test: open the site via IPv4 only (e.g. `http://<IPv4>`). If the IP is correct then, IPv6 is the cause.
   - **Hairpin**: the client is the Docker host itself, or reaches the service through the host's own address. That connection is NATed and gets the gateway IP.

Recommended layout: put alwayshue on NPM's Docker network and forward to the container name. The peer is then NPM's container IP, which is the only thing you trust:

```yaml
# docker-compose.yml (alwayshue)
services:
  webserver:
    networks: [npm]
networks:
  npm:
    external: true
    name: npm_default   # `docker network ls`, NPM's network
```

In NPM set *Forward Hostname* to the alwayshue container name (e.g. `alwayshue-webserver-1`) with port `8000`.

## Logging

Activity is logged to `/app/data/app.log` (rotated, 3 × 10 MB) and visible in the **Logs** tab and via `docker compose logs`.

## Security Considerations

- **Admin UI** is password protected (scrypt hash, HttpOnly + SameSite=Strict session cookie, CSRF token, 5 failed logins → 5 min lockout per IP). Restrict it further with *Admin allowed hosts*. You can't save a list that excludes your own IP.
- **Switch endpoints** are unauthenticated GET requests by design (Shelly). Restrict them with *Allowed hosts* (IP/CIDR) and optionally a *switch key*. Without a key, any website opened by a browser on an allowed host can switch your lights (e.g. via `<img src=...>`).
- **Plain HTTP**: the admin password, session cookie and switch key travel unencrypted on your LAN. If you expose the UI beyond a trusted network, put it behind an HTTPS reverse proxy and set `cookie_secure=true`. Behind a proxy, the source IP seen is the proxy's IP, so host allowlists then refer to the proxy.
- **Hue API key** is stored only in the data volume (never in the image), never sent to the browser and never written to logs. Note that the Hue v1 API itself is plain HTTP between server and bridge.
- The container runs as non-root with a read-only root filesystem, all capabilities dropped and `no-new-privileges`.

## Troubleshooting

- **Connection Issues**: Use *Bridge → Test connection*. Make sure the server can reach the Hue Bridge and the Shelly relay can reach the server.
- **Lamp shows as "missing"**: the lamp ID no longer exists on the bridge; click it to remove it.
- **White-only bulbs** don't accept hue/sat: disable *set color* for that room.
- **Locked out of the admin UI**: edit `admin_allowed_hosts` in `config.json` inside the volume, or delete `admin_password_hash` there and restart to get a new generated password.

## Contributing

Contributions are welcome! Feel free to submit issues and pull requests to improve the project.

## License

This project is licensed under the MIT License.

---

By following this guide, you can integrate your existing wall switches with Philips Hue lamps, maintaining smart functionality while using familiar controls. 

---