# Windows 安装和启动

需要 Python 3.10+、Node.js 20.9+ 和可运行的 Stockfish。建议将项目放在有足够空间的数据盘。
在项目根目录用 PowerShell 完成一次安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

如果已有 `.env`，保留现有配置，跳过复制。将适合电脑的 Windows Stockfish 可执行文件放到
`backend/engine/bin/stockfish.exe`，同时保留发行包中的许可证文件；也可在 `.env` 用
`STOCKFISH_PATH` 指向现有引擎的绝对路径。

下面两行配置仅供本页的 Windows 启动器使用。已有 `frontend/.env.local` 时，编辑其中的
`NEXT_PUBLIC_API_BASE` 为该地址，保留其他设置：

```powershell
Set-Content -LiteralPath frontend/.env.local -Value 'NEXT_PUBLIC_API_BASE=http://127.0.0.1:8017' -Encoding utf8
Set-Location frontend
npm ci
$env:NEXT_TELEMETRY_DISABLED = '1'
npm run build
Set-Location ..
```

双击项目根目录的 `启动复盘教练.cmd`，打开 `http://127.0.0.1:3017`。后端只监听本机
`127.0.0.1:8017`，启动器为这些地址配置跨域访问。首次体验可点击「填入示例」并开始复盘。

双击 `停止复盘教练.cmd` 关闭本启动器管理的服务，保存的棋局和授权会保留。
再次启动会恢复已有棋局。如果端口被其他程序占用，启动器会报错，不会结束其他程序。
启动日志位于忽略提交的 `.run/`；可用 `powershell -File scripts/windows.ps1 -Action status` 查看状态。

修改前端代码后先停止服务，在 `frontend` 重新执行 `npm run build`，再启动。
修改后端或 `.env` 后重启服务即可。也可以继续使用 README 中的独立前后端开发流程，
此时应让 `NEXT_PUBLIC_API_BASE`、前端端口与后端 `CORS_ORIGINS` 保持一致。
