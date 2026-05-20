# Antigravity CLI Status Line

一个给 Anti Gravity / Antigravity CLI 用的状态栏配置：显示当前模型、Agent 状态、上下文剩余百分比、当前目录、当前模型的真实 `/usage` quota 剩余百分比，以及本轮 token 统计。

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

## 同步真实 Quota

Antigravity 的真实模型额度来自内置 `/usage` 命令。状态栏不会伪造 quota，只读取 `/usage` 的缓存。

在 Antigravity CLI 里运行 `/usage`，复制输出，然后执行：

```bash
pbpaste | python3 ~/.antigravity/agy-quota-cache.py
```

默认缓存位置是：

```text
~/.antigravity/quota-cache.json
```

状态栏会按当前模型名称匹配缓存中的 quota，例如 `Gemini 3.1 Pro (High)` 只显示这一行模型的剩余量。缓存过期或不存在时会显示 `Quota: sync /usage`，不会展示假百分比。

如果 `/usage` 弹层显示：

```text
Gemini 3.1 Pro (High)
40% remaining · Refreshes in 1h 32m
```

缓存器会把 `Gemini 3.1 Pro (High)` 解析为 `40%`。同一次复制只更新复制内容中出现的模型，其他模型会保留上一次缓存值。

## 可选环境变量

- `AGY_QUOTA_CACHE`: 自定义 quota 缓存路径。
- `AGY_QUOTA_MAX_AGE_SECONDS`: quota 缓存有效期，默认 `900` 秒。
