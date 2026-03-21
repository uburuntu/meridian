# Meridian Refactoring Vision

## North Star
Easy VPN management for censorship avoidance. Target: semi-technical people who share VPN access with less technical people. Leverage existing protocols, don't build them.

## Future Direction
- Multi-protocol: Hysteria2, TUIC, SSH tunnels (as censors adapt)
- Community: contributions, translations, forks for different countries
- Eventually UI tooling (strong foundation first)

## Key Architectural Decisions (from review)

### Credential Format v2 (Protocol-Indexed)
```yaml
version: 2

panel:
  username: abc123
  password: xyz789
  web_base_path: /abc
  info_page_path: /def
  port: 2053

server:
  ip: 1.2.3.4
  domain: example.com
  sni: www.microsoft.com

protocols:
  reality:
    uuid: ...
    private_key: ...
    public_key: ...
    short_id: ...
  wss:
    uuid: ...
    ws_path: /ghi
  xhttp:
    uuid: ...

clients:
  - name: default
    added: "2026-03-21T10:30:00Z"
    reality_uuid: "<UUID>"
    wss_uuid: "<UUID>"
```

- Auto-migrate v1 on load, always write v2 on save
- `None` = "not set" (distinct from empty string)
- Client tracking merged into proxy.yml (drop separate -clients.yml)

### Inbound Type Registry
Shared constants for remark strings, email prefixes, flow values:
```python
INBOUND_TYPES = {
    "reality": InboundType(remark="VLESS-Reality", email_prefix="reality-", flow="xtls-rprx-vision"),
    "wss": InboundType(remark="VLESS-WSS", email_prefix="wss-", flow=""),
    "xhttp": InboundType(remark="VLESS-Reality-XHTTP", email_prefix="xhttp-", flow=""),
}
```

### PanelClient (Python, replaces Ansible API calls)
```python
class ThreeXUIClient:
    def login(self) -> None
    def list_inbounds(self) -> list[Inbound]
    def ensure_inbound(self, config: InboundConfig) -> Inbound
    def add_client(self, inbound_id: int, client: ClientConfig) -> None
    def remove_client(self, client_uuid: str) -> None
    def update_settings(self, settings: dict) -> None
    def generate_keys(self) -> KeyPair
    def generate_uuid(self) -> str
```

### Protocol Abstraction
```python
class ProtocolABC:
    def configure(self, panel: ThreeXUIClient, creds: ServerCredentials) -> None
    def add_client(self, panel: ThreeXUIClient, name: str) -> ClientInfo
    def remove_client(self, panel: ThreeXUIClient, uuid: str) -> None
    def build_url(self, client: ClientInfo, server: ServerInfo) -> str
    def credential_fields(self) -> dict
```

### Chain Mode
- DELETE current code (playbook-chain.yml, xray_relay/, output_relay/)
- KEEP architecture ready: the protocol abstraction + relay concept stays documented
- When whitelists come, rebuild on top of the new protocol abstraction

### Connection Info Templates
- Consolidate 3 → 1 template with Jinja2 conditionals
- demo.html reuses the same template/CSS
- Server-hosted (Caddy) vs local-saved is a conditional, not a separate file

### CI/CD
- Switch docs/ from git-tracked to GitHub Pages deploy artifact
- Merge CD workflow into Release workflow
- Add mypy to CI

### Ansible Scope (after refactoring)
Ansible KEEPS: common, docker, haproxy, caddy (infrastructure)
Ansible LOSES: 3x-ui API calls, output generation, client management (→ Python)

## Execution Order
Wave 1: Chain extraction, Template consolidation, CLI UX, Community+Docs
Wave 2: Credential redesign, Inbound constants, CI/CD restructure
Wave 3: PanelClient Python class
Wave 4: Protocol abstraction
Wave 5: E2E tests, CLAUDE.md trim
