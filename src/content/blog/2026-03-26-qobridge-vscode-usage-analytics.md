---
title: 'VS Code 使用统计系统：WebSocket + ClickHouse 全链路'
date: 2026-03-26
description: '从零搭建 Qoder AI 编辑器使用统计系统，包含 VS Code 扩展数据采集、WebSocket 实时收集、ClickHouse 时序存储和 MCP 查询接口。'
tags: ['VS Code', 'WebSocket', 'ClickHouse', '数据分析']
---

## 需求

Qoder 是一款基于 VS Code 的 AI 代码编辑器，需要统计使用情况：谁在用、用了多久、AI 功能使用频率。现有方案没有，从零搭。

## 架构

三个服务 + 一个 VS Code 扩展，monorepo 管理：

```
VS Code 扩展（数据采集）
    ↓ WebSocket
收集器服务（实时接收 + 批量写入）
    ↓
ClickHouse（时序存储） + PostgreSQL（元数据）
    ↓
MCP 服务器（查询接口，给 AI 编辑器用）
```

## VS Code 扩展：增量数据同步

扩展从 Qoder 本地 SQLite 数据库读取会话数据，增量同步到服务端：

```typescript
// 记录上次同步位置，只发增量数据
const lastSyncId = context.globalState.get('lastSyncId', 0);
const newSessions = await queryLocalDb(
  'SELECT * FROM sessions WHERE id > ? ORDER BY id',
  [lastSyncId]
);

if (newSessions.length > 0) {
  ws.send(JSON.stringify({ type: 'sync', data: newSessions }));
  await context.globalState.update('lastSyncId', newSessions[newSessions.length - 1].id);
}
```

关键点：增量同步避免重复传输，断线重连后从上次位置继续。

## WebSocket 收集器：批量写入优化

直接逐条写 ClickHouse 性能很差，用 batch-writer 攒一批再写：

```typescript
class BatchWriter {
  private buffer: Record[] = [];
  private timer: NodeJS.Timeout | null = null;

  add(record: Record) {
    this.buffer.push(record);
    // 攒够 1000 条或 5 秒超时，批量写入
    if (this.buffer.length >= 1000) {
      this.flush();
    } else if (!this.timer) {
      this.timer = setTimeout(() => this.flush(), 5000);
    }
  }

  async flush() {
    const batch = this.buffer.splice(0);
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    if (batch.length > 0) {
      await clickhouse.insert(batch);
    }
  }
}
```

两个触发条件取其先：数量满 1000 条或时间满 5 秒。保证大流量时高吞吐，低流量时不丢数据。

## 消息去重与校验

WebSocket 不保证 exactly-once，需要在收集器端去重：

```typescript
// 用 sessionId + timestamp 作为去重键
const dedupeKey = `${msg.sessionId}:${msg.timestamp}`;
if (seen.has(dedupeKey)) return; // 跳过重复
seen.add(dedupeKey);
```

同时用 Zod 做消息格式校验，畸形数据直接丢弃不入库。

## MCP 查询接口

给 AI 编辑器提供查询能力，通过 API Key 鉴权：

```typescript
// API Key 用 SHA-256 哈希存储，不存明文
const hashedKey = crypto.createHash('sha256')
  .update(apiKey)
  .digest('hex');
const record = await db.query(
  'SELECT * FROM api_keys WHERE key_hash = $1',
  [hashedKey]
);
```

通过 MCP 协议暴露 ClickHouse 和 PostgreSQL 的查询接口，AI 可以直接分析使用数据。

## 部署

Docker Compose 一键拉起全部服务：

```yaml
services:
  collector:
    build: ./packages/collector
    ports: ["8080:8080"]
  clickhouse:
    image: clickhouse/clickhouse-server
    volumes: ["./data/clickhouse:/var/lib/clickhouse"]
  postgres:
    image: postgres:16
    volumes: ["./data/postgres:/var/lib/postgresql/data"]
  mcp-server:
    build: ./packages/mcp-server
    ports: ["3001:3001"]
```

## 总结

这个项目最有价值的经验：

1. **WebSocket + 批量写入**是时序数据采集的经典模式，简单有效
2. **增量同步**比全量同步节省 90%+ 的带宽
3. **API Key 哈希存储**是基本安全素养，不要存明文
4. **Monorepo（npm workspace）**管理多个关联服务很方便，共享类型定义和工具函数
