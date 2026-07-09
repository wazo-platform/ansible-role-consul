import os

import pytest
import testinfra.utils.ansible_runner

testinfra_hosts = testinfra.utils.ansible_runner.AnsibleRunner(
    os.environ["MOLECULE_INVENTORY_FILE"]
).get_hosts("all")

# Which DNS resolver path the converge exercised (see prepare.yml).
RESOLVER = os.environ.get("CONSUL_DNS_RESOLVER", "systemd-resolved")
IS_DNSMASQ = RESOLVER == "dnsmasq"

resolved_path = pytest.mark.skipif(IS_DNSMASQ, reason="systemd-resolved path only")
dnsmasq_path = pytest.mark.skipif(not IS_DNSMASQ, reason="dnsmasq path only")


# --- Common: consul itself ---------------------------------------------------


@pytest.mark.parametrize("path", ["/etc/consul.d/consul.hcl"])
def test_files(host, path):
    with host.sudo():
        item = host.file(path)
        assert item.exists
        assert item.user == "consul"
        assert item.group == "bin"
        assert item.contains("datacenter =")


def test_telemetry_configured(host):
    with host.sudo():
        item = host.file("/etc/consul.d/telemetry.hcl")
        assert item.exists
        assert item.user == "consul"
        assert item.group == "bin"
        assert item.contains("telemetry {")
        assert item.contains("prometheus_retention_time = ")


def test_systemd_type_override(host):
    with host.sudo():
        item = host.file("/etc/systemd/system/consul.service.d/override.conf")
        assert item.exists
        assert item.contains("Type=simple")


def test_user(host):
    u = host.user("consul")
    assert u.exists


@pytest.mark.parametrize("name", ["consul"])
def test_services(host, name):
    item = host.service(name)
    assert item.is_running
    assert item.is_enabled


def test_is_server(host):
    with host.sudo():
        cmd = host.check_output("consul info")
        assert "server = true" in cmd, cmd


@pytest.mark.parametrize(
    "socket",
    ["tcp://127.0.0.1:8500", "tcp://127.0.0.1:8600"],
)
def test_sockets(host, socket):
    assert host.socket(socket).is_listening


# --- systemd-resolved path ---------------------------------------------------


@resolved_path
def test_systemd_resolved_configured(host):
    with host.sudo():
        item = host.file("/etc/systemd/resolved.conf.d/10-consul.conf")
        assert item.exists
        assert item.contains("DNS=127.0.0.1:8600")


@resolved_path
def test_dnsmasq_not_installed(host):
    assert not host.package("dnsmasq").is_installed


# --- dnsmasq path ------------------------------------------------------------


@dnsmasq_path
def test_dnsmasq_installed(host):
    assert host.package("dnsmasq").is_installed


@dnsmasq_path
def test_dnsmasq_configured(host):
    with host.sudo():
        item = host.file("/etc/dnsmasq.d/10-consul")
        assert item.exists
        assert item.contains("127.0.0.1#8600")


@dnsmasq_path
def test_dnsmasq_running(host):
    svc = host.service("dnsmasq")
    assert svc.is_running


@dnsmasq_path
def test_systemd_resolved_not_configured(host):
    assert not host.file("/etc/systemd/resolved.conf.d/10-consul.conf").exists
