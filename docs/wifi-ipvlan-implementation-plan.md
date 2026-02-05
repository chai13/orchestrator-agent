# WiFi Support via IPvlan - Implementation Plan

This document describes the implementation strategy for enabling vPLC container networking on WiFi interfaces using IPvlan as an alternative to MACVLAN.

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Technical Background](#technical-background)
3. [Solution Architecture](#solution-architecture)
4. [Implementation Tasks](#implementation-tasks)
5. [Cleanup and Deletion](#cleanup-and-deletion)
6. [Testing Strategy](#testing-strategy)
7. [Rollback Plan](#rollback-plan)

---

## Problem Statement

### Current Situation

The orchestrator-agent uses MACVLAN Docker networks to give each vPLC container its own MAC address and IP address, making them appear as separate physical devices on the network. This works well on **Ethernet** interfaces but **fails on WiFi** interfaces.

### Why MACVLAN Fails on WiFi

```
┌─────────────────────────────────────────────────────────────────┐
│                    MACVLAN on WiFi - The Problem                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Host                         WiFi Access Point               │
│   ┌──────────────┐             ┌──────────────┐                │
│   │   wlan0      │             │              │                │
│   │   MAC: AA:BB │◄───────────►│  Authenticated│               │
│   │   (auth'd)   │   802.11    │  MAC: AA:BB  │                │
│   └──────┬───────┘             └──────────────┘                │
│          │                                                      │
│   ┌──────┴───────┐                                             │
│   │   MACVLAN    │                                             │
│   │   Network    │                                             │
│   └──────┬───────┘                                             │
│          │                                                      │
│   ┌──────┴───────┐             ┌──────────────┐                │
│   │  Container   │             │              │                │
│   │  MAC: 02:XX  │─────────X───│  NOT auth'd! │                │
│   │  (different) │   BLOCKED   │  MAC: 02:XX  │                │
│   └──────────────┘             └──────────────┘                │
│                                                                 │
│   Result: Container traffic is dropped by the access point     │
│   because its MAC address never completed 802.11 auth/assoc    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Root Cause:** WiFi access points perform MAC-based authentication. Only devices that have completed the 802.11 authentication and association handshake can send/receive traffic. MACVLAN creates containers with **new MAC addresses** that the AP has never seen, so their traffic is dropped.

**Why Ethernet Works:** Ethernet switches are promiscuous by design - they forward frames based on MAC learning without authenticating devices. Any MAC address on a port is accepted.

### Requirements

1. vPLCs must be reachable by other devices on the network (Modbus, OPC-UA, SCADA protocols)
2. vPLCs must be able to communicate with other devices on the network
3. Each vPLC should ideally have its own IP address
4. DHCP should work for automatic IP assignment
5. Existing Ethernet functionality must not be affected

---

## Technical Background

### MACVLAN vs IPvlan

| Feature | MACVLAN | IPvlan L2 |
|---------|---------|-----------|
| Container MAC | Unique per container | Same as parent interface |
| Works on WiFi | No | Yes |
| DHCP identification | By MAC address | By client-id (option 61) |
| Host-container communication | Yes | No (Linux limitation) |
| Network visibility | Separate device | Separate IP, same MAC |

### IPvlan L2 Mode

IPvlan L2 (Layer 2) mode allows containers to share the parent interface's MAC address while having unique IP addresses. This is the key to WiFi compatibility.

```
┌─────────────────────────────────────────────────────────────────┐
│                    IPvlan L2 on WiFi - Solution                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Host                         WiFi Access Point               │
│   ┌──────────────┐             ┌──────────────┐                │
│   │   wlan0      │             │              │                │
│   │   MAC: AA:BB │◄───────────►│  Authenticated│               │
│   │   (auth'd)   │   802.11    │  MAC: AA:BB  │                │
│   └──────┬───────┘             └──────────────┘                │
│          │                                                      │
│   ┌──────┴───────┐                                             │
│   │   IPvlan L2  │                                             │
│   │   Network    │                                             │
│   └──────┬───────┘                                             │
│          │                                                      │
│   ┌──────┴───────┐             ┌──────────────┐                │
│   │  Container   │             │              │                │
│   │  MAC: AA:BB  │◄───────────►│  Same MAC!   │                │
│   │  (same!)     │   ALLOWED   │  Traffic OK  │                │
│   │  IP: unique  │             │              │                │
│   └──────────────┘             └──────────────┘                │
│                                                                 │
│   Result: Container traffic flows through because it uses      │
│   the same authenticated MAC address as the host               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### DHCP with IPvlan (Client Identifier)

Since all containers share the same MAC, DHCP servers would normally see them as the same client. We solve this using **DHCP Option 61 (Client Identifier)**.

```
┌─────────────────────────────────────────────────────────────────┐
│                    DHCP with Client-ID                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Container A                    Container B                    │
│   ┌──────────────┐              ┌──────────────┐               │
│   │ MAC: AA:BB   │              │ MAC: AA:BB   │               │
│   │ (shared)     │              │ (shared)     │               │
│   └──────┬───────┘              └──────┬───────┘               │
│          │                             │                        │
│          │ DHCP DISCOVER               │ DHCP DISCOVER          │
│          │ Client-ID: "vplc-a:eth0"    │ Client-ID: "vplc-b:eth0"
│          │                             │                        │
│          └─────────────┬───────────────┘                       │
│                        │                                        │
│                        ▼                                        │
│              ┌─────────────────┐                               │
│              │   DHCP Server   │                               │
│              │                 │                               │
│              │ Identifies by   │                               │
│              │ Client-ID, not  │                               │
│              │ MAC address     │                               │
│              └────────┬────────┘                               │
│                       │                                         │
│         ┌─────────────┴─────────────┐                          │
│         │                           │                           │
│         ▼                           ▼                           │
│   Container A: 192.168.1.50   Container B: 192.168.1.51        │
│                                                                 │
│   Both containers get unique IPs!                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

The `udhcpc` DHCP client supports custom client-id via the `-x` option:
```bash
udhcpc -i eth1 -x 0x3d:76706c632d613a65746830  # hex-encoded "vplc-a:eth0"
```

---

## Solution Architecture

### Hybrid Approach

We implement a **hybrid strategy** that automatically selects the appropriate network driver based on interface type:

- **Ethernet interfaces** → MACVLAN (existing behavior, unchanged)
- **WiFi interfaces** → IPvlan L2 with client-id DHCP

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                       Container Creation Flow                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Cloud Command: create_new_runtime                              │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────────────────────────────────┐                   │
│  │ 1. Load vNIC config                     │                   │
│  │    - parent_interface: "wlan0"          │                   │
│  └─────────────────┬───────────────────────┘                   │
│                    │                                            │
│                    ▼                                            │
│  ┌─────────────────────────────────────────┐                   │
│  │ 2. Get interface type from cache        │                   │
│  │    - Check INTERFACE_CACHE["wlan0"]     │                   │
│  │    - type: "wifi"                       │                   │
│  └─────────────────┬───────────────────────┘                   │
│                    │                                            │
│                    ▼                                            │
│  ┌─────────────────────────────────────────┐                   │
│  │ 3. Select network driver                │                   │
│  │    - WiFi? → get_or_create_ipvlan()     │                   │
│  │    - Ethernet? → get_or_create_macvlan()│                   │
│  └─────────────────┬───────────────────────┘                   │
│                    │                                            │
│                    ▼                                            │
│  ┌─────────────────────────────────────────┐                   │
│  │ 4. Create container with network        │                   │
│  │    - IPvlan: container shares parent MAC│                   │
│  │    - MACVLAN: container gets unique MAC │                   │
│  └─────────────────┬───────────────────────┘                   │
│                    │                                            │
│                    ▼                                            │
│  ┌─────────────────────────────────────────┐                   │
│  │ 5. Start DHCP (if network_mode=dhcp)    │                   │
│  │    - IPvlan: use_client_id=True         │                   │
│  │      udhcpc -x 0x3d:{hex_client_id}     │                   │
│  │    - MACVLAN: use_client_id=False       │                   │
│  │      udhcpc (standard, by MAC)          │                   │
│  └─────────────────┬───────────────────────┘                   │
│                    │                                            │
│                    ▼                                            │
│  ┌─────────────────────────────────────────┐                   │
│  │ 6. Save vNIC config with network type   │                   │
│  │    - Store interface_type for reconnect │                   │
│  └─────────────────────────────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Tasks

### Task 1: Add WiFi Interface Type Detection to netmon

**File:** `install/autonomy-netmon.py`

**Changes:**

1. Add `get_interface_type()` function:

```python
def get_interface_type(ifname: str) -> str:
    """
    Detect if a network interface is WiFi or Ethernet.

    Detection methods (in order):
    1. Check /sys/class/net/{ifname}/wireless directory
    2. Check /sys/class/net/{ifname}/phy80211 symlink
    3. Check interface name patterns (wlan*, wlp*, wlx*)

    Returns:
        "wifi" or "ethernet"
    """
    # Method 1: Check for wireless sysfs directory
    wireless_path = f"/sys/class/net/{ifname}/wireless"
    if os.path.exists(wireless_path):
        return "wifi"

    # Method 2: Check for phy80211 (wireless PHY) link
    phy_path = f"/sys/class/net/{ifname}/phy80211"
    if os.path.exists(phy_path):
        return "wifi"

    # Method 3: Check interface name patterns (fallback)
    if ifname.startswith(("wlan", "wlp", "wlx")):
        return "wifi"

    return "ethernet"
```

2. Update `get_interface_info()` to include type:

```python
def get_interface_info(self, ifname: str) -> Optional[Dict]:
    # ... existing code ...
    return {
        "interface": ifname,
        "index": idx,
        "operstate": operstate,
        "type": get_interface_type(ifname),  # NEW FIELD
        "ipv4_addresses": ipv4_addresses,
        "gateway": gateway,
        "timestamp": datetime.now().isoformat(),
    }
```

3. The `network_discovery` and `network_change` events will now include the `type` field.

---

### Task 2: Update Interface Cache to Include Type

**File:** `src/tools/interface_cache.py`

**Changes:**

1. Update cache structure to include type:

```python
# Cache structure:
# INTERFACE_CACHE = {
#     "eth0": {
#         "subnet": "192.168.1.0/24",
#         "gateway": "192.168.1.1",
#         "type": "ethernet",  # NEW
#         "addresses": [...]
#     },
#     "wlan0": {
#         "subnet": "10.0.0.0/24",
#         "gateway": "10.0.0.1",
#         "type": "wifi",  # NEW
#         "addresses": [...]
#     }
# }
```

2. Add `get_interface_type()` accessor:

```python
def get_interface_type(interface_name: str) -> str:
    """
    Get the type of an interface from cache.

    Returns:
        "wifi" or "ethernet" (defaults to "ethernet" if unknown)
    """
    if interface_name in INTERFACE_CACHE:
        return INTERFACE_CACHE[interface_name].get("type", "ethernet")
    return "ethernet"
```

3. Update `update_interface_cache()` to store type from netmon events.

**File:** `src/tools/network_event_listener.py`

Update event handlers to extract and store interface type:

```python
# In _handle_network_discovery():
for iface in interfaces:
    interface_name = iface.get("interface")
    interface_type = iface.get("type", "ethernet")  # NEW
    update_interface_cache(interface_name, {
        "subnet": ...,
        "gateway": ...,
        "type": interface_type,  # NEW
        "addresses": ...
    })
```

---

### Task 3: Create IPvlan Network Driver Support

**File:** `src/tools/docker_tools.py`

**Changes:**

1. Add `get_or_create_ipvlan_network()` function:

```python
def get_or_create_ipvlan_network(
    parent_interface: str,
    parent_subnet: str = None,
    parent_gateway: str = None,
):
    """
    Get existing IPvlan L2 network for a parent interface or create a new one.

    IPvlan L2 mode allows containers to share the parent's MAC address while
    having unique IPs. Essential for WiFi where APs only accept authenticated MACs.

    Args:
        parent_interface: Physical network interface (e.g., "wlan0")
        parent_subnet: Subnet in netmask or CIDR format (optional, auto-detected)
        parent_gateway: Gateway address (optional, auto-detected)

    Returns:
        Docker network object
    """
    # Resolve subnet (same logic as MACVLAN)
    if parent_subnet and parent_gateway:
        if is_cidr_format(parent_subnet):
            pass
        else:
            cidr_prefix = netmask_to_cidr(parent_subnet)
            network_base = calculate_network_base(parent_gateway, parent_subnet)
            parent_subnet = f"{network_base}/{cidr_prefix}"
    else:
        parent_subnet, parent_gateway = detect_interface_network(parent_interface)
        if not parent_subnet:
            raise ValueError(
                f"Could not detect subnet for interface {parent_interface}"
            )

    # Different naming pattern from MACVLAN
    network_name = f"ipvlan_{parent_interface}_{parent_subnet.replace('/', '_')}"

    # Check for existing network
    try:
        network = CLIENT.networks.get(network_name)
        if _validate_network_exists(network):
            log_debug(f"IPvlan network {network_name} already exists, reusing it")
            return network
    except docker.errors.NotFound:
        pass

    log_info(
        f"Creating new IPvlan L2 network {network_name} for parent interface "
        f"{parent_interface} with subnet {parent_subnet}"
    )

    ipam_pool_config = {"subnet": parent_subnet}
    if parent_gateway:
        ipam_pool_config["gateway"] = parent_gateway

    ipam_pool = docker.types.IPAMPool(**ipam_pool_config)
    ipam_config = docker.types.IPAMConfig(pool_configs=[ipam_pool])

    network = CLIENT.networks.create(
        name=network_name,
        driver="ipvlan",
        driver_opts={
            "parent": parent_interface,
            "ipvlan_mode": "l2",
        },
        ipam=ipam_config,
    )
    log_info(f"IPvlan network {network_name} created successfully")
    return network
```

2. Add `get_ipvlan_network_key()` for validation (mirrors MACVLAN logic):

```python
def get_ipvlan_network_key(
    parent_interface: str,
    parent_subnet: str = None,
    parent_gateway: str = None,
) -> str:
    """Compute the IPvlan network key for validation."""
    # Same logic as get_macvlan_network_key but with ipvlan_ prefix
    if parent_subnet and parent_gateway:
        if is_cidr_format(parent_subnet):
            resolved_subnet = parent_subnet
        else:
            cidr_prefix = netmask_to_cidr(parent_subnet)
            network_base = calculate_network_base(parent_gateway, parent_subnet)
            resolved_subnet = f"{network_base}/{cidr_prefix}"
    else:
        resolved_subnet, _ = detect_interface_network(parent_interface)
        if not resolved_subnet:
            return f"ipvlan_{parent_interface}_unknown"

    return f"ipvlan_{parent_interface}_{resolved_subnet.replace('/', '_')}"
```

---

### Task 4: Update Container Creation for WiFi

**File:** `src/use_cases/docker_manager/create_runtime_container.py`

**Changes:**

1. Import the new interface type function:

```python
from tools.interface_cache import get_interface_type
from tools.docker_tools import (
    CLIENT,
    get_or_create_macvlan_network,
    get_or_create_ipvlan_network,  # NEW
    create_internal_network,
    get_macvlan_network_key,
)
```

2. Update vNIC processing loop to detect interface type:

```python
for vnic_config in vnic_configs:
    vnic_name = vnic_config.get("name")
    parent_interface = vnic_config.get("parent_interface")
    parent_subnet = vnic_config.get("subnet")
    parent_gateway = vnic_config.get("gateway")

    # Detect interface type from cache
    interface_type = get_interface_type(parent_interface)
    vnic_config["_interface_type"] = interface_type  # Store for DHCP
    vnic_config["_is_ipvlan"] = interface_type == "wifi"  # Store flag

    log_debug(
        f"Processing vNIC {vnic_name} for {interface_type} interface {parent_interface}"
    )

    # Choose network driver based on interface type
    if interface_type == "wifi":
        log_info(f"Using IPvlan L2 for WiFi interface {parent_interface}")
        network = get_or_create_ipvlan_network(
            parent_interface, parent_subnet, parent_gateway
        )
    else:
        network = get_or_create_macvlan_network(
            parent_interface, parent_subnet, parent_gateway
        )

    networks.append((network, vnic_config))
```

3. Update DHCP vNIC collection to include IPvlan flag:

```python
dhcp_vnics = []
for network, vnic_config in networks:
    network_mode = vnic_config.get("network_mode", "dhcp")
    if network_mode == "dhcp":
        vnic_name = vnic_config.get("name")
        mac_address = network_settings.get(network.name, {}).get("MacAddress")
        is_ipvlan = vnic_config.get("_is_ipvlan", False)

        if container_pid > 0:
            dhcp_vnics.append({
                "vnic_name": vnic_name,
                "mac_address": mac_address,
                "container_pid": container_pid,
                "use_client_id": is_ipvlan,  # IPvlan needs client-id
            })
```

4. Update vNIC persistence to include network type:

```python
# When saving vNIC configs, include network type for reconnection
vnic_config["_network_driver"] = "ipvlan" if is_ipvlan else "macvlan"
save_vnic_configs(container_name, vnic_configs)
```

---

### Task 5: Update netmon DHCP for IPvlan

**File:** `install/autonomy-netmon.py`

**Changes:**

1. Add interface finder for IPvlan (cannot use MAC):

```python
def _find_interface_for_ipvlan(
    self, container_pid: int
) -> Optional[str]:
    """
    Find the IPvlan interface in a container's netns.

    Since IPvlan interfaces share the parent's MAC, we can't identify by MAC.
    We find by exclusion: not loopback, not on internal bridge subnet (172.x.x.x).

    Returns:
        Interface name or None if not found
    """
    try:
        result = subprocess.run(
            ["nsenter", "-t", str(container_pid), "-n", "ip", "-j", "addr", "show"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None

        interfaces = json.loads(result.stdout)

        for iface in interfaces:
            ifname = iface.get("ifname", "")

            # Skip loopback
            if ifname == "lo":
                continue

            # Check if interface is on internal bridge (172.x.x.x)
            addr_info = iface.get("addr_info", [])
            on_internal = False
            for addr in addr_info:
                if addr.get("family") == "inet":
                    local_addr = addr.get("local", "")
                    if local_addr.startswith("172."):
                        on_internal = True
                        break

            if on_internal:
                continue

            # This should be our IPvlan interface
            logger.info(f"Found IPvlan interface: {ifname}")
            return ifname

        logger.warning("Could not find IPvlan interface by exclusion")
        return None

    except Exception as e:
        logger.error(f"Error finding IPvlan interface: {e}")
        return None
```

2. Update `start_dhcp()` to support client-id:

```python
def start_dhcp(
    self,
    container_name: str,
    vnic_name: str,
    mac_address: str,
    container_pid: int,
    use_client_id: bool = False,  # NEW PARAMETER
) -> Dict[str, Any]:
    """
    Start a DHCP client for a container's vNIC.

    Args:
        container_name: Name of the container
        vnic_name: Name of the virtual NIC
        mac_address: MAC address (for MACVLAN) or None (for IPvlan)
        container_pid: PID of the container's init process
        use_client_id: If True, use DHCP option 61 client-id (for IPvlan)
    """
    key = f"{container_name}:{vnic_name}"

    # ... existing validation code ...

    # Find interface - method depends on network type
    if use_client_id:
        # IPvlan mode - find by exclusion
        logger.info(f"Looking for IPvlan interface in container PID {container_pid}")
        interface = self._find_interface_for_ipvlan(container_pid)
    else:
        # MACVLAN mode - find by MAC (existing behavior)
        logger.info(f"Looking for interface with MAC {mac_address}")
        interface = None
        for attempt in range(10):
            interface = self._find_interface_by_mac(container_pid, mac_address)
            if interface:
                break
            time.sleep(0.3)

    if not interface:
        return {"success": False, "error": "Interface not found"}

    # Build udhcpc command
    cmd = [
        "nsenter", "-t", str(container_pid), "-n",
        "udhcpc", "-f", "-i", interface,
        "-s", "/usr/share/udhcpc/default.script",
        "-t", "5", "-T", "3",
    ]

    # For IPvlan: add unique client-id
    if use_client_id:
        client_id_str = f"{container_name}:{vnic_name}"
        client_id_hex = client_id_str.encode('utf-8').hex()
        # Option 61 (0x3d) = Client Identifier
        cmd.extend(["-x", f"0x3d:{client_id_hex}"])
        logger.info(f"Using DHCP client-id: {client_id_str}")

    # ... rest of existing code ...

    # Store use_client_id for DHCP restarts
    self.last_lease_state[key]["use_client_id"] = use_client_id
```

3. Update `_monitor_leases()` to preserve client-id on restart.

4. Update `handle_command()` to accept `use_client_id` parameter.

---

### Task 6: Update network_event_listener

**File:** `src/tools/network_event_listener.py`

**Changes:**

1. Update DHCP start calls to pass `use_client_id`:

```python
async def start_dhcp(
    self,
    container_name: str,
    vnic_name: str,
    mac_address: str,
    container_pid: int,
    use_client_id: bool = False,  # NEW
):
    """Request netmon to start DHCP for a container's vNIC."""
    command = {
        "command": "start_dhcp",
        "container_name": container_name,
        "vnic_name": vnic_name,
        "mac_address": mac_address,
        "container_pid": container_pid,
        "use_client_id": use_client_id,  # NEW
    }
    return await self._send_command(command)
```

2. Update reconnection logic to use correct network type:

```python
async def _reconnect_container_vnic(self, container_name, vnic_config, new_subnet, new_gateway):
    """Reconnect a container's vNIC to the appropriate network."""

    interface_type = vnic_config.get("_interface_type", "ethernet")
    is_ipvlan = interface_type == "wifi"

    if is_ipvlan:
        network = get_or_create_ipvlan_network(
            vnic_config["parent_interface"], new_subnet, new_gateway
        )
    else:
        network = get_or_create_macvlan_network(
            vnic_config["parent_interface"], new_subnet, new_gateway
        )

    # ... reconnection logic ...

    # Restart DHCP with correct mode
    if vnic_config.get("network_mode") == "dhcp":
        await self.start_dhcp(
            container_name,
            vnic_config["name"],
            vnic_config.get("mac_address"),
            container_pid,
            use_client_id=is_ipvlan,  # NEW
        )
```

---

## Cleanup and Deletion

### Runtime Container Deletion

**File:** `src/use_cases/docker_manager/delete_runtime_container.py`

The existing deletion logic handles cleanup correctly because:

1. **Container removal** - Works the same for IPvlan and MACVLAN
2. **vNIC config deletion** - Already implemented
3. **Network cleanup** - IPvlan networks are shared (like MACVLAN), not deleted per-container

**Note:** Line 24 in the current code states "MACVLAN networks are NOT removed as they may be shared by other containers." The same applies to IPvlan networks.

### Orchestrator Self-Destruct

**File:** `src/use_cases/docker_manager/selfdestruct.py`

**Changes Required:**

1. Add IPvlan network pattern (line ~23):

```python
# Existing pattern
MACVLAN_NETWORK_PATTERN = re.compile(r"^macvlan_[a-zA-Z0-9]+_\d+\.\d+\.\d+\.\d+_\d+$")

# NEW: IPvlan network pattern
IPVLAN_NETWORK_PATTERN = re.compile(r"^ipvlan_[a-zA-Z0-9]+_\d+\.\d+\.\d+\.\d+_\d+$")
```

2. Update `_cleanup_orchestrator_networks()` to include IPvlan:

```python
def _cleanup_orchestrator_networks():
    """
    Clean up all orchestrator-created networks that are no longer in use.

    This removes:
    - Internal bridge networks matching UUID_internal pattern
    - MACVLAN networks matching macvlan_{interface}_{subnet}_{mask} pattern
    - IPvlan networks matching ipvlan_{interface}_{subnet}_{mask} pattern  # NEW

    Networks with connected containers are skipped.
    """
    # ... existing code ...

    for network in all_networks:
        network_name = network.name

        is_internal = INTERNAL_NETWORK_PATTERN.match(network_name)
        is_macvlan = MACVLAN_NETWORK_PATTERN.match(network_name)
        is_ipvlan = IPVLAN_NETWORK_PATTERN.match(network_name)  # NEW

        if not is_internal and not is_macvlan and not is_ipvlan:  # UPDATED
            continue

        # ... rest of cleanup logic (unchanged) ...
```

### DHCP Process Cleanup

DHCP cleanup happens automatically:

1. When a container is deleted, its network namespace is destroyed
2. The `udhcpc` process running in that namespace is terminated
3. netmon's `_monitor_leases()` detects the dead process and cleans up state

No additional changes needed for DHCP cleanup.

### vNIC Persistence Cleanup

The existing `delete_vnic_configs()` function handles cleanup. The additional `_interface_type` and `_is_ipvlan` fields are deleted along with the rest of the config.

---

## Testing Strategy

### Unit Testing

1. **Interface type detection:**
   - Mock `/sys/class/net/{ifname}/wireless` existence
   - Test with various interface names (eth0, wlan0, enp0s3, wlp2s0)

2. **Network creation:**
   - Test IPvlan network creation with valid parameters
   - Test overlap handling

3. **DHCP client-id:**
   - Verify hex encoding of client-id string
   - Test command construction

### Integration Testing

1. **Ethernet path (regression):**
   - Create vPLC on Ethernet interface
   - Verify MACVLAN network created
   - Verify DHCP works with MAC-based identification

2. **WiFi path (new):**
   - Create vPLC on WiFi interface
   - Verify IPvlan network created
   - Verify DHCP works with client-id

3. **Mixed scenario:**
   - Create vPLCs on both Ethernet and WiFi
   - Verify correct network driver selection

4. **Reconnection:**
   - Trigger network change event
   - Verify containers reconnect with correct network type

5. **Deletion:**
   - Delete vPLC
   - Verify cleanup
   - Self-destruct orchestrator
   - Verify all IPvlan networks cleaned up

### Manual Testing Checklist

- [ ] Create vPLC on Ethernet - verify MACVLAN used
- [ ] Create vPLC on WiFi - verify IPvlan used
- [ ] Verify vPLC reachable from other devices on network
- [ ] Verify vPLC can reach other devices on network
- [ ] Test DHCP IP assignment on WiFi vPLC
- [ ] Test static IP on WiFi vPLC
- [ ] Disconnect/reconnect WiFi - verify container reconnects
- [ ] Delete vPLC - verify network cleanup
- [ ] Self-destruct - verify IPvlan networks removed

---

## Rollback Plan

If issues are discovered after deployment:

1. **Revert to MACVLAN-only:**
   - The interface type detection defaults to "ethernet"
   - Setting `get_interface_type()` to always return "ethernet" disables IPvlan

2. **Network cleanup:**
   - IPvlan networks follow same cleanup patterns as MACVLAN
   - Self-destruct handles both network types

3. **No data migration needed:**
   - vNIC configs are backward compatible
   - Missing `_interface_type` field defaults to "ethernet"

---

## File Summary

| File | Changes |
|------|---------|
| `install/autonomy-netmon.py` | Add `get_interface_type()`, update `get_interface_info()`, add `_find_interface_for_ipvlan()`, update `start_dhcp()` |
| `src/tools/interface_cache.py` | Add type field to cache, add `get_interface_type()` accessor |
| `src/tools/docker_tools.py` | Add `get_or_create_ipvlan_network()`, `get_ipvlan_network_key()` |
| `src/tools/network_event_listener.py` | Update cache updates, update DHCP calls with `use_client_id` |
| `src/use_cases/docker_manager/create_runtime_container.py` | Detect interface type, select network driver, pass IPvlan flag to DHCP |
| `src/use_cases/docker_manager/selfdestruct.py` | Add `IPVLAN_NETWORK_PATTERN`, update `_cleanup_orchestrator_networks()` |

---

## References

- [Docker IPvlan Documentation](https://docs.docker.com/network/drivers/ipvlan/)
- [BusyBox udhcpc README](https://udhcp.busybox.net/README.udhcpc)
- [RFC 2132 - DHCP Options](https://www.rfc-editor.org/rfc/rfc2132) (Option 61: Client Identifier)
- [Linux IPvlan Documentation](https://www.kernel.org/doc/Documentation/networking/ipvlan.txt)
