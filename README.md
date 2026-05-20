# Antigravity CLI Status Line

一个给 Anti Gravity / Antigravity CLI 用的状态栏配置：显示当前模型、Agent 状态、上下文剩余百分比、当前目录、当前模型的真实 quota 剩余百分比，以及本轮 token 统计。

## 效果

```text
Gemini 3.1 Pro (High) | Idle | Context 92% left | ~/Desktop/opc/right-enhance | Quota: 100% | ↑85k ↓94k 179k tok
  Tip: Use /goal for complex, multi-step tasks that need deep focus.
```

## 文件

- `status.py`: Antigravity statusLine command 脚本。
- `agy-quota-cache.py`: 把 `/usage` 输出解析成本地 quota 缓存，供状态栏读取。

## 安装

```bash
mkdir -p ~/.antigravity
cp status.py ~/.antigravity/status.py
cp agy-quota-cache.py ~/.antigravity/agy-quota-cache.py
chmod +x ~/.antigravity/status.py ~/.antigravity/agy-quota-cache.py
```

然后在 `~/.gemini/antigravity-cli/settings.json` 中配置：

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 /Users/YOUR_USER/.antigravity/status.py"
  }
}
```

## 真实 Quota

状态栏会直接读取本机 Antigravity `language_server` 的 `GetUserStatus` 接口，数据来源和内置 `/usage` 是同一套本地状态。它会自动发现：

- `language_server` 进程
- 本地监听端口
- `X-Codeium-Csrf-Token`

默认每 30 秒刷新一次 quota。新开对话、账号变化、缓存不存在或当前模型缺失时，会立即刷新，不需要手动复制 `/usage` 输出。

刷新结果会写入本地缓存，接口短暂失败时可回退显示上一次成功结果：

```text
~/.antigravity/quota-cache.json
```

状态栏会按当前模型名称匹配缓存中的 quota，例如 `Gemini 3.1 Pro (High)` 只显示这一行模型的剩余量。

## 手动备用

如果本地接口不可用，也可以用内置 `/usage` 弹层作为备用：在 Antigravity CLI 里运行 `/usage`，复制输出，然后执行：

```bash
pbpaste | python3 ~/.antigravity/agy-quota-cache.py
```

例如 `/usage` 弹层显示：

```text
Gemini 3.1 Pro (High)
40% remaining · Refreshes in 1h 32m
```

缓存器会把 `Gemini 3.1 Pro (High)` 解析为 `40%`。同一次复制只更新复制内容中出现的模型，其他模型会保留上一次缓存值。

## 可选环境变量

- `AGY_QUOTA_CACHE`: 自定义 quota 缓存路径。
- `AGY_QUOTA_MAX_AGE_SECONDS`: quota 缓存有效期，默认 `900` 秒。
- `AGY_QUOTA_REFRESH_INTERVAL_SECONDS`: 自动刷新间隔，默认 `30` 秒。
