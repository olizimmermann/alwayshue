

```markdown
# Hue Relay Trigger Tool

This repository contains a tool for integrating Hue lamps with relays (e.g., Shelly devices) using an API. It allows you to maintain constant power to your smart lamps while still using traditional light switches. Instead of cutting the power to the lamps, a web server sends API requests to toggle the lights on or off.

## Features
- **Smart Switch Integration**: Keep your Hue lamps always powered and use traditional switches to trigger API calls.
- **Room & Group Control**: Manage individual lamps or groups of lamps through defined endpoints.
- **Environment Variables**: Configure the setup using `.env` for easy adaptation.
- **FastAPI Framework**: A lightweight and efficient API for controlling the lights.
- **Docker Support**: Run the service with Docker for easy deployment.

---

## How It Works

1. **Relay/Switch Integration**:
   - When the relay or traditional switch is toggled, an API request is sent to the server.
   - The server determines the current state of the lamps and toggles them accordingly.

2. **Hue Bridge Communication**:
   - Uses the Hue Bridge API to fetch the current state of lamps or groups and to send commands.

3. **Environment Configuration**:
   - Define API keys, Hue Bridge IP, and allowed hosts in the `.env` file.

---

## Getting Started

### Prerequisites
- Hue Bridge
- Shelly (or similar relay device)
- Docker (optional, for containerized deployment)

### Environment Variables
Create an `.env` file with the following configuration:
```env
apikey=<YOUR_HUE_API_KEY>
ip=<HUE_BRIDGE_IP>
allowed_hosts=<ALLOWED_HOSTS> # Comma-separated IPs or '*' for all
```

### Build and Run with Docker
1. **Clone the repository**:
   ```bash
   git clone https://github.com/olizimmermann/alwayshue.git
   cd alwayshue
   ```

2. **Build and start the Docker container**:
   ```bash
   docker-compose up --build -d
   ```

3. **Access the API**:
   The service will be available at `http://<host-ip>:8000`.

---

## API Endpoints
### Single Lamp Control
- **`GET /room_1`**: Toggle lamps in Room 1.
- **`GET /room_2`**: Toggle lamps in Room 2.

### Group Control
- **`GET /group_1`**: Toggle all lamps in Group 1.

### Middleware
- Restricts access based on allowed hosts specified in `.env`.

---

## Benefits
- Keeps Hue lamps always powered, preserving smart functionalities.
- Seamlessly integrates old light switches into modern smart home setups.
- Simple and customizable API for controlling lamps and groups.
- Prevents unnecessary hardware replacements.

---

## Code Overview

### `main.py`
- Defines FastAPI routes for toggling individual lamps or groups.
- Middleware ensures environment variables and allowed hosts are correctly configured.

### `hue.py`
- Handles communication with the Hue Bridge for retrieving lamp states and sending commands.
- Supports toggling individual lamps and groups with threading for parallel execution.

### Docker
- **Dockerfile**: Builds a lightweight Python 3.11 image with FastAPI and dependencies.
- **docker-compose.yml**: Simplifies multi-service deployment and configuration.

---

## Contributing
Feel free to submit pull requests or create issues for improvements and bug fixes.

---

## License
This project is open-source and available under the [MIT License](LICENSE).

---

## Contact
For questions or support, please reach out to `github@ozimmermann.com`.

Happy Smart Switching! 🚀
```