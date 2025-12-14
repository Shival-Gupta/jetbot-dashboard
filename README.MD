# JetBot Dashboard

A web-based dashboard for controlling and monitoring your JetBot, featuring Arduino integration, system monitoring, and remote control capabilities.

## Features

### 🖥️ Dashboard
- Real-time system monitoring (CPU, GPU, RAM, Power, Storage)
- Arduino connection status
- System temperature monitoring
- Network status monitoring
- Device management interface

### 🔧 Arduino Integration
- List and connect to Arduino devices
- Upload/verify sketches
- Serial monitor interface
- Built-in code editor
- Real-time device status

### 🎮 Robot Control
- Mecanum wheel movement control
- Line following capabilities
- Speed control
- Keyboard and touch controls
- Status monitoring
- Real-time feedback

### ⚙️ Setup Tools
- Package installation
- Arduino CLI setup
- Autostart configuration
- System status checking
- Network configuration

## Requirements

- Jetson Nano
- Arduino board (connected via USB)
- Docker and Docker Compose V2
- Web browser (on client device)

## Project Structure
```
├── backend/
│   ├── handlers/          # API endpoint handlers
│   ├── scripts/          # Utility scripts
│   ├── requirements.txt  # Python dependencies
│   └── server.py         # Main Tornado server
├── frontend/
│   └── src/
│       ├── global.css    # Shared styles
│       ├── global.js     # Shared JavaScript
│       ├── index.html    # Login page
│       ├── dashboard/    # System monitoring
│       ├── arduino/      # Arduino IDE interface
│       ├── control/      # Robot control interface
│       └── setup/        # System configuration
├── docker-compose.yml
└── Dockerfile
```

## Quick Start

1. Clone the repository:
```bash
git clone https://github.com/Shival-Gupta/jetbot-command-centre.git
cd jetbot-dashboard
```

2. Start the dashboard:
```bash
COOKIE_SECRET=$(openssl rand -hex 32)
COOKIE_SECRET=$COOKIE_SECRET docker compose up -d
```

3. Access the dashboard:
- Open `http://<jetson-ip>:8888`
- Login with default credentials:
  - Username: `jetbot`
  - Password: `jetbot`

## Setup Guides

### Arduino Setup
1. Connect Arduino via USB
2. Open Setup page in dashboard
3. Click "Setup Arduino CLI"
4. Use Arduino IDE page to upload code
5. Verify connection in dashboard

### Autostart Configuration
To start dashboard on boot:
```bash
./backend/scripts/setup_service.sh
```

## Development

### Building Images
```bash
# For Jetson Nano (ARM64)
docker compose build

# For PC (AMD64)
PLATFORM=linux/amd64 docker compose build
```

### Container Registry
Images available at:
- `docker.io/shivalgupta5545/jetbot-dashboard:latest`
- `ghcr.io/shival-gupta/jetbot-dashboard:latest`

### API Endpoints
- `/auth/login` - Authentication
- `/ws/stats` - WebSocket for system stats
- `/arduino/*` - Arduino device management
- `/control/*` - Robot movement control
- `/setup/*` - System configuration

## Troubleshooting

### Common Issues

1. **Arduino Not Found**
   - Check USB connection
   - Try different USB port
   - Run: `sudo usermod -aG dialout $USER`
   - Verify device permissions in container
   - Check Arduino CLI installation

2. **Dashboard Not Loading**
   - Verify container status: `docker compose ps`
   - Check logs: `docker compose logs`
   - Ensure port 8888 is accessible
   - Check network connection
   - Verify system resources

3. **Docker Permission Issues**
   - Add user to docker group: `sudo usermod -aG docker $USER`
   - Log out and log back in
   - Check container privileges

4. **Autostart Issues**
   - Verify service installation
   - Check systemd logs: `journalctl -u jetbot-dashboard`
   - Ensure correct permissions
   - Validate configuration

### Logs
- Container logs: `docker compose logs`
- System service: `journalctl -u jetbot-dashboard`
- Arduino CLI: Check Setup page logs
- Application logs: Check `./logs` directory

## Security

- Change default credentials for production
- Use HTTPS if exposed to internet
- Keep Docker and system packages updated
- Secure your network configuration
- Modify credentials in `auth_handler.py`
- Regular security updates
- Proper file permissions

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request
6. Follow coding standards

## Support

Create an issue for:
- Bug reports
- Feature requests
- General questions
- Documentation improvements

## License

MIT License - see LICENSE file
