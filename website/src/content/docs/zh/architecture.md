---
title: 架构
description: 系统架构、流量流向和服务拓扑。
order: 7
section: reference
---

## 服务拓扑

### 独立模式（无域名）

```mermaid
flowchart TD
    Internet((Internet)) -->|Port 443| HAProxy[HAProxy<br>SNI Router]
    HAProxy -->|"SNI = reality_sni"| Xray["Xray Reality<br>:10443"]
    HAProxy -->|"SNI = server IP"| Caddy["Caddy TLS<br>:8443"]
    Caddy -->|/info-path| Page[Connection Page]
    Caddy -->|/panel-path| Panel[3x-ui Panel]
    Caddy -->|/xhttp-path| XrayXHTTP["Xray XHTTP<br>localhost"]
    Internet -->|Port 80| CaddyACME["Caddy<br>ACME challenges"]
```

HAProxy **不**终止 TLS。它从 TLS Client Hello 中读取 SNI 主机名，并将原始 TCP 流转发到相应的后端。

Caddy 通过 ACME `shortlived` 配置文件从 Let's Encrypt 请求 IP 证书（有效期 6 天，自动续期）。如果不支持 IP 证书颁发，将回退到自签证书。

XHTTP 运行在仅限本地的端口上，由 Caddy 反向代理——无需暴露额外的外部端口。

### 域名模式

```mermaid
flowchart TD
    Internet((Internet)) -->|Port 443| HAProxy[HAProxy<br>SNI Router]
    HAProxy -->|"SNI = reality_sni"| Xray["Xray Reality<br>:10443"]
    HAProxy -->|"SNI = domain"| Caddy["Caddy TLS<br>:8443"]
    Caddy -->|/info-path| Page[Connection Page]
    Caddy -->|/panel-path| Panel[3x-ui Panel]
    Caddy -->|/xhttp-path| XrayXHTTP["Xray XHTTP<br>localhost"]
    Caddy -->|/ws-path| XrayWSS["Xray WSS<br>localhost"]
    Internet -->|Port 80| CaddyACME["Caddy<br>ACME challenges"]
    Internet -.->|"CDN (Cloudflare)"| Caddy
```

域名模式添加 VLESS+WSS 作为 CDN 回退路径。流量通过 Cloudflare 的 CDN 经由 WebSocket 流动，即使服务器 IP 被阻断也能工作。

### 中继拓扑

```mermaid
flowchart LR
    Client([Client]) -->|Port 443| Relay["Relay<br>(Realm TCP)"]
    Relay -->|Port 443| Exit["Exit Server<br>(abroad)"]
    Exit --> Internet((Internet))
```

中继节点是一个轻量级 TCP 转发器，运行 [Realm](https://github.com/zhboner/realm)。客户端连接到中继的国内 IP，中继将原始 TCP 转发到国外的出口服务器。所有加密都是端到端的，在客户端和出口之间——中继永远看不到明文。

## Reality 协议如何工作

1. 服务器生成一个 **x25519 密钥对**。公钥与客户端共享，私钥保留在服务器上。
2. 客户端在端口 443 上连接，发送包含伪装域名（例如 `www.microsoft.com`）作为 SNI 的 TLS Client Hello。
3. 对于任何观察者来说，这看起来像一个到 microsoft.com 的正常 HTTPS 连接。
4. 如果一个**探针**发送自己的 Client Hello，服务器会将连接代理到真实的 microsoft.com——探针看到一个有效的证书。
5. 如果客户端包含有效的身份验证（从 x25519 密钥派生），服务器建立 VLESS 隧道。
6. **uTLS** 使 Client Hello 逐字节与 Chrome 相同，击败 TLS 指纹识别。

## 端口分配

| 端口 | 服务 | 模式 |
|------|---------|------|
| 443 | HAProxy (SNI 路由器) | 全部 |
| 80 | Caddy (ACME 挑战) | 全部 |
| 10443 | Xray Reality (内部) | 全部 |
| 8443 | Caddy TLS (内部) | 全部 |
| localhost | Xray XHTTP | 启用 XHTTP 时 |
| localhost | Xray WSS | 域名模式 |
| 2053 | 3x-ui panel (内部) | 全部 |

XHTTP 和 WSS 端口仅限本地——Caddy 在端口 443 上将它们反向代理。

## 配置管道

| # | 步骤 | 目的 |
|---|------|---------|
| 1 | InstallPackages | OS 包 |
| 2 | EnableAutoUpgrades | 无人值守升级 |
| 3 | SetTimezone | UTC |
| 4 | HardenSSH | 仅密钥认证 |
| 5 | ConfigureBBR | TCP 拥塞控制 |
| 6 | ConfigureFirewall | UFW: 22 + 80 + 443 |
| 7 | InstallDocker | Docker CE |
| 8 | Deploy3xui | 3x-ui 容器 |
| 9 | ConfigurePanel | Panel 凭证 |
| 10 | LoginToPanel | API 认证 |
| 11 | CreateRealityInbound | VLESS+Reality |
| 12 | CreateXHTTPInbound | VLESS+XHTTP |
| 13 | CreateWSSInbound | VLESS+WSS (域名) |
| 14 | VerifyXray | 健康检查 |
| 15 | InstallHAProxy | SNI 路由 |
| 16 | InstallCaddy | TLS + 反向代理 |
| 17 | DeployConnectionPage | 二维码 + 页面 |

## 凭证生命周期

1. **生成**：随机凭证（panel 密码、x25519 密钥、客户端 UUID）
2. **本地保存**：`~/.meridian/credentials/<IP>/proxy.yml`——应用到服务器之前保存
3. **应用**：panel 密码更改、入站创建
4. **同步**：凭证复制到服务器上的 `/etc/meridian/proxy.yml`
5. **重新运行**：从缓存加载，不会重新生成（幂等）
6. **跨机器**：`meridian server add IP` 通过 SSH 从服务器获取
7. **卸载**：从服务器和本地机器中删除
