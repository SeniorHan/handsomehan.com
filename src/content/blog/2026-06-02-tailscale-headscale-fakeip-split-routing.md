---
title: '打开 Tailscale 就无感翻墙：不用 exit node 的「DNS 决定谁出墙」分流架构'
date: 2026-06-02
description: '本地只需一个 Tailscale 客户端、不开 exit node，打开就自动翻墙+分流。用 Headscale 接管 DNS + fake-ip split-horizon 分流 + advertise 198.18.0.0/15 子网路由，让只有境外流量被选择性拉到翻墙网关，客户端零配置。'
tags: ['Tailscale', 'Headscale', '翻墙', 'DNS', '网络']
---

> 我想要的效果很简单：任何一台设备，装个 Tailscale 客户端、登录我自建的 Headscale，**什么规则都不配、什么开关都不点**，国内网站照常直连飞快，境外网站自动翻墙——而且我**没有**开 exit node。这篇讲清楚这套「无感翻墙 + 分流」是怎么用 DNS + fake-ip + 子网路由三个齿轮咬出来的。

## 传统翻墙的两种姿势，都不够爽

在搞这套之前，我翻墙无非两条路，各有各的别扭：

1. **每台设备各装一个 clash/sing-box，各配一套分流规则**。新设备要重新配、规则要同步、手机上还得折腾。设备一多就是灾难。
2. **Tailscale 开 exit node，全量流量走家里网关**。这个干净，但它是 **all-or-nothing**：一旦选了 exit node，**所有**流量（包括访问百度、淘宝、公司内网）都绕一圈到家里再出去。国内站点平白多绕一段、慢，网关也成了全流量单点。

我要的是第三种：**像 exit node 一样零客户端配置，但只把「该翻墙的流量」拉走，国内流量保持本地直连。** 换句话说，分流的决策不能放在客户端（太重），得放在网络里，而且要能「选择性地」只接管境外流量。

## 核心思路：让 DNS 决定谁出墙，让路由把它拉过来

整套架构就一句话：

> **用 DNS 解析的结果来区分「境内/境外」，给境外域名发一个假 IP（fake-ip）；再把这个假 IP 网段用 Tailscale 子网路由广播出去，于是只有境外流量会被自动路由到家里的翻墙网关。**

它由三个齿轮咬合而成。我家里那台跑 OpenWrt 的软路由（下文叫「网关」）同时扮演了**翻墙出口**和 **tailnet 的 DNS 大脑**两个角色；自建的 **Headscale** 是控制平面。

### 齿轮一：Headscale 接管所有客户端的 DNS

Headscale（Tailscale 的开源自建控制端）有两个关键开关，让我能强行把每台客户端的 DNS 指向网关：

```yaml
# headscale config.yaml
dns:
  magic_dns: true
  override_local_dns: true          # 客户端 DNS 完全由 headscale 接管
  nameservers:
    global:
      - 100.64.0.16                  # ← 指向网关（它的 tailnet IP）
```

`override_local_dns: true` + `global nameserver = 网关` 意味着：**任何 `accept-dns=true` 的客户端，所有 DNS 查询都会被送到网关的 53 端口**，经 `tailscale0` 这条加密隧道。客户端自己一行配置都不用动。

### 齿轮二：网关上的 DNS 大脑做 split-horizon 分流

网关上跑一个 dnsmasq 当「DNS 大脑」，对每个查询按域名分三类处理：

```
tailnet 客户端 (DNS=网关, accept-dns=true)
        │  tailscale0
        ▼
   网关 dnsmasq :53
        ├ 命中 china-list（11.3 万条 .cn/.com 国内域）→ 转公网国内 DNS（119.29.29.29）→ 返回【真实国内 IP】
        ├ 命中内网 split-horizon（如 git.corp.example.com）→ 返回【内网 IP】
        └ 其它（境外域名）→ 转 sing-box fake-ip DNS → 返回【假 IP 198.18.x.x】
```

- **国内域名**拿到的是**真实 IP**。客户端直接走自己所在网络的默认网关出去——国内 SaaS 看到的是你本地的 IP，速度和不翻墙完全一样。
- **境外域名**拿到的是一个 **fake-ip**（取自 `198.18.0.0/15` 这个保留网段）。这个假 IP 是关键道具，看下一个齿轮。

china-list 是一份 11 万多条的国内域名清单（`server=/<域>/119.29.29.29`），每周自动更新一次。里面有一条 `server=/cn/119.29.29.29` 把所有 `*.cn` 一锅端走国内 DNS，所以绝大多数国内 SaaS 自动命中。

### 齿轮三：把 fake-ip 网段用子网路由广播出去

这是点睛之笔。网关向 tailnet **广播（advertise）`198.18.0.0/15` 这条路由**：

```bash
# 网关上（带全已有路由，避免覆盖）
tailscale set --advertise-routes=0.0.0.0/0,::/0,2000::/3,198.18.0.0/15
```

```bash
# 控制端 head 上批准这条路由
headscale routes enable -r <route-id>
```

于是链路自动闭环：

```
客户端访问 google.com
  → DNS 大脑返回 fake-ip 198.18.3.7
  → 客户端发包给 198.18.3.7
  → 因为网关广播了 198.18.0.0/15，Tailscale 把这个包路由到网关
  → 网关 tproxy(:7893) 收下 → sing-box 用 fake-ip 反查出原始域名 google.com
  → 选一个境外节点（vless / hysteria2）出墙
```

