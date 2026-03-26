---
title: '从零搭建赛博朋克风格技术博客：Astro + Cloudflare Pages'
date: 2026-03-26
description: '记录用 Astro 框架搭建个人技术博客并部署到 Cloudflare Pages 的完整过程，包括域名选择、赛博朋克主题设计、评论和搜索功能集成。'
tags: ['Astro', 'Cloudflare', '博客', '建站']
---

## 起因

想搞个自己的技术博客，要求很简单：便宜、能写动态内容、从大陆访问快。

对比了一圈平台延迟后，选择了 **Cloudflare Pages**——免费托管、自带 CDN、自动 HTTPS。框架选了 **Astro**，天生为内容站设计，构建出来的页面几乎零 JS。

## 技术选型

| 组件 | 选型 | 费用 |
|------|------|------|
| 框架 | Astro | 免费 |
| 样式 | Tailwind CSS | 免费 |
| 评论 | Giscus（GitHub Discussions） | 免费 |
| 搜索 | Pagefind（客户端搜索） | 免费 |
| 统计 | Cloudflare Web Analytics | 免费 |
| 部署 | Cloudflare Pages | 免费 |
| 域名 | handsomehan.com | ~$10/年 |

**总计：$10/年**，只花了一个域名的钱。

## 大陆延迟实测

部署前实测了各平台从大陆直连的延迟：

```
腾讯云        8ms    ✅ 需要备案
阿里云       14ms    ✅ 需要备案
腾讯 EdgeOne  67ms    无需备案
Cloudflare  195ms    无需备案
Vercel      194ms    40% 丢包
Fly.io      207ms    无需备案
Deno Deploy 305ms    无需备案
```

不想备案的情况下，Cloudflare 是最佳选择——延迟可接受，稳定性好，生态完整。

## 踩过的坑

### 1. Cloudflare adapter 与静态输出冲突

一开始 `astro add cloudflare` 同时设了 `output: 'static'`，部署后 404。

原因：Cloudflare adapter 会生成 server-side 的 wrangler 配置，但纯静态站不需要它。

**解决**：删掉 `@astrojs/cloudflare` adapter 和 `wrangler.jsonc`，用纯静态模式。

```javascript
// astro.config.mjs - 纯静态就这么简单
export default defineConfig({
  site: 'https://handsomehan.com',
  output: 'static',
});
```

### 2. Pagefind 动态 import 被 Vite 拦截

Pagefind 的 JS 文件是构建后才生成的，直接 `import('/pagefind/pagefind-ui.js')` 会被 Vite 当作模块依赖报错。

**解决**：用 `<script is:inline>` 避免 Astro 处理，手动创建 `<script>` 标签动态加载：

```javascript
var script = document.createElement('script');
script.src = '/pagefind/pagefind-ui.js';
script.onload = function() {
  new PagefindUI({ element: '#pagefind-search' });
};
document.head.appendChild(script);
```

### 3. wrangler.jsonc 的 name 不能有点号

`"name": "handsomehan.com"` 直接报错，wrangler 要求 name 只能用字母数字和短横线。改成 `"handsomehan"` 就好了。

## 赛博朋克主题

用 Tailwind CSS 自定义了一套霓虹配色：

```css
--color-accent: #00f0ff;      /* 青色霓虹 */
--color-accent-pink: #ff2d95;  /* 粉色霓虹 */
--color-accent-purple: #bf5af2; /* 紫色霓虹 */
```

加上扫描线、网格背景、发光边框、渐变动画文字，赛博味就出来了。

## 总结

如果你也想搭个便宜的个人博客：

1. **Astro + Cloudflare Pages** 是目前性价比最高的方案
2. 不备案的话 Cloudflare 延迟在 200ms 左右，完全可用
3. Pagefind + Giscus 能零成本解决搜索和评论
4. 整套方案一年只要一个域名的钱
