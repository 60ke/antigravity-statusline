# Antigravity CLI Status Line

English | [中文](#中文)

Una línea de estado colorida para Antigravity CLI / `agy` que muestra:

- modelo activo
- estado del agente
- porcentaje de contexto restante
- directorio de trabajo actual
- cuota real restante para el modelo activo
- totales de tokens de la sesión
- consejos (tips) rotativos

Lee la cuota directamente de la API `GetUserStatus` del `language_server` local de Antigravity, el mismo estado local utilizado por `/usage`. No se requiere sincronización manual en el uso normal.

## Vista Previa

![Antigravity CLI status line preview](assets/statusline-preview.png)

```text
Gemini 3.1 Pro (High) | Idle | Context 92% left | ~/Desktop/opc/right-enhance | Quota: 40% · reset 1h 21m | ↑85k ↓15k 100k tok
  Tip: Use /agents to see all active sub-agents and their status.
```

## Instalación

```bash
git clone https://github.com/60ke/antigravity-statusline.git
cd antigravity-statusline
./install.sh
```

Luego reinicie Antigravity CLI o inicie una nueva sesión de `agy`.

El instalador:

- copia los scripts a `~/.antigravity/`
- respalda los archivos existentes en `~/.antigravity/backups/`
- actualiza `~/.gemini/antigravity-cli/settings.json`
- preserva todos los ajustes no relacionados

## Instalación en una línea

```bash
git clone https://github.com/60ke/antigravity-statusline.git /tmp/antigravity-statusline && /tmp/antigravity-statusline/install.sh
```

## Desinstalación

```bash
cd antigravity-statusline
./uninstall.sh
```

El desinstalador elimina los scripts instalados y remueve el comando `statusLine` de este repositorio de los ajustes de Antigravity. También crea un respaldo antes de editar los ajustes.

## Cómo funciona la Cuota (Quota)

La línea de estado automáticamente:

- busca el proceso local de `language_server` de Antigravity
- busca los procesos locales del servidor de CLI `agy`
- extrae el token CSRF local desde su línea de comandos
- descubre el puerto de escucha local
- llama a `GetUserStatus`
- empareja la cuota mediante la etiqueta del modelo activo
- prefiere la respuesta de la API local cuyo correo electrónico coincida con la sesión actual de Antigravity CLI
- muestra la cuenta regresiva para el reinicio desde el tiempo de reinicio de cuota del modelo

La cuota se actualiza cada 30 segundos por defecto. También se actualiza inmediatamente cuando cambia la sesión/cuenta/modelo activos o cuando no hay caché disponible.

Si la API local no está disponible temporalmente, recurre a la última caché exitosa:

```text
~/.antigravity/quota-cache.json
```

## Alternativa Manual

Si la API local no está disponible, ejecute `/usage`, copie la salida y luego:

```bash
pbpaste | python3 ~/.antigravity/agy-quota-cache.py
```

## Variables de Entorno

- `AGY_STATUSLINE_DIR`: directorio de instalación, predeterminado `~/.antigravity`
- `AGY_SETTINGS_FILE`: ruta de ajustes, predeterminado `~/.gemini/antigravity-cli/settings.json`
- `AGY_QUOTA_CACHE`: ruta de caché de cuota, predeterminado `~/.antigravity/quota-cache.json`
- `AGY_QUOTA_MAX_AGE_SECONDS`: edad máxima de la caché, predeterminado `900`
- `AGY_QUOTA_REFRESH_INTERVAL_SECONDS`: intervalo de actualización en vivo, predeterminado `30`

## Archivos

- `status.py`: renderizador de la línea de estado y extractor de cuota en vivo
- `agy-quota-cache.py`: alternativa de análisis manual de `/usage`
- `install.sh`: instalador
- `uninstall.sh`: desinstalador

---

## 中文

[English](#antigravity-cli-status-line) | 中文

这是一个给 Antigravity CLI / `agy` 用的彩色状态栏配置，可以显示：

- 当前模型
- Agent 状态
- 上下文剩余百分比
- 当前工作目录
- 当前模型的真实剩余额度
- 本轮 token 统计
- 轮换 Tips

它会直接读取本机 Antigravity `language_server` 的 `GetUserStatus` 接口，数据来源和内置 `/usage` 是同一套本地状态。正常情况下不需要手动同步。

## 效果

![Antigravity CLI 状态栏预览](assets/statusline-preview.png)

```text
Gemini 3.1 Pro (High) | Idle | Context 92% left | ~/Desktop/opc/right-enhance | Quota: 40% · reset 1h 21m | ↑85k ↓15k 100k tok
  Tip: Use /agents to see all active sub-agents and their status.
```

## 安装

```bash
git clone https://github.com/60ke/antigravity-statusline.git
cd antigravity-statusline
./install.sh
```

然后重启 Antigravity CLI，或者重新打开一个 `agy` 会话。

安装脚本会：

- 把脚本复制到 `~/.antigravity/`
- 把旧文件备份到 `~/.antigravity/backups/`
- 更新 `~/.gemini/antigravity-cli/settings.json`
- 保留所有无关配置

## 一行安装

```bash
git clone https://github.com/60ke/antigravity-statusline.git /tmp/antigravity-statusline && /tmp/antigravity-statusline/install.sh
```

## 卸载

```bash
cd antigravity-statusline
./uninstall.sh
```

卸载脚本会删除安装到 `~/.antigravity/` 的脚本，并移除本仓库写入的 `statusLine` 配置。修改配置前也会自动备份。

## Quota 原理

状态栏会自动：

- 查找本机 Antigravity `language_server` 进程
- 查找本机 `agy` CLI server 进程
- 从进程命令行提取本地 CSRF token
- 发现本地监听端口
- 调用 `GetUserStatus`
- 按当前模型名称匹配 quota
- 优先使用 email 与当前 Antigravity CLI 会话一致的本地 API 响应
- 根据模型 quota reset time 显示重置倒计时

默认每 30 秒刷新一次。新会话、账号、模型变化或缓存不存在时，会立即刷新。

如果本地接口短暂不可用，会回退到上一次成功缓存：

```text
~/.antigravity/quota-cache.json
```

## 手动备用

如果本地接口不可用，可以运行 `/usage`，复制输出，然后执行：

```bash
pbpaste | python3 ~/.antigravity/agy-quota-cache.py
```

## 环境变量

- `AGY_STATUSLINE_DIR`: 安装目录，默认 `~/.antigravity`
- `AGY_SETTINGS_FILE`: settings 路径，默认 `~/.gemini/antigravity-cli/settings.json`
- `AGY_QUOTA_CACHE`: quota 缓存路径，默认 `~/.antigravity/quota-cache.json`
- `AGY_QUOTA_MAX_AGE_SECONDS`: 缓存最长有效时间，默认 `900`
- `AGY_QUOTA_REFRESH_INTERVAL_SECONDS`: 实时刷新间隔，默认 `30`

## 文件说明

- `status.py`: 状态栏渲染和实时 quota 获取
- `agy-quota-cache.py`: 手动 `/usage` 解析备用工具
- `install.sh`: 安装脚本
- `uninstall.sh`: 卸载脚本
