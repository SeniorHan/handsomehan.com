---
name: blog-pipeline
description: 小帅的个人博客 handsomehan.com 全流程助手——从历史 AI 会话里挖选题、把会话改写成脱敏的中文技术博客、再发布到 Astro 站点(commit+push 触发 Cloudflare Pages 部署)。Use this skill 只要小帅提到:写博客/写篇文章/找选题/找文章素材、把某段会话/某次折腾写成 blog、翻历史会话挖素材、发布到 handsomehan、给文章脱敏、博客发上线 等——即使没明说"用 blog-pipeline"也要触发。涉及 ~/.claude 或 ~/.omp 会话转写、src/content/blog/ 文章、frontmatter、Cloudflare Pages 发布时同样适用。
---

# blog-pipeline —— handsomehan.com 选题 → 写作 → 发布

把小帅的「翻历史会话找素材 → 改写成中文技术博客 → 发布上线」这条流水线固化下来。
三个阶段，每个都能独立进入(他可能直接丢一段会话让你写，或直接让你发布一篇已审稿)。

工作目录是博客仓库 `~/workspace/handsomehan.com`(Astro 站，内容集合在 `src/content.config.ts`)。
本 skill 自带两个脚本(`scripts/`)，把重复的脏活做掉，别每次重写。

---

## 阶段一：找素材

历史会话是最大的选题库。两套工具的主会话转写按「运行时的工作目录」分桶存放：

- Claude Code：`~/.claude/projects/<编码cwd>/<uuid>.jsonl`
- omp：`~/.omp/agent/sessions/<编码cwd>/<时间戳>_<uuid>.jsonl`

> 子代理转写(`.../subagents/*.jsonl`、omp 的阶段切片子目录)不是人机对话，blog 素材在主对话里——`scan_sessions.py` 已自动排除它们。

用 `scripts/scan_sessions.py` 检索，**别手写一次性脚本**：

```bash
S=.claude/skills/blog-pipeline/scripts/scan_sessions.py

# 按体量列最大的主会话(大会话往往是一次完整折腾)
python3 "$S" list --top 15 --detail

# 按主题检索：在「用户原话」里数关键词命中(比全文准，避开部署日志噪音)
python3 "$S" theme --keywords "uart,gpio,刷机,固件,逆向,adb" --top 10   # 硬件折腾
python3 "$S" theme --keywords "tailscale,headscale,翻墙,fakeip,exit node" --top 10
```

挑出候选后，给每个会话生成精简 digest，**派子代理读 digest 出一句话概要 + blog 价值评分**(高/中/低)——digest 小、读起来快，别让子代理直接啃几十 MB 的原始 jsonl：

```bash
python3 "$S" digest --path <session.jsonl> --label hotel-iptv --out /tmp/blogscan
# → /tmp/blogscan/digest_hotel-iptv.md
```

最有 blog 相的题材，按经验排序：
1. **有故事性 / 生活向**(出差折腾、硬件改造、远程盲操)——传播相最强，门槛低
2. **通用可复用**(薅羊毛、自建服务、网络架构)——干货帖
3. **诡异 bug 啃源码找根因**——硬核 debug 故事
4. **AI 多代理协作踩坑**——方法论

体量榜会漏掉「小而精」的好题材(一两 MB 的聚焦会话)，所以**主题检索比纯按大小更值得跑一轮**。

---

## 阶段二：写文章

### 先抽「带剧情」的转写

digest 只有用户 prompt，不够写作。用 `story` 抽出完整剧情(用户原话 + 助手叙述 + 关键命令/结果，封顶约 95KB，够写一篇且不撑爆上下文)：

```bash
python3 "$S" story --path <session.jsonl> --label hotel-iptv --out /tmp/blogscan
# 一篇文章融合多段会话(主+续)就传多个 --path：
python3 "$S" story --path a.jsonl b.jsonl --label oracle --out /tmp/blogscan
```

### 写作规范

第一人称「我」(小帅视角)，中文 Markdown、代码块保留英文。结构：

```
# 标题
> 一句话导语(钩子，点出反差/看点)
## 背景 / 起因
## 踩坑与转折   ← 保留真实的「啊哈时刻」和踩坑细节，这是看点
## 解决过程     ← 适当嵌真实命令/代码片段，让读者能照做
## 结果
## 可复用要点    ← bullet，抽象成别人也能用的经验
(结尾一句 takeaway)
```

- 篇幅一般 800–1600 字；硬核架构文可更长。叙事流畅，不要流水账。
- **绝不编造**转写里没有的技术细节。story 被截断就用已有部分写，不脑补后续。
- 不写工时 / 工作量评估(AI 写代码，工时对人无意义——见 `~/.claude/CLAUDE.md`)。
- 多篇可并行：派写作子代理，每个读一篇 story、产出一篇草稿，注意嘱咐它们脱敏。

### 脱敏(发布前的硬性红线)

博客是公开的，小帅的真实基建绝不能外泄。逐项检查：

| 类别 | 处理 |
|---|---|
| token / 密码 / 授权码 / API key / 手机号 / cloudflared credentials / tunnel token / OCID | 删除或换 `<REDACTED>` |
| 内网/自建域名 `*.tidun.cn` `*.xiujiadian.com` `*.handsomehan.com` | 占位：`example.com` / `ts.example.com` / `git.corp.example.com` |
| 真实公网 IP、IPv6、内网网段(如 `192.168.90.x`、`10.254.x`) | 占位：`<node-ip>` / `<server-ip>` / `内网网关` |
| 公司/部门代号(啄木鸟、梯盾、xiujiadian) | 泛化成「公司内网」「某 .cn SaaS」 |

