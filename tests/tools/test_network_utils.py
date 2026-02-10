from tools.network_utils import (
    is_cidr_format,
    netmask_to_cidr,
    calculate_network_base,
    resolve_subnet,
    get_macvlan_network_key,
)


class TestIsCidrFormat:
    def test_true(self):
        assert is_cidr_format("192.168.1.0/24") is True

    def test_false(self):
        assert is_cidr_format("255.255.255.0") is False

    def test_slash_only(self):
        assert is_cidr_format("/") is True


class TestNetmaskToCidr:
    def test_24(self):
        assert netmask_to_cidr("255.255.255.0") == 24

    def test_16(self):
        assert netmask_to_cidr("255.255.0.0") == 16

    def test_8(self):
        assert netmask_to_cidr("255.0.0.0") == 8

    def test_32(self):
        assert netmask_to_cidr("255.255.255.255") == 32

    def test_20(self):
        assert netmask_to_cidr("255.255.240.0") == 20


class TestCalculateNetworkBase:
    def test_slash24(self):
        assert calculate_network_base("192.168.1.1", "255.255.255.0") == "192.168.1.0"

    def test_slash16(self):
        assert calculate_network_base("172.16.5.1", "255.255.0.0") == "172.16.0.0"

    def test_slash8(self):
        assert calculate_network_base("10.1.2.3", "255.0.0.0") == "10.0.0.0"

    def test_slash20(self):
        assert calculate_network_base("192.168.17.1", "255.255.240.0") == "192.168.16.0"


class TestResolveSubnet:
    def test_already_cidr(self):
        assert resolve_subnet("192.168.1.0/24", "192.168.1.1") == "192.168.1.0/24"

    def test_from_netmask(self):
        result = resolve_subnet("255.255.255.0", "192.168.1.1")
        assert result == "192.168.1.0/24"

    def test_from_netmask_16(self):
        result = resolve_subnet("255.255.0.0", "172.16.5.1")
        assert result == "172.16.0.0/16"


class TestGetMacvlanNetworkKey:
    def test_explicit_cidr(self):
        key = get_macvlan_network_key("eth0", "192.168.1.0/24", "192.168.1.1")
        assert key == "macvlan_eth0_192.168.1.0_24"

    def test_explicit_netmask(self):
        key = get_macvlan_network_key("eth0", "255.255.255.0", "192.168.1.1")
        assert key == "macvlan_eth0_192.168.1.0_24"

    def test_no_cache_returns_unknown(self):
        key = get_macvlan_network_key("eth0")
        assert key == "macvlan_eth0_unknown"

    def test_no_subnet_no_cache_returns_unknown(self):
        key = get_macvlan_network_key("wlan0", parent_subnet=None, parent_gateway=None)
        assert key == "macvlan_wlan0_unknown"
