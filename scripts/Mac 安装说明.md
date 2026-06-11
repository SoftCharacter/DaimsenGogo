# Mac 安装说明

本文档适用于第一次从 GitHub 下载项目、电脑中可能尚未安装开发环境的 macOS 用户。

项目启动前需要准备：

- Homebrew：用于安装和管理运行环境
- Miniconda：提供 `conda` 命令和项目 Python 环境
- Node.js 18 或更高版本：提供前端所需的 `node` 与 `npm`

以下命令均在 macOS 的“终端”应用中运行。可以按 `Command + 空格`，搜索“终端”并打开。

## 第一步：安装 Homebrew

先检查是否已经安装：

```bash
brew --version
```

如果提示 `command not found: brew`，运行 Homebrew 官方安装命令：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

安装结束后，按照终端最后显示的 `Next steps` 配置 Homebrew，然后关闭并重新打开终端。

再次确认：

```bash
brew --version
```

## 第二步：安装 Miniconda 和 Node.js

运行：

```bash
brew install --cask miniconda
brew install node
```

初始化 Conda，使后续打开的终端可以直接使用 `conda` 命令：

```bash
conda init "$(basename "${SHELL}")"
```

关闭并重新打开终端。

## 第三步：接受 Anaconda 默认频道服务条款

Conda 首次创建项目环境前，需要由用户接受 Anaconda 默认频道的服务条款：

```bash
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
```

Conda 本身可以免费使用，但 Anaconda 默认频道受其服务条款约束，组织或商业使用者应自行确认许可要求。

## 第四步：确认运行环境

依次运行以下命令：

```bash
conda --version
node --version
npm --version
```

三个命令都应显示版本号。Node.js 版本应为 18 或更高版本。

如果任一命令提示 `command not found`，请先重新打开终端再试；仍然失败时，重新检查前面的安装步骤。

## 第五步：启动项目

先在终端进入项目目录。可以输入 `cd `，然后将项目文件夹拖入终端窗口，按回车执行。

确认当前目录正确：

```bash
ls scripts/start.sh
```

如果能看到 `scripts/start.sh`，运行：

```bash
bash scripts/start.sh
```

首次启动时，脚本会创建名为 `env_reactAgent` 的 Conda 环境，并安装后端和前端依赖，需要等待几分钟。后续再次启动时，未发生变化的依赖会自动跳过。

启动成功后访问：

- 前端：`http://localhost:5173`
- 后端接口文档：`http://localhost:8000/docs`

在终端按 `Control + C` 可以停止项目。
