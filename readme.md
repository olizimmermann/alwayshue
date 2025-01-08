# Smart Light Switch Integration

This project enables you to control your Philips Hue lamps using traditional wall switches without cutting power to the bulbs. By integrating devices like Shelly relays, your switches send commands to a server, which then controls the lights via the Hue API.

## Features

- **Preserve Smart Bulb Functionality**: Keep your Hue lamps continuously powered to maintain smart features.
- **Use Existing Switches**: Operate your lights with traditional wall switches.
- **Seamless Integration**: Switches send requests to a server, which manages the lights without interrupting power.

## Prerequisites

Before setting up, ensure you have:

- **Philips Hue Bridge**: Manages your Hue lamps.
- **Shelly Relay (or similar)**: Installed behind your wall switches to send HTTP requests.
- **Docker**: To run the server application.

## Setup Guide

Follow these steps to set up the system:

### 1. Clone the Repository

Download the project files to your local machine:

```bash
git clone https://github.com/olizimmermann/alwayshue.git
cd alwayshue
```

### 2. Configure Environment Variables

Create a `.env` file in the `app` directory with the following content:

```env
apikey=YOUR_HUE_API_KEY
ip=YOUR_HUE_BRIDGE_IP
allowed_hosts=*
```

- `apikey`: Your Philips Hue Bridge API key.
- `ip`: The IP address of your Hue Bridge.
- `allowed_hosts`: Comma-separated list of IPs allowed to control the lights (use `*` to allow all).

### 3. Build and Run the Docker Container

Ensure Docker is installed on your system. Then, build and run the container:

```bash
docker-compose up --build -d
```

- This command builds the Docker image and starts the server in detached mode.

### 4. Configure Shelly Relay

Set up your Shelly relay to send HTTP GET requests to the server when the switch is toggled:

- **URL**: `http://SERVER_IP:8000/room_1` (replace `SERVER_IP` with your server's IP address).
- **Method**: GET

Repeat this configuration for each switch, adjusting the endpoint (`/room_1`, `/room_2`, etc.) as needed.

## Logging

The application logs its activities to `app.log` within the container. To access the logs:

1. Enter the running container:

   ```bash
   docker exec -it smart-light-switch_webserver_1 bash
   ```

2. View the log file:

   ```bash
   cat /app/app.log
   ```

The logging system uses rotation to prevent the log file from becoming too large, maintaining up to three backup files, each with a maximum size of 10 MB.

## Security Considerations

- **Allowed Hosts**: Restrict `allowed_hosts` to specific IP addresses to enhance security.
- **API Key**: Keep your Hue API key confidential.

## Troubleshooting

- **Connection Issues**: Ensure the server can communicate with the Hue Bridge and that the Shelly relay can reach the server.
- **Log Files**: Check `app.log` for error messages and debugging information.

## Contributing

Contributions are welcome! Feel free to submit issues and pull requests to improve the project.

## License

This project is licensed under the MIT License.

---

By following this guide, you can integrate your existing wall switches with Philips Hue lamps, maintaining smart functionality while using familiar controls. 