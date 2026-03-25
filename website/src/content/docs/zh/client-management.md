---
title: 客户端管理
description: 添加用户、分享连接信息和管理访问密钥。
order: 5
section: guides
---

## 添加客户端

```
meridian client add alice
```

这会为"alice"创建一个唯一的连接密钥并显示：
- **终端中的二维码** — 用 VPN 应用扫描它即可立即连接
- **连接 URL** — 每个协议的 VLESS 链接（Reality、XHTTP 和 WSS（如果启用了域名模式））
- **可共享的页面 URL** — 托管在您的服务器上，可通过任何信使发送
- **本地保存的 HTML 文件** — 离线共享的备份

### 收件人看到的内容

可共享的 URL 打开一个连接页面，包括：
- 安装 VPN 应用（v2RayTun、v2rayNG、Hiddify 或 v2rayN）的分步说明
- 每个连接协议的二维码
- 一键"在应用中打开"的深度链接
- 连接状态和使用统计

通过电子邮件、iMessage、Telegram 或任何信使发送该 URL。收件人打开它、安装应用、扫描二维码并连接。无需任何技术知识。

## 显示连接信息

要在任何时候重新显示现有客户端的连接信息：

```
meridian client show alice
```

这会输出相同的二维码、连接 URL 和可共享的页面链接——不会创建新密钥。在以下情况下使用：
- 您需要与某人重新分享连接页面
- 您丢失了原始二维码或 HTML 文件
- 您想验证客户端的连接看起来如何

## 列出客户端

```
meridian client list
```

显示所有客户端及其协议连接（Reality、XHTTP、WSS）。

## 删除客户端

```
meridian client remove alice
```

立即撤销访问权限。客户端的 UUID 将从服务器上的所有入站中删除。

## 多服务器

使用 `--server` 来针对特定的命名服务器：

```
meridian client add alice --server finland
meridian client show alice --server finland
meridian client list --server finland
```

如果您只有一个服务器，它会自动选择。

## 工作原理

客户端名称映射到带有协议前缀的 3x-ui `email` 字段：
- `reality-alice` — Reality 入站
- `xhttp-alice` — XHTTP 入站
- `wss-alice` — WSS 入站（域名模式）

每个客户端在服务器上所有入站中获得唯一的 UUID。
