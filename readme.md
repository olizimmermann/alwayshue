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