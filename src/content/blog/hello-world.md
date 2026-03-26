---
title: '你好，世界'
date: 2026-03-26
description: '这是我的第一篇博客文章，记录博客搭建的过程和技术选型。'
tags: ['博客', 'Astro', 'Cloudflare']
---

## 博客上线了

经过一番折腾，我的技术博客终于上线了。这篇文章简单记录一下搭建过程。

## 技术选型

- **框架**: [Astro](https://astro.build) — 专为内容站设计，构建速度快
- **样式**: Tailwind CSS — 暗色科技风主题
- **评论**: Giscus — 基于 GitHub Discussions
- **搜索**: Pagefind — 构建时生成索引，客户端搜索
- **部署**: Cloudflare Pages — 全球 CDN，自动 HTTPS
- **统计**: Cloudflare Web Analytics — 隐私友好

## 为什么选 Astro

Astro 的 Island Architecture 非常适合博客场景：

```javascript
// 默认生成纯静态 HTML，零 JS
// 需要交互时才加载组件
<InteractiveComponent client:load />
```

大部分博客页面不需要 JavaScript，Astro 默认输出纯 HTML + CSS，页面加载极快。

## 下一步

- 持续写作，分享技术心得
- 完善博客功能
- 优化阅读体验

感谢你的访问！
