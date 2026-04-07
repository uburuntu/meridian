---
title: 安全
description: 安全设计、漏洞报告和范围。
order: 11
section: reference
---

## 报告漏洞

如果您在 Meridian 中发现安全漏洞：

1. **不要开放公开问题**
2. 给维护者发电子邮件或使用 [GitHub 安全公告](https://github.com/uburuntu/meridian/security/advisories/new)
3. 包含复现步骤和潜在影响

我们的目标是在 48 小时内响应，并将在修复中感谢报告者。

## 安全设计

- **凭证**: 以 `0600` 权限存储在 `~/.meridian/credentials/<IP>/` 中，秘密信息从不通过未使用 `shlex.quote()` 的 shell 命令传递，从 `meridian doctor` 输出中删除。目录权限为 `0700`（仅所有者）。以您的用户身份运行的任何应用程序都可以读取这些文件 — 这是所有在本地存储凭证的 CLI 工具的固有特性（SSH 密钥、云 CLI 令牌等）。如果您的本地计算机在用户级别被入侵，凭证加密也无济于事：恶意软件可以记录密码或拦截 SSH 会话。保护好您的本地计算机。
- **面板访问**: 由 nginx 反向代理在所有模式下通过秘密 HTTPS 路径 — 不需要 SSH 隧道。面板 URL 和凭证在 `~/.meridian/credentials/<IP>/proxy.yml` 中
- **SSH**：默认禁用密码认证
- **防火墙**：UFW 配置为默认拒绝，仅打开端口 22、80 和 443
- **Docker**：3x-ui 镜像固定到已测试的版本
- **TLS**：acme.sh 通过 Let's Encrypt 处理证书，由 nginx 提供服务

## 范围

Meridian 配置代理服务器——它**不**实现加密协议。基础安全取决于：

- [Xray-core](https://github.com/XTLS/Xray-core)——VLESS+Reality 协议
- [3x-ui](https://github.com/MHSanaei/3x-ui)——管理 panel
- [nginx](https://nginx.org/)——SNI 路由和 TLS 终止
