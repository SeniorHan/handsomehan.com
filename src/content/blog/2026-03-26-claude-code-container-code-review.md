---
title: '用 Claude Code + Docker 构建自动化代码审查系统'
date: 2026-03-26
description: '基于 Next.js 调度 Docker 容器运行 Claude Code CLI，实现 GitLab Push 触发的全自动代码审查，审查结果通过钉钉推送给开发者。'
tags: ['Claude Code', 'Docker', 'AI', 'DevOps']
---

## 背景

团队代码审查长期依赖人工，质量参差不齐，大量 MR 堆积没人看。想做一个自动化的 AI 代码审查系统，要求：

1. GitLab Push 自动触发，无需手动操作
2. 审查质量接近人工 Code Review
3. 结果推送到钉钉，融入现有工作流

## 架构设计

```
GitLab Push Webhook
    ↓
Next.js BFF（任务调度）
    ↓
Docker 容器（Claude Code CLI）
    ↓
审查报告 → 钉钉待办 + 管理后台
```

核心思路：用 Next.js 做任务调度和管理后台，每个审查任务启动一个独立的 Docker 容器运行 Claude Code CLI。

### 为什么用容器隔离

- **安全**：每个审查任务在独立沙箱中执行，互不影响
- **并发**：最多同时跑 5 个审查容器，一个仓库同一时间只有一个任务
- **清理**：任务结束容器自动销毁，不留垃圾

## 关键实现

### 1. 调度循环

调度器每 30 秒轮询数据库，找到排队中的任务后启动容器：

```typescript
// scheduler-loop.ts 核心逻辑
async function pollOnce() {
  const task = await pickNextTask(); // 同仓库不并发
  if (!task) return;

  const container = await launchContainer(task);
  await updateTask(task.id, {
    status: 'RUNNING',
    containerId: container.id
  });
}
```

超时保护机制：30 分钟无心跳自动重试，2 小时绝对超时直接标记失败。最多重试 3 次。

### 2. 容器编排

通过 Dockerode 动态创建容器，注入任务信息和凭证：

```typescript
// container-manager.ts
const config = {
  Image: 'cr-agent:latest',
  Env: [
    `TASK_ID=${task.id}`,
    `REPO_URL=${repo.cloneUrl}`,
    `BRANCH=${task.branch}`,
    `BEFORE_COMMIT=${task.beforeCommit}`,
    `AFTER_COMMIT=${task.afterCommit}`,
    `ANTHROPIC_BASE_URL=${process.env.ANTHROPIC_BASE_URL}`,
    `ANTHROPIC_AUTH_TOKEN=${process.env.ANTHROPIC_AUTH_TOKEN}`,
    `ANTHROPIC_MODEL=${process.env.ANTHROPIC_MODEL}`,
  ],
  HostConfig: {
    Binds: [
      `${repoDir}:/repo:ro`,
      `${workspaceDir}:/workspace:ro`,
    ],
  },
};
```

### 3. Agent 工作流

容器内的 `entrypoint.sh` 启动 Claude Code CLI，通过 `AGENTS.md` 定义审查规范：

```bash
#!/bin/bash
# 生成审查指令
INITIAL_PROMPT=$(agent-guide 2>&1)

# 以非 root 用户运行 Claude Code
exec gosu claude claude \
  --dangerously-skip-permissions \
  -p "$INITIAL_PROMPT"
```

`agent-guide` 脚本会生成包含 git diff、分支信息、提交历史的完整审查上下文，Claude Code 据此执行代码审查。

### 4. 结果回调

Claude Code 审查完成后，通过 MCP 工具或直接 HTTP 回调通知 BFF：

```
容器完成审查
  → PATCH /api/tasks/{id} (status: COMPLETED)
    → BFF 创建钉钉待办卡片
      → 开发者收到通知，点击查看详情
```

## 从 OpenCode 迁移到 Claude Code

最初用的是 OpenCode（Go 实现的 AI CLI 工具），后来迁移到 Claude Code。主要变化：

- **配置方式**：从生成配置文件改为环境变量注入（`ANTHROPIC_*`）
- **安全模型**：添加了非 root 用户 `claude`，用 `gosu` 降权执行
- **入口简化**：不再需要生成复杂的配置文件，`entrypoint.sh` 精简了一半

## 数据模型

```
ReviewTask: 任务队列（状态机：QUEUED → RUNNING → COMPLETED/FAILED）
GitRepo:    仓库配置（分支匹配策略用 glob 模式）
LocalIssue: 审查发现的问题（关联 MR 和代码行号）
```

分支策略用 minimatch glob 匹配，配置灵活：

```json
{ "patterns": ["main", "release/*", "hotfix/**"] }
```

## 效果

- 每次 Push 自动审查，开发者无感知
- 平均 5 分钟出结果（取决于代码变更量）
- 审查结果直接推送到钉钉待办，融入日常工作流
- 支持 5 路并发，高峰期不堆积

## 总结

这套系统的核心设计：**用容器隔离 AI Agent 执行环境，用调度器管理任务生命周期**。Claude Code CLI 本身能力很强，关键在于怎么把它编排成可靠的自动化流水线。