而访问 `baidu.com` 时，客户端拿到的是百度的**真实 IP**，不在 `198.18.0.0/15` 里，Tailscale 不接管，直接走本地网络出去。

**分流就这样天然发生了**：境内/境外的区分发生在 DNS 那一层，而「要不要把流量拉到网关」由「这个 IP 是不是 fake-ip 网段」决定。客户端全程无感。

## 为什么这套比 exit node 强

| | exit node | 本方案（fake-ip + 子网路由） |
|---|---|---|
| 接管范围 | **全部**流量 | **只**接管境外（fake-ip）流量 |
| 国内访问 | 绕网关再出去，慢 | 本地直连，和不翻墙一样快 |
| 客户端配置 | 选一下 exit node | accept-routes 即可，零规则 |
| 网关压力 | 扛全流量 | 只扛境外流量 |
| 分流粒度 | 没有，全有或全无 | 按域名（DNS 决定） |

exit node 的本质是「把默认路由 `0.0.0.0/0` 指向网关」，所以无差别全量。而我只广播 `198.18.0.0/15`，**只有解析成 fake-ip 的境外流量落进这条路由**——等于用一条更窄的路由实现了选择性接管。这就是「不用 exit node 也能分流」的核心。

## 客户端只需要做什么

一台新设备接入，全部操作就这些：

```bash
tailscale up --login-server=https://ts.example.com \
  --accept-dns=true \         # 接受 headscale 下发的 DNS（指向网关大脑）
  --accept-routes=true        # 接受网关广播的 198.18.0.0/15 路由
```

iOS 就在 App 里登录自建 server、把「接受 DNS / 接受路由」打开。**之后再不用碰任何翻墙配置**——开着 Tailscale，境外自动翻、境内自动直连。这正是我要的「打开 Tailscale 就无感翻墙 + 分流」。

## 几个用血换来的坑

这套东西看着优雅，真正费时间的是这些反直觉的细节：

- **fake-ip 不能 ping，也不能 traceroute**。`198.18.x.x` 是凭空发的假地址，只有被路由到网关、反查成域名后才有意义。诊断只能用 `dig`/`curl`/`nslookup`，别拿 ping 测。

- **网关自己查境外域名会丢包**。网关本机进程查 `github.com` 也会从自己的 dnsmasq 拿到 fake-ip，但网关本机路由表里没有 `198.18.0.0/15`（那是给 tailnet 客户端的），于是丢包。所以网关上凡是需要联外网的脚本（比如每周更新 china-list 的 cron），都得**绕开 DNS 层直接走本机 socks5 代理**：

  ```bash
  curl -x socks5h://127.0.0.1:7890 https://example.com/china-list.txt
  ```

- **`.cn` 一锅端，但 `.com` 的国内 SaaS 要逐条加白名单**。china-list 里 `*.cn` 整段走国内 DNS，但像某些 `.com` 结尾的国内服务（企业 IM、办公套件等）如果没在清单里，就会被当成境外走 fake-ip → 翻墙节点访问 → 触发风控甚至验证码。发现某个国内站莫名其妙走了代理，先 `grep` 清单确认有没有命中，没有就补一条。

- **UDP/QUIC 也必须走透明代理**。早期只对 TCP 做了 tproxy，结果 QUIC（HTTP/3）的 UDP 流量绕过代理直接出了 WAN，表现为「有些网站时好时坏」。tproxy 规则要同时覆盖 TCP 和 UDP。

- **改 `advertise-routes` 必须带全已有的路由**。`tailscale set --advertise-routes=` 是整体覆盖，漏写一条就丢一条——曾经因此把 exit node 的 `0.0.0.0/0` 覆盖没了。

- **内网域名要做 split-horizon**。公司内网某些域名的内网 IP ≠ 公网 IP（典型如内部 GitLab），得在 DNS 大脑上加一条 `address=/<域名>/<内网IP>` 强制解析到内网地址，同时确保对应内网段也通过另一台节点广播进了 tailnet。

## 可复用要点

- **分流决策放在 DNS 层，不要放在客户端**：境内 → 真实 IP（直连），境外 → fake-ip。客户端零规则。
- **fake-ip 网段（`198.18.0.0/15`）当作「翻墙入口路由」广播**：只有解析成 fake-ip 的境外流量会被 Tailscale 拉到网关，天然实现选择性接管，比 exit node 的全量路由优雅得多。
- **Headscale `override_local_dns + global nameserver` 接管客户端 DNS**：这是「无感」的前提——客户端 DNS 自动指向网关大脑。
- **网关本机查境外要绕开自己的 fake-ip DNS**，走 socks5，否则丢包。
- **`.cn` 可整段放行，`.com` 国内 SaaS 需逐条白名单**，否则被当境外翻墙触发风控。
- **TCP/UDP 都要透明代理**，否则 QUIC 漏网。
- **`advertise-routes` 整体覆盖，永远带全已有路由**。

## 写在最后

这套架构最妙的地方，是把「翻墙」和「分流」两件事拆到了不同的层：**分流交给 DNS（境内真实 IP / 境外 fake-ip），路由只负责把 fake-ip 流量拉到出口**。客户端因此可以彻底「无脑」——它眼里只有一个 Tailscale 开关。

代价是网关那台机器的配置不简单（DNS 大脑 + 透明代理 + 子网路由要协同），但复杂度集中在一处、一次配好，换来的是**每一台新设备都零成本接入**。对一个家里设备一大把的人来说，这笔买卖太划算了。
