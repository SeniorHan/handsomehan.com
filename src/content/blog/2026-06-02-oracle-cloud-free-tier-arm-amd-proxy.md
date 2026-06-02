---
title: '白嫖甲骨文 ARM + AMD 五台永久免费机：从轮询抢号到 Cloudflare 搭梯子'
date: 2026-06-02
description: '一台 2022 老号 + 轮询脚本抢下甲骨文 3 台 ARM + 2 台 AMD 永久免费机，记录抢号 429 退避、AMD/ARM 两套独立免费额度、TCP QoS 测速玄学，以及 hysteria2(IPv6) + vless/Cloudflare 双路翻墙架构与部署踩坑。'
tags: ['Oracle Cloud', '白嫖', 'Cloudflare', '翻墙', '网络']
---

> 一台四年前注册的甲骨文老号，加一个轮询脚本蹲了 21 小时，换来 3 台永久免费的境外 ARM 服务器；后来又顺手薅了 2 台 AMD——而这两套免费额度，居然是**互不冲突**的。这一路还踩出了测速玄学、双路翻墙架构和一堆部署坑。

## 起因：被遗忘的 2022 老号

甲骨文云（Oracle Cloud）的 **VM.Standard.A1.Flex（Ampere ARM）** 是目前最香的永久免费机型：每月送 **3000 OCPU 小时 + 18000 GB 小时**，折算下来够你长期跑满 **4 核 / 24G 内存 / 200G 块存储 / 10TB 月流量**，可以拆成 1～4 台。问题是 99% 的人手动建会撞 `Out of host capacity`，核心套路只有一条：**先把账号搞定，再用脚本 7×24 轮询 API 抢容量**。

我手里正好有张 2022 年注册的新加坡老号——这等于直接跳过了最难的「过注册关」。先用 OCI CLI 给账号做了个体检：

```bash
# 装 CLI（系统 pip 被 PEP 668 拦了，改用 uv tool 最干净）
uv tool install oci-cli

# 用 openssl 直接生成无 passphrase 的 API key（非交互环境跑不了 oci setup keys）
cd ~/.oci
openssl genrsa -out oci_api_key.pem 2048 && chmod 600 oci_api_key.pem
openssl rsa -pubout -in oci_api_key.pem -out oci_api_key_public.pem
```

把公钥贴进控制台 → 复制配置回填 `~/.oci/config`，鉴权一通，体检结果近乎完美：账号还是 `Always Free` 状态、历史上 0 台实例、**A1 配额 4 OCPU + 24G 全额可用且零占用**。能查到 A1 limit 这件事本身，就证明账号没被偷偷降级。唯一硬伤：新加坡只有 1 个可用区（AD-1），不能像凤凰城那样三个 AD 轮询。

## 抢号脚本：429 才是真正的敌人

目标定为 **1×2C12G + 2×1C6G**，正好打满 4 核配额。我没用现成的开源项目，而是写了个几十行的 `grab.sh`：对每个目标调一次 `oci compute instance launch`，按返回分类处理，用 systemd `--user` 服务后台跑（`Linger=yes`，断 SSH 也不停）。可复用的轮询骨架长这样：

```bash
TARGETS=("han-arm-2c12g|2|12" "han-arm-1c6g-a|1|6" "han-arm-1c6g-b|1|6")
SLEEP_BETWEEN=120   # 单目标间隔，别太密

while :; do
  for t in "${TARGETS[@]}"; do
    name=${t%%|*}
    [[ -f "state/$name.ok" ]] && continue          # 抢到的跳过
    out=$(oci compute instance launch ... 2>&1)
    if echo "$out" | grep -q '"lifecycle-state": "PROVISIONING"'; then
      touch "state/$name.ok"; notify_mail "🎉 抢到 $name"  # 成功落地标记 + 邮件
    elif echo "$out" | grep -qiE 'Out of host capacity'; then
      :                                            # 没货，正常，继续
    elif echo "$out" | grep -qiE 'TooManyRequests|Too many requests|for the user|"status":[[:space:]]*429'; then
      sleep 300                                    # 撞限流，额外退避冷却
    fi
    sleep "$SLEEP_BETWEEN"
  done
done
```

关键的坑全在 **429（TooManyRequests）** 上：

