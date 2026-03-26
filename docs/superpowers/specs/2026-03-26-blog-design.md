# handsomehan.com 技术博客设计文档

## 概述

为 handsomehan 搭建一个暗色科技风格的个人技术博客，部署在 Cloudflare Pages，域名 handsomehan.com。

## 技术栈

| 组件 | 选型 | 理由 |
|------|------|------|
| 框架 | Astro | 内容站首选，静态为主按需动态 |
| 样式 | Tailwind CSS | 暗色主题定制方便 |
| 评论 | Giscus | 基于 GitHub Discussions，免费 |
| 搜索 | Pagefind | 构建时生成索引，客户端搜索，零成本 |
| 统计 | Cloudflare Web Analytics | 零配置，隐私友好，免费 |
| 部署 | Cloudflare Pages | Git 推送自动部署 |
| 内容 | Markdown (.md) | 写作友好 |

## 页面结构

```
/                  首页（最新文章列表）
/blog/             文章归档列表（分页）
/blog/[slug]       文章详情页
/tags/             标签云
/tags/[tag]        按标签筛选文章
/about             关于页面
```

## 功能设计

### 文章系统
- Astro Content Collections 管理 Markdown 文章
- frontmatter 包含：title, date, tags, description, draft
- 支持代码高亮（Shiki，暗色主题）
- 支持中文排版优化

### 评论系统（Giscus）
- 基于 GitHub Discussions
- 在文章详情页底部加载
- 暗色主题匹配博客风格
- 需要：创建 GitHub 仓库 + 启用 Discussions + 安装 Giscus App

### 搜索功能（Pagefind）
- 构建时自动索引所有文章
- 客户端搜索，无服务端依赖
- 支持中文分词

### 访问统计（Cloudflare Web Analytics）
- 在 Cloudflare 控制台启用
- 插入一行 JS 即可
- 隐私友好，无 cookie

## 视觉风格

- 暗色主题为主（深灰/黑底 + 亮色点缀）
- 科技感：代码高亮突出，等宽字体
- 响应式设计，移动端适配
- 简洁导航栏：Logo / Blog / Tags / About / Search

## 项目结构

```
handsomehan.com/
├── src/
│   ├── content/
│   │   └── blog/          # Markdown 文章
│   ├── components/         # 组件
│   │   ├── Header.astro
│   │   ├── Footer.astro
│   │   ├── PostCard.astro
│   │   ├── Giscus.astro
│   │   └── Search.astro
│   ├── layouts/
│   │   ├── Base.astro      # 基础布局
│   │   └── Post.astro      # 文章布局
│   └── pages/
│       ├── index.astro
│       ├── about.astro
│       ├── blog/
│       │   ├── index.astro
│       │   └── [slug].astro
│       └── tags/
│           ├── index.astro
│           └── [tag].astro
├── public/                  # 静态资源
├── astro.config.mjs
├── tailwind.config.mjs
└── package.json
```

## 部署流程

1. GitHub 创建仓库 handsomehan.com
2. Cloudflare Pages 关联 GitHub 仓库
3. 构建命令：`npm run build`
4. 输出目录：`dist`
5. 绑定自定义域名 handsomehan.com
6. 启用 Cloudflare Web Analytics

## 运行成本

- 域名：$7.50/年（首年），$10.13/年（续费）
- 托管/CDN/统计：$0（Cloudflare Pages 免费）
- 评论：$0（Giscus 免费）
- 搜索：$0（Pagefind 客户端）
- **总计：~$7.50/年**
