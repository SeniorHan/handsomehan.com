---
title: '逆向分析 Electron 应用的本地数据加密：以 Qoder IDE 为例'
date: 2026-03-26
description: '记录对 Qoder AI 编辑器本地聊天记录加密机制的逆向分析过程，涵盖 Electron 应用结构分析、AES 加密定位、密钥提取方法论。'
tags: ['逆向工程', '安全研究', 'Electron', '加密']
---

## 背景

Qoder 是一款 AI 代码编辑器，本地聊天记录存在 SQLite 数据库里，但 `question` 和 `answer` 字段是加密的。出于研究目的，我想看看自己的聊天记录到底存了些什么。

## 第一步：定位数据存储

macOS 上 Electron 应用的用户数据一般在 `~/Library/Application Support/` 下：

```
~/Library/Application Support/Qoder/SharedClientCache/
├── cache/
│   ├── db/
│   │   └── local.db          # SQLite 主数据库
│   └── machine_token.json    # 机器令牌
└── index/
    └── git/v1/               # Git 相关数据
```

直接打开 `local.db` 查看 `chat_record` 表：

```sql
SELECT question FROM chat_record LIMIT 1;
-- B73O6i2RiknnLankq5NytwRVXZWNOKM0m85urWg8+Cs...
```

Base64 编码，解码后长度是 16 字节的倍数——典型的**块加密**特征。

## 第二步：分析应用结构

```bash
file /Applications/Qoder.app/Contents/MacOS/Qoder
# Mach-O 64-bit executable arm64
```

确认是 Electron 应用后，核心逻辑在 JS 文件中：

```
Contents/Resources/app/out/vs/
├── code/electron-utility/sharedProcess/sharedProcessMain.js
└── workbench/workbench.desktop.main.js
```

Electron 应用的好处（对逆向来说）：JS 代码虽然经过打包压缩，但没有编译成二进制，直接可读。

## 第三步：定位加密代码

在 `sharedProcessMain.js` 中搜索 `encrypt`、`decrypt`、`AES` 等关键词，找到了加解密函数：

```javascript
// 加密
aesEncrypt(plaintext, key) {
    const data = Buffer.from(plaintext, "utf8");
    const keyBuf = Buffer.from(key, "utf8");
    const iv = keyBuf.slice(0, 16);  // IV = 密钥前 16 字节
    const cipher = crypto.createCipheriv("aes-128-cbc", keyBuf, iv);
    return Buffer.concat([cipher.update(data), cipher.final()])
                 .toString("base64");
}

// 解密
aesDecrypt(ciphertext, key) {
    const data = Buffer.from(ciphertext, "base64");
    const keyBuf = Buffer.from(key, "utf8");
    const iv = keyBuf.slice(0, 16);
    const decipher = crypto.createDecipheriv("aes-128-cbc", keyBuf, iv);
    return Buffer.concat([decipher.update(data), decipher.final()])
                 .toString("utf8");
}
```

**关键信息**：
- 算法：AES-128-CBC
- IV：复用密钥前 16 字节（这是一个安全缺陷）
- 编码：Base64

## 第四步：寻找密钥

算法有了，密钥在哪？两个思路：

### 思路 A：从 JS 代码中追踪

在 JS 中追踪 `aesEncrypt` 的调用链，找到密钥参数的来源。Electron 应用的 JS 虽然压缩过，但变量名和字符串还在。

### 思路 B：从原生二进制中提取

Qoder 还有一个原生二进制模块，用 `strings` 提取：

```bash
strings /path/to/native/binary | grep -E '.{16}' | head -50
```

寻找长度恰好 16 字符的可疑字符串——因为 AES-128 的密钥就是 16 字节。

### 验证候选密钥

找到候选后用 Python 逐个验证：

```python
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64

def try_decrypt(encrypted_b64, key_str):
    try:
        ciphertext = base64.b64decode(encrypted_b64)
        key = key_str.encode('utf-8')
        iv = key[:16]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return decrypted.decode('utf-8')
    except Exception:
        return None

# 对每个候选密钥测试
for candidate in candidates:
    result = try_decrypt(sample_encrypted_data, candidate)
    if result:
        print(f"找到密钥！解密结果: {result[:50]}...")
```

当解密结果是可读的中文/代码文本时，密钥就找对了。

## 安全分析

这次逆向暴露了几个常见问题：

| 问题 | 影响 | 建议 |
|------|------|------|
| 密钥硬编码在代码中 | 任何人都能提取 | 基于机器特征动态派生密钥 |
| IV 复用（IV = Key[:16]） | 相同明文产生相同密文 | 每次加密使用随机 IV |
| 无密钥派生函数 | 密钥强度取决于硬编码字符串 | 使用 PBKDF2/scrypt |
| SQLite 明文存储 | 加密只在字段级别 | 考虑 SQLCipher 整库加密 |

## Electron 应用逆向小结

Electron 应用的逆向相比原生应用要简单得多：

1. **JS 代码直接可读**：打包压缩 ≠ 编译，格式化一下就能看
2. **数据库在固定位置**：`~/Library/Application Support/{AppName}/`
3. **Node.js API 调用清晰**：`crypto.createCipheriv` 这类调用一搜就到
4. **Chrome DevTools 可用**：部分 Electron 应用可以直接开 DevTools 调试

对开发者的启示：如果你的 Electron 应用需要保护本地数据，**不要在客户端做加密的安全决策**——客户端的一切都是透明的。