1. **限流被误判**。一开始我的 `grep` 只匹配连写的 `TooManyRequests`，但 OCI 实际返回的是带空格的 `Too many requests for the user`——结果一堆限流被归进「未知错误」。统计口径直接失真，看着像没事，其实每小时被压了 6 次。**教训：错误分类的正则必须照着真实返回文案写，别想当然。**
2. **`for the user` = 账号级限流**。不是 IP 级。说明频率太高时，OCI 是盯着你这个账号收紧的，单纯换 IP 没用，只能降频。我把间隔从 60s 拉到 120s、429 退避从 180s 提到 300s，显式 429 当小时就从 7 次清零。
3. **「未知错误」最后查清是网络超时**。`The connection to endpoint timed out`——代理偶发抖动，跟 OCI 无关，脚本重试即可。

蹲了大约 21 小时（横跨一整夜，新加坡区白天基本零希望，UTC 16:00–20:00 是甜点窗口），3 台 ARM 全部 `PROVISIONING` 落地，邮件一封封进来，脚本自动 `exit 0` 退出。

## 意外发现：AMD 和 ARM 是两套独立的免费额度

抢完 ARM 我一直以为「免费额度就这么多了」。直到某天复查账单——5 分钱（SGD 0.01）的小额告警——顺手把配额翻出来看，才发现自己一直记反了一件事：

> **甲骨文的 Always Free 里，AMD（x86）的 `VM.Standard.E2.1.Micro` 和 ARM 的 `A1.Flex` 是两套完全独立的免费额度。**

我之前以为它们共用一个「总额度」，AMD 不敢碰。实测一查直接打脸——最有力的证据就是：**A1 已经用满 4 核了，如果是「总额度」，E2 Micro 就该开不出来；但查出来 Micro 额度还在**：

```bash
# A1 ARM 核心
oci limits resource-availability ... --service-name compute \
  --limit-name standard-a1-core-count
# → { "available": 246, "used": 4 }      ← 4 核已满（246 是 PAYG 付费天花板，不是免费额度）

# E2.1.Micro 实例数
oci limits resource-availability ... --service-name compute \
  --limit-name vm-standard-e2-1-micro-count
# → { "available": 2, "used": 0 }        ← 还有 2 台没领！
```

再去翻甲骨文官方文档逐字核实（不凭记忆）：Always Free 的 "Available Shapes" 里，A1 和 AMD Micro 是**分开列的两条独立 allocation**——AMD 这边永久免费给你 **2 台 VM.Standard.E2.1.Micro**，每台 1/8 OCPU + 1G 内存。配置弱得可怜，但白嫖的跳板/DNS/探针/备用出口足够了。

于是我把抢号脚本改个 shape 名再跑一遍，又薅下来 2 台 AMD：

- 一个坑：**新加坡 region 不是所有 AD 都提供 E2.1.Micro shape**，有些较新 region 只有 A1。先用 `oci compute shape list` 确认该 region 真的能开，再去抢，别白等。
- 抢 AMD 比 ARM 容易得多——AMD 物理机充裕，基本不撞 `Out of host capacity`，挂上脚本很快就到手。

最终账号下挂了 **3 台 ARM + 2 台 AMD = 5 台永久免费机**，零月租。

## 测速玄学：直连被掐 150 倍，代理/Tunnel 救场

机器到手，从国内服务器 ssh 上去做吞吐测试，结果离谱：同一台机器，前后两次速度差 **40 倍**，一会 23Mbps 一会 0.2Mbps，但 ICMP 始终稳稳 242ms、0% 丢包。

真相是 **国际出口的 TCP 流量整形（QoS）**：链路本身没断，是运营商/国内云出海段对持续大 TCP 流做了限速，控制类小包（ping、敲命令）不受影响。验证下来一张表说清：

| 链路 | 实测吞吐 |
| --- | --- |
| 直连国际线路 | 0.1–23 Mbps（看运气抽奖） |
| 经国内跳板机中转 | 0.1–0.4 Mbps（同一上游，没救） |
| 走境外 SOCKS5 代理 | ~40 Mbps（稳定） |
| 走 Cloudflare Tunnel | ~35 Mbps（稳定 + 隐藏真实 IP） |

代理和 Tunnel 之所以快，是因为出口在境外，**绕开了国内→新加坡那段拥塞的国际海缆**。日常 ssh 上去，给每台机配个别名就行：

```ini
Host my-vps
    HostName <node-ip>
    User ubuntu
    IdentityFile ~/.ssh/id_ed25519
```

> 顺带一提：抢号阶段我纠结过「走代理是不是抢得快」。结论是**不会**——抢号瓶颈在 OCI 后端查容量（5–30 秒），网络层快那点可忽略。但**保持 IP 一致性**很重要：浏览器登录和脚本最好用同一出口，省得同账号冒出两个地理位置触发风控。

## Cloudflare Tunnel：不开端口就把服务挂上公网

