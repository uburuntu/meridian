# Meridian — Architecture Diagrams

## CLI Command Flow

```mermaid
flowchart LR
    User([User]) --> CLI[meridian CLI]
    CLI --> |"setup / client / uninstall"| Ansible[Ansible Playbook]
    CLI --> |"check / scan / diagnostics"| SSH[SSH Commands]
    CLI --> |"client list"| API[Direct API Call]
    CLI --> |"ping"| Local[Local TCP/TLS]

    Ansible --> |ansible_connection: local| Server
    Ansible --> |SSH + become| Server
    SSH --> Server[Target Server]
    API --> |"curl via SSH"| Server
```

## Privilege Escalation

```mermaid
flowchart TD
    Start([meridian command]) --> Where{Running where?}

    Where --> |Laptop| Remote[SSH to server]
    Where --> |Server as root| LocalRoot[Local mode]
    Where --> |Server as non-root| LocalSudo[Local mode + sudo]

    Remote --> UserCheck{User = root?}
    UserCheck --> |Yes| Direct[Direct execution]
    UserCheck --> |No| Become[ansible_become: true]

    LocalRoot --> DirectLocal[bash -c command]
    LocalSudo --> SudoLocal[sudo bash -c command]

    Direct --> Tasks[Ansible tasks]
    Become --> Tasks
    DirectLocal --> Tasks
    SudoLocal --> Tasks
```

## Standalone Mode — No Domain

```mermaid
flowchart TD
    Internet([Internet]) --> |":443"| Xray443["Xray: VLESS+Reality+TCP\n(xtls-rprx-vision)"]
    Internet --> |":XHTTP_PORT"| XrayXH["Xray: VLESS+Reality+XHTTP\n(random port, seeded)"]

    subgraph Docker["Docker: 3x-ui"]
        Xray443
        XrayXH
        Panel["3x-ui Panel\n:2053 (localhost only)"]
    end

    SSHTunnel([SSH Tunnel]) -.-> Panel
```

## Standalone Mode — Domain

```mermaid
flowchart TD
    Internet([Internet]) --> |":443"| HAProxy

    subgraph Server
        HAProxy["HAProxy\n(SNI Router, no TLS termination)"]

        HAProxy --> |"SNI = reality_sni"| Xray["Xray: VLESS+Reality\n:10443"]
        HAProxy --> |"SNI = domain"| Caddy["Caddy: Auto-TLS\n:8443"]

        Caddy --> |"/ws-path"| XrayWSS["Xray: VLESS+WSS\n(internal port)"]
        Caddy --> |"/panel-path"| Panel["3x-ui Panel\n:2053"]
        Caddy --> |"/info-path"| InfoPage["Connection Info Page"]

        Internet2([Internet]) --> |":XHTTP_PORT"| XrayXH["Xray: VLESS+Reality+XHTTP\n(random port)"]

        subgraph Docker["Docker: 3x-ui"]
            Xray
            XrayXH
            XrayWSS
            Panel
        end
    end
```

## Credential Lifecycle

```mermaid
sequenceDiagram
    participant CLI as meridian CLI
    participant Local as ~/.meridian/credentials/
    participant Server as /etc/meridian/
    participant Panel as 3x-ui API

    Note over CLI: First install
    CLI->>CLI: Generate credentials (keys, UUID, password)
    CLI->>Local: Save proxy.yml (BEFORE applying)
    CLI->>Panel: POST /login (default creds)
    CLI->>Panel: POST /panel/setting/updateUser
    CLI->>Panel: POST /panel/api/inbounds/add
    CLI->>Server: Sync credentials (post_tasks)

    Note over CLI: Re-run (idempotent)
    CLI->>Local: Load saved credentials
    CLI->>Panel: POST /login (saved creds)
    CLI->>Panel: GET /panel/api/inbounds/list
    Note over CLI: Inbound exists → skip

    Note over CLI: Cross-machine
    CLI->>Server: SCP /etc/meridian/proxy.yml
    Server->>Local: Copy to local cache

    Note over CLI: Uninstall
    CLI->>Panel: Remove inbounds
    CLI->>Server: Delete /etc/meridian/
    CLI->>Local: Delete credentials/
```

## Client Management

```mermaid
flowchart TD
    Add["meridian client add alice"] --> Login[POST /login]
    Login --> List[GET /panel/api/inbounds/list]
    List --> FindReality[Find VLESS-Reality inbound]
    FindReality --> GenUUID[Generate UUID]
    GenUUID --> AddReality["POST /panel/api/inbounds/addClient\n(reality-alice)"]
    AddReality --> AddXHTTP["POST /panel/api/inbounds/addClient\n(xhttp-alice)"]
    AddXHTTP --> |"domain mode"| AddWSS["POST /panel/api/inbounds/addClient\n(wss-alice)"]
    AddXHTTP --> Output[Generate QR + HTML + TXT]
    AddWSS --> Output

    Remove["meridian client remove alice"] --> Login2[POST /login]
    Login2 --> List2[GET /panel/api/inbounds/list]
    List2 --> FindUUID["Find UUID by email\n(NOT by email — use UUID)"]
    FindUUID --> DelReality["POST /panel/api/inbounds/{id}/delClient/{uuid}"]
    DelReality --> DelXHTTP["POST /panel/api/inbounds/{id}/delClient/{uuid}"]
```

## Install & PATH Resolution

```mermaid
flowchart TD
    Install["curl | bash (install.sh)"] --> Strategy{Install strategy}
    Strategy --> |"preferred"| UV["uv tool install\n→ ~/.local/bin/meridian"]
    Strategy --> |"fallback"| Pipx["pipx install\n→ ~/.local/bin/meridian"]
    Strategy --> |"last resort"| Pip["pip3 --user\n→ ~/.local/bin/meridian"]

    UV --> PATH["Prepend PATH to .bashrc\n(before interactivity guard)"]
    Pipx --> PATH
    Pip --> PATH

    PATH --> Symlink{"sudo -n available?"}
    Symlink --> |Yes| Link["ln -sf → /usr/local/bin/meridian"]
    Symlink --> |No| Skip["Skip (laptop, no sudo)"]

    Link --> Works1["sudo meridian ✓"]
    Link --> Works2["ssh host 'meridian ...' ✓"]
    PATH --> Works3["Interactive shell ✓"]
```

## CI/CD Pipeline

```mermaid
flowchart LR
    Push([git push]) --> CI[CI Workflow]

    subgraph CI[CI]
        Lint[ansible-lint]
        PyTest[pytest\nPython 3.10 + 3.12]
        Ruff[ruff check\n+ format]
        Validate[Syntax check\n+ templates]
        Shell[shellcheck\n+ policy checks]
        Integration[Docker: 3x-ui\nAPI round-trip]
        DryRun[ansible --check]
    end

    CI --> |on success| CD[CD Workflow]
    CD --> |sync| Pages["GitHub Pages\nmeridian.msu.rocks"]

    CD --> |on success| Release[Release Workflow]
    Release --> Tag["Git tag vX.Y.Z"]
    Release --> GHRelease["GitHub Release"]
    Release --> PyPI["Publish to PyPI"]
```
