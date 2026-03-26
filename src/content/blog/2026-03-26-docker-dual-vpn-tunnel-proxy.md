---
title: '一个 Docker 容器搞定双 VPN 隧道自动分流'
date: 2026-03-26
description: '用 Docker + OpenVPN + microsocks 实现开发/生产双 VPN 环境同时在线，通过 Linux 内核路由表自动分流，一个 SOCKS5 端口搞定所有内网访问。'
tags: ['Docker', 'VPN', 'Linux', '网络']
---

## 问题

公司有开发和生产两套 VPN 环境，经常需要同时连。但 VPN 客户端一次只能连一个，来回切换很烦，而且 VPN 一连上就把本机路由全改了，影响其他网络。

## 思路

把 VPN 隧道关进 Docker 容器里：

```
本机 → SOCKS5 代理(:1080) → 容器内部
                              ├── 开发 VPN 隧道 → 开发内网
                              └── 生产 VPN 隧道 → 生产内网
```

容器内跑两个 OpenVPN 客户端 + 一个 SOCKS5 代理（microsocks），用 Linux 路由表自动分流。

## 核心实现

### 路由分流

这是最巧妙的部分——利用 Linux 内核路由表，根据目标 IP 自动选择走哪条隧道：

```bash
# 开发环境网段走 tun0（开发 VPN）
ip route add 10.10.0.0/16 via $DEV_GATEWAY dev tun0

# 生产环境网段走 tun1（生产 VPN）
ip route add 10.20.0.0/16 via $PROD_GATEWAY dev tun1
```

应用层完全不需要关心路由，发给 SOCKS5 代理后内核自动选路。

### DNS 同步

VPN 连接时会推送内部 DNS 服务器，需要同步到容器的 resolv.conf：

```bash
# 从 OpenVPN 的 up 脚本中获取推送的 DNS
echo "nameserver $DNS_DEV" > /etc/resolv.conf
echo "nameserver $DNS_PROD" >> /etc/resolv.conf
```

这样在容器内可以直接解析 `db.dev.internal` 这类内网域名。

### Docker Compose

```yaml
services:
  vpn-proxy:
    build: .
    cap_add:
      - NET_ADMIN
    devices:
      - /dev/net/tun
    ports:
      - "1080:1080"
    volumes:
      - ./dev.ovpn:/etc/openvpn/dev.ovpn
      - ./prod.ovpn:/etc/openvpn/prod.ovpn
```

`NET_ADMIN` 和 `/dev/net/tun` 是 VPN 容器的必要权限。

## 使用方式

本机配好 SOCKS5 代理后，所有工具都能直连内网：

```bash
# SSH 通过代理连开发服务器
ssh -o ProxyCommand="nc -x 127.0.0.1:1080 %h %p" dev-server

# Clash 中配置上游代理
# 浏览器直接访问内网地址
```

也可以在 Clash 里加一条规则，内网网段自动走这个 SOCKS5 代理，其他流量正常出去。

## 优势

- **不污染宿主机路由表**：VPN 隧道完全封装在容器内
- **双隧道同时在线**：不用来回切换
- **一个端口搞定**：所有内网访问统一走 1080 端口
- **Alpine 镜像很小**：容器只有几十 MB

## 总结

这个方案的精髓在于把 VPN 当成"容器内部的网络基础设施"，而不是宿主机的全局网络变更。Linux 路由表的优先级机制天然支持多隧道分流，不需要任何额外的分流软件。