测速时顺手把 Cloudflare Tunnel 也搭了，它的价值一句话讲清：在机器上跑 `cloudflared` 客户端**主动连出**到 Cloudflare 边缘，外部访问域名时流量经隧道回到你机器——**不需要公网 IP、不用开任何端口、自动 HTTPS、真实 IP 永不暴露**。它甚至能转发 SSH：

```bash
# 客户端 ~/.ssh/config：
#   ProxyCommand cloudflared access ssh --hostname %h
```

实测 cloudflared 走 SSH 稳定 33–37Mbps，跟 SOCKS5 代理持平，还白送 IP 隐藏 + 防端口爆破——把 OCI 的 22 端口对公网完全关掉都行。

> **脱敏提醒**：`cloudflared tunnel login` 落地的 `cert.pem` 和 tunnel credentials JSON 里含 zoneID/accountID/apiToken/tunnel token，等同账号钥匙，**千万别外发、别进 git**。

## 真正搭梯子：双路接入架构

既然这套链路抗 GFW，自然要拿 5 台机器搭梯子。我最后定的方案是**每台节点「双路接入」**——同一台机器同时挂两条独立通道，客户端自动择优：

```
                      ┌─ 路径 A: hysteria2 (IPv6 直连, UDP/443)
   客户端(home-proxy) ─┤
                      └─ 路径 B: vless + ws ──→ Cloudflare 边缘 ──→ cloudflared tunnel ──→ 节点
```

### 路径 A：hysteria2，故意只走 IPv6

第一条路是 hysteria2，**刻意只监听公网 IPv6**（`[2603:...]:443/udp`），配 salamander 混淆、伪装成某个正常网站、ACME 自动证书、DNS 只放 AAAA 记录走灰云（不经 CDN）：

```yaml
# /etc/hysteria/config.yaml（节选，已脱敏）
listen: "[::]:443"            # 只监听 IPv6
obfs:
  type: salamander
  salamander: { password: "<REDACTED>" }
masquerade:                    # 被主动探测时伪装成正常 HTTPS 站
  type: proxy
  proxy: { url: "https://news.ycombinator.com/", rewriteHost: true }
acme:
  domains: [ "hy2.example.com" ]
  email: "<REDACTED>"
```

**为什么死磕 IPv6？** 前期实测发现一个反直觉的现象：**GFW 对 IPv6 下的 hysteria2 封锁明显比 IPv4 松**。QUIC（UDP）本来就难做 DPI，叠加 IPv6 地址空间巨大、运营商封锁规则没跟上，IPv6 这条路稳得多。代价是**没有公网 IPv6 的客户端连不上 hysteria，只能退到路径 B**——所以才需要第二条路兜底。

### 路径 B：vless + ws 走 Cloudflare

第二条路是 sing-box 的 **VLESS + WebSocket**：本机 `0.0.0.0:8080` 跑**明文 ws（不带 TLS）**，TLS 全交给 Cloudflare 边缘终结，再经 cloudflared tunnel 暴露成一个橙云域名走 CDN。GFW 看到的就是普通的 Cloudflare HTTPS+WebSocket 流量，**封不掉、也不暴露节点真实 IP**，纯 IPv4 客户端也能用。

最后把 5 台机器的 **10 个节点（vless / hy2 各 5 个）** 全塞进家庭网关 home-proxy 的 sing-box，开 `urltest` 自动测速选最优节点，整套梯子就活了。

### 部署踩坑（这几条最费时间）

- **二进制必须在目标机直接下载，别从跳板机中转**。试过 `cat | ssh 'sudo cat >'`（sudo+stdin 极易 Broken pipe）、`scp` 走 SOCKS5（龟速 + 并发写同一文件损坏 → 运行时 Segfault），全翻车。OCI 新加坡出口带宽大，直接 `curl` GitHub release 几秒搞定。
- **认准 CPU 架构**：现在账号里 ARM 和 AMD 混着，下二进制别拿错——ARM 机用 `...-linux-arm64`，AMD 机用 `...-linux-amd64`，拿反了直接 `Exec format error`。

  ```bash
  # AMD(E2.1.Micro) 上：
  curl -sSL -o /tmp/hysteria https://github.com/apernet/hysteria/releases/download/app%2Fv2.9.2/hysteria-linux-amd64
  # ARM(A1) 上把结尾换成 hysteria-linux-arm64
  ```
- **cloudflared 用 apt 装，别手动放二进制**：apt 装完一句 `cloudflared service install <token>` 直接注册 systemd service，干净；手动复制还得自己写 unit、还容易踩软链接的坑。
- **hysteria 的 systemd 两个坑**：服务名是 `hysteria-server.service`（不是 `hysteria2`），二进制叫 `hysteria`（v2 不带「2」）；用 `useradd -r` 建的 system user 没有 home，`WorkingDirectory=~` 会展开失败报 `CHDIR`，要写成 `WorkingDirectory=/etc/hysteria`。

