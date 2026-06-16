# ansible-role-consul

Install and configure [HashiCorp Consul](https://www.consul.io/) on Debian, as a
Consul **server** or as a Consul **agent (client)**.

This role installs Consul from the official **HashiCorp APT
repository** rather than downloading binaries, keeping the node on a supported
upgrade path.

## What it does

- Adds the HashiCorp apt repository and GPG key and installs the `consul` package
  (the package provides the `consul` user, `/opt/consul`, `/etc/consul.d` and the
  `consul.service` systemd unit).
- Renders `/etc/consul.d/consul.hcl` for a server, bootstrap or client node.
- Drops a systemd override forcing **`Type=simple`** (see below).
- Configures host DNS to forward the Consul domain to the local Consul DNS
  interface: `systemd-resolved` when it is running, otherwise `dnsmasq`.
- Starts/enables the service and waits for a cluster leader.

### Why the `Type=simple` override

The HashiCorp apt package ships the unit with `Type=notify`. That has a flaw when
starting a **single node**: the unit never signals "ready", so systemd waits and
eventually times out. The role writes
`/etc/systemd/system/consul.service.d/override.conf` with `Type=simple` to fix
this.

### DNS resolver

The role configures whichever stub resolver the host runs, decided automatically
at runtime — there is **no toggle** for it:

- If `systemd-resolved` is running, it is pointed at consul's DNS port directly
  (`/etc/systemd/resolved.conf.d/10-consul.conf` with
  `DNS=127.0.0.1:<dns_port>` and a routing-only `Domains=~<consul_domain>`).
- Otherwise, **dnsmasq is installed** and configured to forward the consul
  domain. dnsmasq is no longer optional and there is no `consul_dnsmasq_enable`
  variable: when `systemd-resolved` is absent, dnsmasq is the resolver.

## Requirements

- Debian (bullseye / bookworm / trixie).
- The [`wazo.metadata`](https://github.com/wazo-platform/ansible-role-metadata)
  role (a dependency) provides `metadata_owner` / `metadata_environment`, used by
  the `consul_datacenter` / `consul_domain` defaults.
- The molecule test image is hosted on AWS ECR, so Docker must be authenticated against the registry before running `tox`. With the AWS CLI configured, run:
```sh
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin 119948825560.dkr.ecr.eu-west-1.amazonaws.com
```

## Role variables

See [defaults/main.yml](defaults/main.yml) for the full list. Key variables:

| Variable | Default | Description |
| --- | --- | --- |
| `consul_enabled` | `true` | Toggle the whole role. |
| `consul_version` | `""` | Pin a package version, e.g. `1.20.5`. Empty = latest available. |
| `consul_install_upgrade` | `false` | Upgrade the package each run (only when `consul_version` is unset). |
| `consul_datacenter` | `"{{ metadata_owner }}-{{ metadata_environment }}"` | Consul datacenter name. |
| `consul_domain` | `"{{ metadata_environment }}.{{ metadata_owner }}"` | Consul DNS domain. |
| `consul_disable_update_check` | `true` | Disable Consul's update check. |
| `consul_node_role` | `server` | `server`, `bootstrap` or `client`. |
| `consul_bootstrap_expect` | `true` | Emit `bootstrap_expect` (ignored for the `bootstrap` role). |
| `consul_bootstrap_expect_value` | `""` | Expected server count. Empty = computed from the number of server nodes in the `all` inventory group. |
| `consul_bind_address` | `"{{ ansible_default_ipv4.address }}"` | Bind address. |
| `consul_advertise_address_wan` | `""` | WAN advertise address (servers). |
| `consul_translate_wan_address` | `false` | Prefer WAN addresses when translating between datacenters. |
| `consul_client_address` | `0.0.0.0` | Client (API/DNS) bind address. |
| `consul_addresses` | `{dns,grpc,http,https: 0.0.0.0}` | Per-API bind interfaces. |
| `consul_ports` | `{dns: 8600, http: 8500, https/grpc: -1, serf_lan: 8301, serf_wan: 8302, server: 8300}` | Listener ports (`-1` disables). |
| `consul_raft_protocol` | `3` | Raft protocol version. |
| `consul_performance` | `{leave_drain_time: 5s, raft_multiplier: 1, rpc_hold_timeout: 7s}` | Performance tuning block. |
| `consul_enable_script_checks` | `false` | Allow script health checks. |
| `consul_enable_local_script_checks` | `false` | Allow local script health checks. |
| `consul_encrypt_enable` | `true` | Enable gossip encryption (set `consul_raw_key`). |
| `consul_raw_key` | `""` | Gossip encryption key (`consul keygen`); supply via vault. |
| `consul_join` | `[]` | Static LAN peers (used when cloud autodiscovery is off). |
| `consul_join_wan` | `[]` | Static WAN peers. |
| `consul_retry_interval` | `30s` | LAN re-join interval. |
| `consul_retry_max` | `0` | Max LAN join attempts (`0` = infinite). |
| `consul_cloud_autodiscovery` | `false` | Use a cloud `retry_join` string instead of static peers. |
| `consul_cloud_autodiscovery_string` | `""` | e.g. `provider=aws tag_key=Service tag_value=consul addr_type=private_v4`. |
| `consul_dnsmasq_servers` | `[169.254.169.253, 9.9.9.9]` | Upstream DNS servers for dnsmasq (only used on the dnsmasq path). |

> **Note on `bootstrap_expect`:** with `consul_bootstrap_expect: true` and an
> empty `consul_bootstrap_expect_value`, the role counts the server-role hosts in
> the `all` inventory group (matching the old `brianshumate.consul` behavior,
> which always used `consul_group_name: all`). Set `consul_bootstrap_expect_value`
> to an integer to override.

## Example playbooks

Consul server with AWS cloud autodiscovery:

```yaml
- hosts: consul_servers
  become: true
  roles:
    - role: wazo.consul
      vars:
        consul_version: 1.20.5
        consul_node_role: server
        consul_bootstrap_expect: true
        consul_bind_address: "{{ ansible_default_ipv4.address }}"
        consul_cloud_autodiscovery: true
        consul_cloud_autodiscovery_string: >-
          provider=aws tag_key=Service tag_value=consul addr_type=private_v4
```

Consul agent (client):

```yaml
- hosts: app_servers
  become: true
  roles:
    - role: wazo.consul
      vars:
        consul_version: 1.20.5
        consul_node_role: client
        consul_cloud_autodiscovery: true
        consul_cloud_autodiscovery_string: >-
          provider=aws tag_key=Service tag_value=consul addr_type=private_v4
```

## Testing

```sh
tox -e linters                     # yamllint, ansible-lint, flake8, black, pre-commit
tox -e molecule-ansible8           # Debian 11 / Ansible 8  — dnsmasq path
tox -e molecule-ansible8-debian12  # Debian 12 / Ansible 8  — systemd-resolved path
tox -e molecule-ansible13          # Debian 13 / Ansible 13 — systemd-resolved path
```

There is a single molecule scenario (`molecule/default`). The DNS resolver path
it exercises is selected by the `CONSUL_DNS_RESOLVER` environment variable —
`systemd-resolved` (default) or `dnsmasq` — which the `prepare.yml` and the
testinfra checks both read. The tox environments above set it accordingly, so
each Debian version is tested against the resolver it uses in practice.

To run the scenario directly against a given path:

```sh
CONSUL_DNS_RESOLVER=dnsmasq molecule test
CONSUL_DNS_RESOLVER=systemd-resolved molecule test
```

## License

MIT

## Author Information

Wazo Developers for Wazo https://wazo.io