**可以保留**的通用非敏感地址：Tailscale CGNAT `100.64.0.0/10`、fake-ip 保留段 `198.18.0.0/15`、公共 DNS(`8.8.8.8`/`119.29.29.29`)、`127.0.0.1`/localhost、公开站点(如伪装用的 `news.ycombinator.com`)。

脱敏后用脚本扫一遍兜底：

```bash
grep -nE 'tidun|xiujiadian|handsomehan|啄木鸟|梯盾|ocid1|[0-9]{1,3}(\.[0-9]{1,3}){3}' /tmp/blogscan/blog_<x>.md
# 命中的逐个判断是不是该占位(公共 DNS / CGNAT 等可放过)
```

### 审阅(默认先审后发)

小帅的习惯是**先发邮箱审阅再发布**。用 mailbox skill 把草稿发给他：

```bash
direnv exec ~/.claude/skills/mailbox ~/.claude/skills/mailbox/mailbox send \
  --to hankangshuai@zmn.cn --subject "Blog 初稿待审阅：<标题>" \
  --body "<一句话索引：标题 + 看点 + 字数>" --attach /tmp/blogscan/blog_<x>.md
```

他给修改意见后改稿、重发，直到他说「就这样发布」再进阶段三。

---

## 阶段三：发布

站点是 Astro 内容集合，文章是 `src/content/blog/<YYYY-MM-DD>-<slug>.md`。
frontmatter schema(`src/content.config.ts`)：`title`、`date`、`description` 必填，`tags` 数组，`draft` 可选。
**布局会把 title 渲染成 `<h1>`，正文不要再写 `# 标题`**(否则双标题)——`publish_post.py` 会替你删掉首行 H1。

用 `scripts/publish_post.py` 一把梭(套 frontmatter → 构建 → 提交 → 推送)：

```bash
P=.claude/skills/blog-pipeline/scripts/publish_post.py

python3 "$P" \
  --draft /tmp/blogscan/blog_oracle.md \
  --title "白嫖甲骨文 ARM + AMD 五台永久免费机：从轮询抢号到 Cloudflare 搭梯子" \
  --date 2026-06-02 --slug oracle-cloud-free-tier-arm-amd-proxy \
  --tags "Oracle Cloud,白嫖,Cloudflare,翻墙,网络" \
  --description "<给 SEO/分享用的一句话摘要>" \
  --build --commit --push
```

脚本的关键约定(都是踩过坑固化下来的)：

- **`--build` 用仓库本地 astro，绝不用 `npx`**：`npx astro` 会拉一个临时 astro，找不到本地配置直接报错。`node_modules` 不在就先 `npm install`。
- **`--commit` 只提交新文章**：`npm install` 会顺手改 `package-lock.json`(删几个 `libc` 字段之类的无关 churn)，脚本会先 `git checkout` 还原它，避免污染提交。git 身份没配就从上一条 commit 借(小帅是 `hankangshuai` / `hankangshuai@zmn.cn`)。
- **`--push` 后 Cloudflare Pages 自动重新构建**，约 1–2 分钟上线。

代码块语言要用 Shiki 认识的，否则构建会有 `language doesn't exist` 警告：`sshconfig` 改 `ini`，`dotenv` 改 `ini`，拿不准就用 `bash`/`text`。

发布后核验线上(等 ~90 秒让 CF Pages 构建完)：

```bash
sleep 90
curl -s -o /dev/null -w "status=%{http_code}\n" \
  "https://handsomehan.com/blog/<date>-<slug>/"      # 期望 200
```

想分步来(不让脚本一把梭)：去掉 `--build/--commit/--push` 只生成文件，自己 `node_modules/.bin/astro build` 验证，再手动 commit/push。

---

## 速查

| 想干嘛 | 命令 |
|---|---|
| 列最大的会话 | `python3 scan_sessions.py list --top 15 --detail` |
| 按主题找会话 | `python3 scan_sessions.py theme --keywords "..." --top 10` |
| 出 digest 给子代理概要 | `python3 scan_sessions.py digest --path X.jsonl --label NAME` |
| 出 story 给写作 | `python3 scan_sessions.py story --path X.jsonl --label NAME` |
| 脱敏自查 | `grep -nE 'tidun\|xiujiadian\|handsomehan\|ocid1\|[0-9.]{7,}' blog.md` |
| 发邮箱审阅 | `direnv exec ~/.claude/skills/mailbox/... send --to hankangshuai@zmn.cn ...` |
| 套frontmatter+构建+提交+推送 | `python3 publish_post.py --draft ... --title ... --date ... --slug ... --tags ... --build --commit --push` |
| 验线上 | `curl -s -o /dev/null -w "%{http_code}" https://handsomehan.com/blog/<date>-<slug>/` |

## 反例(别这样做)

- ❌ 让子代理直接读几十 MB 原始 jsonl 出概要 —— 慢且贵；先 `digest`/`story` 抽精简件。
- ❌ 发布前不脱敏，或漏了 tunnel token / 真实 IP / 内网域名 —— 公开仓库，等于泄密。
- ❌ 编造转写里没有的技术细节凑字数 —— 宁可写短，不可造假。
- ❌ 正文保留 `# 标题` —— 和布局的 h1 重复；交给脚本删。
- ❌ 用 `npx astro build` —— 拉临时 astro 找不到本地配置；用 `node_modules/.bin/astro`。
- ❌ 提交时把 `package-lock.json` 的 churn 一起带上 —— 还原它，只提交文章。
- ❌ 没审阅就直接 push —— 小帅默认先邮箱审稿；除非他明说「直接发」。
- ❌ 文章写工时/工作量评估 —— 不写。
