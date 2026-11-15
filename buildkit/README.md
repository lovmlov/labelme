# Labelme 7.9.1 Windows 单文件构建

本分支基于 `v7.9.1-layout.2`，增加主窗口退出及资源清理修复；保留边缘单击加点、工具栏和按钮拖动布局。应用版本 `7.9.1+exit.1`。

## GitHub Actions

`codex/labelme-7.9.1-exit` 分支的源码变更触发 `Build and release Labelme 7.9.1 clean-exit Windows EXE`。工作流使用 Windows Server 2022 x64、Python 3.12，只有源码测试及实际冻结程序的所有验证通过才创建 `v7.9.1-exit.1` Release。已有 Release 不覆盖。

如果 fork 的 Actions 被 GitHub 暂停，仓库维护者须先从 Actions 页面重新启用，再重新触发分支构建。

`Diagnose published Labelme exit` 独立下载旧版 `layout.2`，观察默认及浮动布局的原生关闭。旧版未复现驻留并不能排除特定电脑或模型使用场景的问题。

## 本地 Windows 构建

需要 Windows x64、Python 3.12 x64、Git 和 PowerShell 7：

```powershell
pwsh -File .\buildkit\build-windows.ps1
```

在隔离虚拟环境中安装固定依赖并构建本分支。打包使用 PyInstaller 单文件 GUI 模式，附带 Qt、ONNXRuntime、osam 资源；AI 模型权重不内置。产物位于 `dist/`。

## 验证与报告

- `windows-tests.xml`：源码回归，包括标注交互、布局、后台保存、预取、模型管理和退出资源。
- `smoke-test.json`：真实 EXE 的依赖加载、标注读写及工具栏自检。
- `exit-test.json`：真实 main()/app.exec() 的 7 种退出场景，以及 PyInstaller 整个进程树的退出状态。
- `native-exit-default.json`、`native-exit-floating.json`：外部发送 Windows WM_CLOSE 并观察完整进程树。
- `build/exit-tests/`：逐场景生命周期、线程和控制台日志；失败时上传供排查。

`psutil` 仅在开发/构建环境供外部观察器使用，不进入应用运行依赖。测试观察器超时后只清理自己的测试进程树，并记录失败，不将强制结束当作退出成功。

程序日志：`%LOCALAPPDATA%\labelme\labelme.log` 及 `portable-startup.log`。Linux 源码测试不等于 Windows EXE 验证；发布门槛必须在 Windows 执行。
