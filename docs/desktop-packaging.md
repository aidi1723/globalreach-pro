# 桌面安装包打包说明

## 目标

对外分发时，不再交付源码目录，而是交付桌面安装包：

- macOS：`.app` / `.dmg`
- Windows：`.exe`

当前项目默认在不同平台使用不同打包后端，入口文件是 [main.py](/Users/aidi/群发工具/main.py)。

- macOS：默认使用 `PyInstaller`
- Windows：默认使用 `Nuitka`

说明：

- 当前这台 macOS 打包机上的 `uv Python 3.12 + tkinter` 与 `Nuitka` 存在依赖扫描兼容问题
- 为了保证可交付，macOS 默认后端切到 `PyInstaller`
- 如果后续更换构建机，也可以显式指定 `--backend nuitka`

## 运行时目录

打包后，软件本地状态和数据库不再写回源码目录，而是写到用户目录：

- macOS：`~/Library/Application Support/globalreach-pro/globalreach.db`
- Windows：`%APPDATA%\\globalreach-pro\\globalreach.db`
- Linux：`~/.local/share/globalreach-pro/globalreach.db`

这样安装包发到别的电脑后，授权状态、模板草稿、SMTP 配置和发送记录都能正常持久化。

## 安装构建依赖

```bash
./.venv/bin/pip install -r requirements-build.txt
```

## 构建 macOS 安装包

生成 `.app`：

```bash
./.venv/bin/python tools/build_desktop.py --target macos --clean
```

同时生成 `.dmg`：

```bash
./.venv/bin/python tools/build_desktop.py --target macos --clean --create-dmg
```

如果需要强制使用指定后端：

```bash
./.venv/bin/python tools/build_desktop.py --target macos --backend pyinstaller --clean
./.venv/bin/python tools/build_desktop.py --target macos --backend nuitka --clean
```

默认输出目录：

```text
dist/desktop/
```

默认 macOS 产物名称：

```text
dist/desktop/GlobalReachPro.app
dist/desktop/GlobalReachPro-2026.04.14.dmg
```

## 构建 Windows 可执行程序

需要在 Windows 环境执行：

```bash
python tools/build_desktop.py --target windows --backend nuitka --clean
```

说明：

- 不建议在 macOS 上直接交叉生成 Windows `.exe`
- Windows 产物应在 Windows 本机或 Windows CI 环境构建
- 默认 Windows 产物名称为 `dist/desktop/GlobalReachPro.exe`

## 分发建议

- 内部测试：优先发 `.app` 或 `.exe`
- 正式客户：macOS 发 `.dmg`，Windows 发 `.exe`
- 首次打开时走现有线上授权流程，输入激活码即可

## 构建前检查

- 本机已安装 Python 虚拟环境依赖
- 线上授权地址已配置
- macOS 打包机可正常运行 `hdiutil`
- 需要发给客户前，先在干净账户或另一台机器做一次完整激活验证
