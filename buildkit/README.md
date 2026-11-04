# Labelme 7.9.1 Windows 单文件构建

此目录提供 Windows x64 单文件 EXE 构建和验证流程。

固定源码版本为 `v7.9.1`，提交 `d179c2353dcf35a29809797b2702dba8d794b84e`。
源代码不作补丁，依赖来自该版本的 `uv.lock`。

## GitHub Actions

将压缩包内的 `buildkit/` 和 `.github/` 放入允许使用的 GitHub 仓库。
在 Actions 中手动运行 `Build Labelme 7.9.1 Windows EXE`。
工作流使用 Windows Server 2022 x64 和 Python 3.12，构建后运行实际 EXE 自检。
只有自检成功才上传 `Labelme-7.9.1-Windows-x64` 成品附件。
失败时另上传构建警告、测试报告及应用日志，供排查。

工作流也监听 `codex/labelme-7.9.1-windows` 分支上对上述文件的 push。
如果 fork 的仓库禁用了 Actions，需要先在该仓库的 Actions 页面启用。

## 本地 Windows 构建

需要 Windows x64、Python 3.12 x64、Git 和 PowerShell 7。
在解压目录中使用独立 Python 环境，再执行：

```powershell
pwsh -File .\buildkit\build-windows.ps1
```

构建需要联网下载固定版本的依赖。完成后查看 `dist/`。

## 打包细节

- PyInstaller 单文件 GUI 模式，保留官方图片资源、中文翻译与 Qt 插件。
- 包含 ONNXRuntime 和 osam 的动态模块与资源，未预置 AI 模型权重。
- 保留原版 `%LOCALAPPDATA%\labelme\labelme.log`；增加启动阶段的异常日志。
- 自动自检覆盖真实打包程序的启动、依赖加载及 PNG/JSON 标注读写。
- 已在 Linux / Python 3.12 下运行同一份自检脚本，原版源码的版本、依赖加载、
  中文翻译、窗口创建、PNG 图片读取和标注 JSON 保存/重开均通过。
- 上述源码测试不等同于 Windows EXE 验证；Windows 自检必须由 Windows 构建机执行。
