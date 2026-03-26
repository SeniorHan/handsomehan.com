---
title: '自托管家庭服务器：26 个 Docker 容器的完整架构'
date: 2026-03-26
description: '基于 Docker Compose 在 Ubuntu Server 上部署 26 个容器，涵盖代理网关、NAS 存储、媒体中心、开发环境和监控告警的完整家庭服务器方案。'
tags: ['Docker', 'HomeLab', 'Linux', '自建服务']
---

## 为什么要自建服务器

云服务按量计费、数据不在自己手里、NAS 买品牌的太贵。于是用一台闲置主机搭了一套全功能家庭服务器，目前跑了 26 个容器，稳定运行中。

## 架构概览

整套系统分四层：

```
┌─────────────────────────────────────────┐
│  网络代理层  Clash + Tailscale + NPM    │
├─────────────────────────────────────────┤
│  存储与媒体  Samba + WebDAV + Jellyfin  │
│             + Immich（照片备份）          │
├─────────────────────────────────────────┤
│  开发部署层  Code-Server + Gitea        │
│             + Portainer                  │
├─────────────────────────────────────────┤
│  监控告警层  Prometheus + Grafana       │
│             + Uptime Kuma               │
└─────────────────────────────────────────┘
```

## 核心技术方案

### 1. 透明代理网关

通过 iptables 将局域网所有流量重定向到 Clash 容器，实现全屋透明代理：

```bash
# 局域网设备只需把网关指向服务器 IP，无需单独配代理
iptables -t nat -A PREROUTING -p tcp -j REDIRECT --to-ports 7892
```

好处是任何设备（电视、游戏机、IoT 设备）都能自动走代理，不需要逐个配置。

### 2. Tailscale 异地组网

出门在外也能访问家里所有服务。Tailscale 基于 WireGuard，延迟低、配置简单：

```yaml
# docker-compose.yml
tailscale:
  image: tailscale/tailscale
  network_mode: host
  cap_add:
    - NET_ADMIN
  volumes:
    - ./tailscale/state:/var/lib/tailscale
```

配合 Tailscale 的 MagicDNS，可以直接用 `http://server:8096` 这样的地址访问 Jellyfin。

### 3. Authelia SSO 统一认证

Nginx Proxy Manager + Authelia 实现所有服务的统一登录，支持 2FA：

```
用户访问 code.home.lan
  → NPM 反向代理
    → Authelia 拦截，要求登录
      → 认证通过，转发到 Code-Server
```

一次登录，所有服务都能访问。

### 4. 自签名 HTTPS

用 mkcert 生成本地 CA 证书，全部服务走 HTTPS：

```bash
mkcert -install
mkcert "*.home.lan"
# 证书导入到 NPM，所有 *.home.lan 子域名自动 HTTPS
```

### 5. 幂等自动化部署

一键 setup.sh 脚本搞定所有初始化：网络配置、磁盘挂载、Docker 环境、GPU 驱动。脚本设计为幂等——重复运行不会出错。

## 服务清单

| 类别 | 服务 | 用途 |
|------|------|------|
| 网络 | Clash, Tailscale, NPM, Authelia | 代理/组网/反代/认证 |
| 存储 | Samba, WebDAV | 文件共享 |
| 媒体 | Jellyfin, Immich | 影音/照片 |
| 开发 | Code-Server, Gitea, Portainer | 远程开发/代码托管/容器管理 |
| 监控 | Prometheus, Grafana, Uptime Kuma | 指标采集/可视化/可用性监控 |
| 其他 | 云游戏、智能家居 | 娱乐/自动化 |

## 踩过的坑

1. **Docker 网段冲突**：Docker 默认会占用 172.17-172.31 网段，如果局域网也在这个范围，会导致容器无法访问局域网设备。解决方案是在 `/etc/docker/daemon.json` 中手动指定 `bip` 和 `default-address-pools`。

2. **GPU 透传给容器**：Jellyfin 硬件转码需要 GPU 直通。NVIDIA 需要安装 `nvidia-container-toolkit`，然后在 compose 里加 `runtime: nvidia`。

3. **数据备份**：用 restic 做增量备份到外置硬盘，cron 定时执行。Immich 的照片数据库单独备份 PostgreSQL dump。

## 总结

自建服务器的核心原则：**Docker 容器化一切 + 自动化部署脚本 + 统一认证网关**。前期配置麻烦一点，但之后运维极其省心，所有服务一个 `docker compose up -d` 就全部启动。
