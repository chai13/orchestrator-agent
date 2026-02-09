# Project Structure

```
orchestrator-agent/
├── src/                                    # Source code
│   ├── index.py                            # Entry point with reconnection loop
│   ├── controllers/                        # Communication protocol handlers
│   │   ├── __init__.py                     # Main WebSocket task
│   │   ├── websocket_controller/           # WebSocket client and topics
│   │   │   ├── __init__.py                 # Client configuration
│   │   │   └── topics/                     # Topic handlers
│   │   │       ├── __init__.py             # Topic registration
│   │   │       ├── receivers/              # Incoming message handlers
│   │   │       │   ├── __init__.py
│   │   │       │   ├── connect.py
│   │   │       │   ├── disconnect.py
│   │   │       │   ├── create_new_runtime.py
│   │   │       │   ├── delete_device.py
│   │   │       │   ├── delete_orchestrator.py
│   │   │       │   ├── get_consumption_device.py
│   │   │       │   ├── get_consumption_orchestrator.py
│   │   │       │   ├── get_device_status.py
│   │   │       │   ├── get_host_interfaces.py
│   │   │       │   ├── get_serial_devices.py
│   │   │       │   ├── restart_device.py
│   │   │       │   ├── run_command.py
│   │   │       │   ├── start_device.py
│   │   │       │   └── stop_device.py
│   │   │       └── emitters/               # Outgoing message handlers
│   │   │           ├── __init__.py
│   │   │           └── heartbeat.py        # Periodic heartbeat emitter
│   │   └── webrtc_controller/              # WebRTC remote terminal access
│   │       ├── __init__.py                 # Session manager and initialization
│   │       ├── types.py                    # Type definitions
│   │       ├── session_manager.py          # Peer connection session tracking
│   │       ├── data_channel/               # Data channel handling
│   │       │   ├── __init__.py
│   │       │   └── data_channel_handler.py # Terminal I/O and keepalive
│   │       └── signaling/                  # WebRTC signaling handlers
│   │           ├── __init__.py
│   │           ├── offer_handler.py        # SDP offer handling
│   │           ├── ice_handler.py          # ICE candidate handling
│   │           └── disconnect_handler.py   # Peer disconnect handling
│   ├── use_cases/                          # Business logic
│   │   ├── __init__.py
│   │   ├── docker_manager/                 # Container and network management
│   │   │   ├── __init__.py                 # Docker client and registry
│   │   │   ├── create_runtime_container.py # Runtime container creation
│   │   │   ├── delete_runtime_container.py # Container deletion
│   │   │   ├── get_device_status.py        # Container status queries
│   │   │   └── selfdestruct.py             # Agent self-termination
│   │   ├── runtime_commands/               # Runtime command execution
│   │   │   ├── __init__.py                 # HTTP request utilities
│   │   │   └── run_command.py              # Command execution
│   │   └── network_monitor/                # Network monitoring
│   │       ├── __init__.py
│   │       └── get_host_interfaces.py      # Host interface discovery
│   └── tools/                              # Utilities
│       ├── __init__.py
│       ├── chunking.py                     # Message chunking protocol
│       ├── contract_validation.py          # Message schema validation
│       ├── devices_usage_buffer.py         # Device usage metrics buffer
│       ├── dns_utils.py                    # DNS resolution utilities
│       ├── docker_event_listener.py        # Docker event monitoring
│       ├── docker_tools.py                 # Docker helper utilities
│       ├── interface_cache.py              # Interface information cache
│       ├── logger.py                       # Logging with rotation
│       ├── network_event_listener.py       # Network event listener and reconnection
│       ├── operations_state.py             # Operation state tracking (race prevention)
│       ├── serial_persistence.py           # Serial device persistence
│       ├── ssl.py                          # mTLS configuration and agent ID
│       ├── system_info.py                  # System information
│       ├── system_metrics.py               # System metrics collection
│       ├── usage_buffer.py                 # Usage metrics buffer
│       ├── utils.py                        # General utilities
│       └── vnic_persistence.py             # vNIC configuration persistence
├── install/                                # Installation files
│   ├── install.sh                          # Installation script
│   ├── autonomy-netmon.py                  # Network monitor daemon
│   ├── Dockerfile.netmon                   # Network monitor container image
│   ├── udhcpc-script.sh                    # DHCP client script
│   └── udhcpc-wifi.sh                      # WiFi DHCP client script
├── docs/                                   # Documentation
│   ├── architecture/                       # System design
│   │   ├── architecture.md                 # System architecture
│   │   └── structure.md                    # This file
│   ├── features/                           # Feature documentation
│   │   ├── cloud-protocol/
│   │   │   └── cloud-protocol.md           # Cloud communication protocol
│   │   ├── runtime-containers/
│   │   │   └── runtime-containers.md       # Runtime container management
│   │   ├── serial-port-passthrough/
│   │   │   ├── README.md                   # Feature overview
│   │   │   ├── ARCHITECTURE.md             # Technical architecture
│   │   │   └── IMPLEMENTATION_PHASES.md    # Implementation plan
│   │   └── webrtc/
│   │       └── webrtc-debug-implementation.md  # WebRTC implementation
│   ├── guides/                             # How-to guides
│   │   ├── development.md                  # Local development
│   │   ├── installation.md                 # Installation guide
│   │   └── troubleshooting.md              # Troubleshooting guide
│   ├── networking/                         # Networking documentation
│   │   ├── networking.md                   # Networking model
│   │   ├── network-monitor.md              # Network monitor sidecar
│   │   └── wifi-proxy-arp-implementation-plan.md  # WiFi support plan
│   └── operations/                         # Operations documentation
│       ├── ci-cd.md                        # CI/CD pipeline
│       ├── logging-metrics.md              # Logging and metrics
│       └── security.md                     # Security and mTLS
├── .devcontainer/                          # VS Code dev container
│   ├── devcontainer.json                   # Dev container configuration
│   ├── Dockerfile                          # Dev container image
│   └── requirements.txt                    # Dev dependencies
├── .github/workflows/                      # CI/CD
│   ├── docker.yml                          # Agent multi-arch image build
│   └── netmon-docker.yml                   # Netmon multi-arch image build
├── .gitignore                              # Git ignore rules
├── CLAUDE.md                               # Claude Code project instructions
├── Dockerfile                              # Production container image
├── LICENSE                                 # Project license
├── README.md                               # Project overview
└── requirements.txt                        # Production dependencies
```

