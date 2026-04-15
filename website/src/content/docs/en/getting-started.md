---
title: Getting Started
description: Install Meridian and deploy your first proxy server in two minutes.
order: 1
section: guides
---

One command sets up an undetectable proxy server with hardened defaults. This guide gets you from zero to a running deployment in about five minutes.

## Prerequisites

You need:
- A **VPS** running Debian or Ubuntu (root SSH key access)
- A **terminal** on your local machine (macOS, Linux, or WSL)

## Install the CLI

```
curl -sSf https://getmeridian.org/install.sh | bash
```

This installs the `meridian` command via [uv](https://docs.astral.sh/uv/) (preferred) or pipx.

You can run this on your local machine or directly on the VPS. A local machine is recommended — it lets you run `meridian test` from outside the server and keeps credentials on your own device.

## Deploy

```
meridian deploy
```

The interactive wizard asks for your server IP, SSH user, and camouflage target (SNI). Smart defaults are provided for everything.

Or specify everything upfront:

```
meridian deploy 1.2.3.4 --sni www.microsoft.com
```

If you're running directly on the VPS as root, skip SSH entirely:

```
meridian deploy local
```

## What happens

1. **Installs Docker** and deploys Xray via the 3x-ui management panel
2. **Generates x25519 keypair** — unique keys for Reality authentication
3. **Hardens the server** — UFW firewall, SSH key-only auth, BBR congestion control
4. **Configures VLESS+Reality** on port 443 — impersonates a real TLS server
5. **Enables XHTTP transport** — additional stealth layer, routed through nginx
6. **Outputs QR codes** and saves an HTML connection page

## Where things live

Meridian connects to the VPS via SSH (or runs directly on it with `deploy local`). After deploy, state is cached locally:

| What | Where |
|------|-------|
| Credentials & keys | `~/.meridian/credentials/<IP>/` on your machine |
| Server registry | `~/.meridian/servers` on your machine |
| Proxy services | Docker, Xray, nginx on the VPS |

When you run `meridian client add alice`, Meridian looks up the server in your local registry, SSHes in, creates the client, and updates the local cache. With multiple servers, target a specific one with `--server NAME`.

## Connect

The deploy command outputs:
- A **QR code** you can scan with your phone
- An **HTML file** with connection links to share with family
- A **shareable URL** (if server-hosted pages are enabled)

Install one of these apps, then scan the QR code or tap "Open in App":

| Platform | App |
|----------|-----|
| iOS | [v2RayTun](https://apps.apple.com/app/v2raytun/id6476628951) |
| Android | [v2rayNG](https://github.com/2dust/v2rayNG/releases/latest) |
| Windows | [v2rayN](https://github.com/2dust/v2rayN/releases/latest) |
| All platforms | [Hiddify](https://github.com/hiddify/hiddify-app/releases/latest) |

## Add more users

```
meridian client add alice
```

Each client gets their own key and connection page. List clients with `meridian client list`, revoke with `meridian client remove alice`.

## Manage servers

When you manage multiple VPS deployments:

```
meridian server list                # view all managed servers
meridian server add 5.6.7.8        # add an existing server
meridian server remove finland     # remove from registry
```

The `--server` flag lets you target a specific server for any command: `meridian client add alice --server finland`.

## Declarative workflow

Once you have more than one server, you can manage the whole fleet declaratively. Describe the desired state in `~/.meridian/cluster.yml`, run `meridian plan` to preview the diff, and `meridian apply` to converge.

A minimal desired-state block:

```yaml
desired_nodes:
  - host: 198.51.100.1
    name: germany-1
    sni: www.microsoft.com
  - host: 198.51.100.2
    name: finland-1
    sni: www.microsoft.com

desired_relays:
  - host: 198.51.100.10
    name: moscow-relay
    exit_node: germany-1          # name or IP

desired_clients:
  - alice
  - bob

subscription_page:
  enabled: true                    # self-hosted Remnawave subscription page
```

```
meridian plan                      # shows a Terraform-style diff: + adds, - removes, ~ updates
meridian apply --yes               # converge (destructive actions still prompt once)
```

Each section is independent. Omitting `desired_clients` entirely leaves client management imperative (`meridian client add/remove` still works); listing it with `[]` tells Meridian to remove every client. Same pattern for `desired_nodes` and `desired_relays`.

`meridian plan` exits `0` when the cluster is converged, `2` when changes are pending — so you can gate CI workflows on it. See [CLI reference](/docs/en/cli-reference/#meridian-plan) for full options.

## Next steps

- [Deploy guide](/docs/en/deploy/) — full deployment walkthrough with all options
- [Relay nodes](/docs/en/relay/) — route through a domestic IP for resilience when the exit IP gets blocked
- [Domain mode](/docs/en/domain-mode/) — add CDN fallback via Cloudflare
- [IP blocked?](/docs/en/recovery/) — step-by-step recovery when your server gets blocked
- [Troubleshooting](/docs/en/troubleshooting/) — common issues and fixes