## 协议选型：几条用血换的经验

- **Cloudflare Tunnel 是 TCP 隧道**，UDP 协议（Hysteria2 / Tuic / WireGuard）穿不进去。复用 Tunnel 只能上 TCP 协议，首选 **vless + ws + tls**，vmess/trojan 备选。
- **要重度 / 看视频，直接用 hysteria2 IP 直连**：QUIC 伪装 HTTPS，100+Mbps，月流量 10TB 随便造，且不踩 Cloudflare 的 TOS。
- **Tailscale Exit Node 别拿来翻墙**：WireGuard 的 UDP 握手特征近年已被识别，大流量穿墙容易被限速/黑洞。Tailscale 适合管机器（小流量 ssh、内网互连），翻墙交给伪装协议。
- **Cloudflare 免费版 TOS 禁止大流量非 HTML 内容**（俗称 no-streaming 条款）。个人小流量浏览/编程/GitHub 几乎无虞，但别拿来挂 BT、长时间 4K、或共享给一堆人——会触发风控甚至封站。

## 保号：Always Free 不是永远不动

最后几个容易被忽略的坑：

- **200G 块存储是所有机器共享的**。我 5 台机器每台默认 47G 启动盘，合计 235G，超出免费的 200G 上限 35G——这就是那笔 SGD 0.01 小额扣费的来源。要么抢号时把启动盘缩到默认下限，要么接受这点零头。
- **Always Free 的 A1 实例，7 天 CPU 平均利用率 < 20% 会被自动回收**（不是删，是 stop 保留磁盘，但要重新抢一次，等于白折腾）。最优雅的是部署真业务（这套梯子本身就是），保底偷懒法：

  ```bash
  sudo apt install -y stress-ng
  nohup stress-ng --cpu 1 --cpu-load 30 --timeout 0 >/dev/null 2>&1 &
  ```
- **升级 PAYG（绑卡按量付费）能进一步防回收**——`Always Free`（资源额度）和 `PAYG`（账号付费模式）不互斥，可以是「PAYG 账号 + 跑着 Always Free 资源」，既永久免费又不吃 idle 回收。但要说清：官方文档只写了「idle 的 **Always Free** 实例可能被回收」，**从没书面承诺「升 PAYG 后就豁免」**——这是社区验证有效的经验，不是白纸黑字的保证。稳妥做法仍是让账号 60 天内保持活跃，并把过期信用卡换张能用的 Visa。

## 可复用要点

- **抢号先体检**：用 `oci CLI` 确认账号是 `Always Free`、配额未占用，能查到 limit 本身就说明没被降级。
- **AMD Micro 和 ARM A1 是两套独立免费额度**：A1 满了不影响开 2 台 E2.1.Micro；先 `oci compute shape list` 确认 region 支持该 shape 再抢。
- **轮询脚本三件套**：成功落地写 `state` 标记并发通知、`Out of capacity` 静默继续、`429` 额外退避；用 systemd `--user` + `Linger` 后台跑，断 SSH 不停。
- **错误分类的正则要照真实返回文案写**：`Too many requests`（带空格）≠ `TooManyRequests`，否则统计全失真；带 `for the user` 是**账号级**限流，靠降频解决（60s→120s），换 IP 无效。
- **国际链路慢多半是 TCP QoS 整形**，不是带宽不够——ICMP 稳但大流被掐就是它；解法是走境外代理 / Cloudflare Tunnel 绕开拥塞段。
- **Cloudflare Tunnel = 主动出站 + 自动 HTTPS + 隐藏真实 IP**，装在哪台暴露哪台，不需要中转服务器；只能跑 TCP 协议。
- **梯子用双路接入兜底**：hysteria2 走 IPv6（GFW 封得松）当主力 + vless/ws 走 CF 兜纯 IPv4 客户端；全节点丢进 sing-box `urltest` 自动选优。
- **跨架构部署认准 arm64/amd64 二进制**；大文件在目标机直接 `curl`，别中转；cloudflared 用 apt；hysteria 服务名是 `hysteria-server`。
- **保号靠 ≥20% CPU 利用率 + 升 PAYG + 账号活跃**；5 台机注意 200G 块存储共享上限。

薅羊毛真正的成本不是那 21 小时的等待，而是搞清楚「为什么慢」「为什么被限流」「为什么 AMD 还能再抢」「为什么 IPv6 这条路更稳」——把每个反直觉的现象追到根因，机器才真正变成你的。