## Key Directories

### src/
Contains all source code for the orchestrator agent.

### src/controllers/
Protocol handlers for WebSocket and WebRTC communication.

### src/use_cases/
Business logic for Docker management, runtime commands, and network monitoring.

### src/tools/
Utility modules for logging, SSL/mTLS, metrics, validation, persistence, and network/Docker event handling.

### install/
Installation script and network monitor sidecar files.

### docs/
Comprehensive documentation for all aspects of the system.

### .devcontainer/
VS Code development container configuration for consistent development environments.

### .github/workflows/
GitHub Actions workflows for CI/CD (multi-architecture Docker image builds).

## Key Files

### src/index.py
Entry point for the orchestrator agent. Implements the main reconnection loop and starts the WebSocket controller.

### src/controllers/websocket_controller/__init__.py
WebSocket client configuration and Socket.IO connection management.

### src/controllers/websocket_controller/topics/receivers/create_new_runtime.py
Handles the `create_new_runtime` topic to create OpenPLC runtime containers.

### src/use_cases/docker_manager/create_runtime_container.py
Core logic for creating runtime containers with MACVLAN and internal networks.

### src/tools/network_event_listener.py
Listens for network change events from the sidecar and triggers container reconnection.

### install/install.sh
Installation script that provisions certificates and deploys containers.

### install/autonomy-netmon.py
Network monitor daemon that detects physical network changes.

## Configuration Files

### Dockerfile
Production container image definition for the orchestrator agent.

### install/Dockerfile.netmon
Container image definition for the network monitor sidecar.

### requirements.txt
Python dependencies for the orchestrator agent.

### .devcontainer/devcontainer.json
VS Code development container configuration.

### .github/workflows/docker.yml
GitHub Actions workflow for multi-architecture Docker image builds.
