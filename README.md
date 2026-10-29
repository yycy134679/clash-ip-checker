# 🚀 Clash Node IP CHECKER

[中文](README.md) | [English](README_EN.md) | [官网](https://tombcato.github.io/clash-ip-checker/) | [Docker部署](https://github.com/tombcato/clash-ip-checker/tree/docker)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
[![Twitter](https://img.shields.io/badge/Twitter-%40hibearss-1DA1F2?style=flat&logo=twitter&logoColor=white)](https://x.com/hibearss)
[![zread](https://img.shields.io/badge/Ask_Zread-_.svg?style=flat&color=00b0aa&labelColor=000000&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuOTYxNTYgMS42MDAxSDIuMjQxNTZDMS44ODgxIDEuNjAwMSAxLjYwMTU2IDEuODg2NjQgMS42MDE1NiAyLjI0MDFWNC45NjAxQzEuNjAxNTYgNS4zMTM1NiAxLjg4ODEgNS42MDAxIDIuMjQxNTYgNS42MDAxSDQuOTYxNTZDNS4zMTUwMiA1LjYwMDEgNS42MDE1NiA1LjMxMzU2IDUuNjAxNTYgNC45NjAxVjIuMjQwMUM1LjYwMTU2IDEuODg2NjQgNS4zMTUwMiAxLjYwMDEgNC45NjE1NiAxLjYwMDFaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00Ljk2MTU2IDEwLjM5OTlIMi4yNDE1NkMxLjg4ODEgMTAuMzk5OSAxLjYwMTU2IDEwLjY4NjQgMS42MDE1NiAxMS4wMzk5VjEzLjc1OTlDMS42MDE1NiAxNC4xMTM0IDEuODg4MSAxNC4zOTk5IDIuMjQxNTYgMTQuMzk5OUg0Ljk2MTU2QzUuMzE1MDIgMTQuMzk9OSA1LjYwMTU2IDE0LjExMzQgNS42MDE1NiAxMy43NTk5VjExLjAzOTlDNS42MDE1NiAxMC42ODY0IDUuMzE1MDIgMTAuMzk5OSA0Ljk2MTU2IDEwLjM5OTlaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik0xMy43NTg0IDEuNjAwMUgxMS4wMzg0QzEwLjY4NSAxLjYwMDEgMTAuMzk4NCAxLjg4NjY0IDEwLjM5ODQgMi4yNDAxVjQuOTYwMUMxMC4zOTg0IDUuMzEzNTYgMTAuNjg1IDUuNjAwMSAxMS4wMzg0IDUuNjAwMUgxMy43NTg0QzE0LjExMTkgNS42MDAxIDE0LjM5ODQgNS4zMTM1NiAxNC4zOTk4IDQuOTYwMVYyLjI0MDFDMTQuMzk4NCAxLjg4NjY0IDE0LjExMTkgMS42MDAxIDEzLjc1ODQgMS42MDAxWiIgZmlsbD0iI2ZmZiIvPgo8cGF0aCBkPSJNNCAxMkwxMiA0TDQgMTJaIiBmaWxsPSIjZmZmIi8%2BCjxwYXRoIGQ9Ik00IDEyTDEyIDQiIHN0cm9rZT0iI2ZmZiIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIvPgo8L3N2Zz4K&logoColor=ffffff)](https://zread.ai/tombcato/clash-ip-checker)




一个针对 **Clash** (及兼容核心) 的自动化节点工具。它会自动遍历代理节点，默认同时查询 [Ping0](https://ping0.cc/) 和 [IPPure](https://ippure.com/)，分别显示两家的评分、IP 类型和 IP 来源，再重命名节点。两家分数不平均，也不合成总分。
效果展示：
![图片描述](assets/clash-node-checked.png)
Web可视化配置检测：
![alt text](assets/clash-web-check.png)
## 📅 更新日志 (Changelog)

### v2.0.0 (2026-01-11)
- **Web UI**: 全新推出 Web 可视化界面，操作更便捷。
- **多源检测**: 新增 `Ping0` 检测源 支持共享人数，与 `ippure` 互补，并设为默认（速度与信息量平衡更佳）。
- **智能降级**: 新增 `Fallback` 机制，例如：Ping0 失败时自动切换至 IPPure。
- **极速默认**: 极速模式 (`fast_mode`) 默认开启，大幅提升批量检测效率。
- **单点重测**: Web 界面支持对单个节点进行重新检测，方便复核。
- **导出增强**: 支持检测结果的实时预览、编辑和一键导出，一键导入Clash
- **体验优化**: 自动清理 IP 缓存，防止结果残留；优化了端口检测和冲突处理。

### v2.1.0 (2026-10-27)
- **双源检测**: Web、命令行和 YAML 导出默认同时显示 Ping0 与 IPPure 结果。任一家失败或超时，另一家的结果仍会保留。
- **结果隔离**: 两家分别显示评分、IP 类型、原生／广播标记和失败原因。两家出口 IP 不同会上报“出口 IP 不一致”。
- **单源兼容**: 旧配置明确写 `source: ping0` 或 `source: ippure` 时，继续使用原来的主源和降级规则。


## ✨ 功能特点

- **🖥️ Web 可视化界面 (新!)**: 提供现代化的 Web 界面，支持可视化配置，检测可查看实时进度显示、单点重测、结果编辑和导出预览，支持一键跳转导入Clash。
- **极速模式**: 默认 **开启**，通过 Ping0 和 IPPure API 直接检测，速度比浏览器模式更快。Web 界面可直接切换；命令行可在 `config.yaml` 中设置 `fast_mode: false`。
- **双源检测（默认）**: 同时查询 Ping0 和 IPPure，分别显示 `Ping0 风控`、`IPPure 评分`。也可以切换到单一主源；降级限制见下方「检测与恢复」。
- **数据归属清楚**: Ping0 提供共享人数，IPPure 浏览器模式提供 Bot 比例。任一 API 模式都不提供 Bot 比例；IPPure API 也不提供共享人数。
- **自动切换**: 自动遍历并切换你的 Clash 代理节点。
- **深度 IP 分析**: 检测 IP 风险分、IP 类型 (住宅/机房)、IP 来源 (原生/广播) 和共享人数。浏览器模式还会显示 IPPure 的 Bot 比例。
- **高拟真检测 (可选)**: 在浏览器模式下使用 **Playwright** 进行高拟真检测，包含 Bot 比例分析。支持无头模式 (Headless) 配置。
- **智能过滤**: 自动跳过无效节点 (如 "到期", "流量重置", "官网" 等)。
- **配置注入**: 生成一个新的 Clash 配置文件 (`_checked.yaml`)，在节点名称后追加 Emoji 和状态信息。
- **强制全局模式**: 检测前保存当前模式和节点，再切换为全局模式；完成、停止或发生异常后恢复原设置。

##  ⚡新增Docker部署 [详情见Docker分支](https://github.com/tombcato/clash-ip-checker/tree/docker)
相对于主分支而言，Docker部署后代理切换不影响本地网络（部署NAS或者云服务器），且能直接输入订阅链接输出新订阅链接，没有繁琐的使用步骤，**一键替换订阅url检测！**
**云部署Demo地址：https://tombcat.space/ipcheck** 

## 🛠️ 前置要求

- **Python 3.10+**
- **Clash Verge** (或其他开启了 External Controller 的 Clash 客户端)

## 📦 安装说明

1.  **克隆仓库**
    ```bash
    git clone https://github.com/tombcato/clash-ip-checker.git
    cd clash-ip-checker
    ```

2.  **安装依赖**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.lock
    # 非极速模式需要
    playwright install chromium
    # 如果 install chromium 运行失败说明 playwright 没添加环境变量，可以用：
    # python -m playwright install chromium
    ```

3.  **启动 Web 界面 (新版推荐)**
    ```bash
    python web.py
    ```
    访问 http://127.0.0.1:8080 即可使用图形化界面进行配置和检测。
    macOS 完成安装后也可双击 `start.command` 启动。
    
4.  **命令行模式 (旧版)**
    - 修改 `config.yaml.example` 删除后缀重命名为 `config.yaml`。
    - 编辑 `config.yaml` 填入命令行配置。Web 界面使用页面上的独立设置，不读取此文件：
        - `yaml_path`: 你的 Clash 配置文件 (**.yaml**) 的绝对路径。
        - `clash_api_secret`: 你的 API 密钥 (如果有的话)。
        - `fast_mode`: ⚡ 是否使用极速模式 (True/False)。
        - `source`: 检测源，可选 `both`、`ping0` 或 `ippure` (默认 `both`)。
        - `fallback`: 单源检测是否尝试备用检测源 (True/False)。具体限制见下方「检测与恢复」。
    - 运行 `python clash_automator.py`。

## Web 界面使用方法 (新版推荐)

Web 输入的 YAML 顶层需要是映射；`proxies` 必须包含至少一个节点，每个节点都需要非空的 `name`。

1. 打开你的 Clash 客户端 (例如 Clash Verge) 将当前clash正在运行的订阅配置文件切换为你想要测试的订阅，点击获取YAML源代码，然后复制粘贴进[web界面](http://127.0.0.1:8080)的yaml框中
    ![alt text](assets/clash-open-yaml-code.png)
2. 确保Clash中 External Controller (外部控制) 已在设置中开启，密码随便设置, 然后再Web界面中配置
![alt text](assets/clash-controller.png)
3. 使用默认配置直接点击开始即可，检测完成后会可一键预览导入Clash
![alt text](assets/clash-web-check.png)

## 命令行模式使用方法（旧版）

1.  打开你的 Clash 客户端 (例如 Clash Verge) 将当前clash正在运行的订阅配置文件切换为你想要测试的订阅， 然后获取该配置文件的yaml文件绝对路径, 在config.yaml中配置yaml_path.
    右键配置文件选择打开文件
    ![](assets/clash-open-yaml.png)
    通过vscode获取path
    ![](assets/clash-open-yaml-vscode.png)
    或者通过记事本获取path, 鼠标悬停展示但无法复制，需要在对应的文件夹中找到再复制
    ![](assets/clash-open-yaml-jsb.png)

1.  确保 **External Controller** (外部控制) 已在设置中开启，并在config.yaml中配置clash_api_url与clash_api_secret与之对应。密码随便设置
    ![alt text](assets/clash-controller.png)
2.  运行脚本:
    ```bash
    python clash_automator.py
    ```
    *默认使用极速模式，不启动浏览器。如需 Bot 比例检测，在 `config.yaml` 中设置 `fast_mode: false`，并先安装 Chromium。*

3.  脚本将会:
    - 连接到 Clash API。
    - 切换到 "Global" (全局) 模式。
    - 逐个测试代理节点，默认同时访问 Ping0 和 IPPure。
    - 生成一个名为 `your_config_checked.yaml` 的新文件。
4.  在项目当前文件夹下将生成的 `_checked.yaml` 文件导入 Clash 即可切换该配置查看结果！
    导入_checked.yaml配置
    ![](assets/clash-import.png)

## 📝 输出示例

你的代理节点将会被重命名，直观展示其质量：

### 🔍 结果解读

双源模式默认使用两家各自的评分：

```text
【Ping0 20%｜IPPure 35%】
【Ping0 超时｜IPPure 35%】
```

* 第一段是 Ping0 风控分，第二段是 IPPure 评分。分数越低越好。
* 一家超时或失败时，仍显示另一家的分数。
* 两家都失败时显示 `【Ping0 失败｜IPPure 失败】`。
* 两家看到的出口 IP 不同时，页面状态显示 `⚠️ IP 不一致`，两家 IP 分别保留。
* 两家分数不平均，也不生成“总风险分”。

单源模式继续使用原来的 Emoji 后缀。格式随数据源和检测方式变化：

* Ping0 极速模式：`【🟢🟡 住宅|原生】`。第 1 个 Emoji 是风控分，第 2 个 Emoji 是共享人数。
* IPPure 浏览器模式：`【🟢🟡 住宅|原生】`。第 1 个 Emoji 是评分，第 2 个 Emoji 是 Bot 比例。
* IPPure API 模式：`【🟢 住宅|原生】`。没有第 2 个 Emoji，因为 API 不返回 Bot 比例。
* `住宅 / 机房` 是 **IP 类型**；`原生 / 广播` 是 **IP 来源**。两者是不同字段，可以独立组合。

#### 📊 评分对照表

| 范围 | Emoji | 含义 |
| :--- | :---: | :--- |
| **0 - 10%** | ⚪ | **极佳** |
| **11 - 30%** | 🟢 | **优秀** |
| **31 - 50%** | 🟡 | **良好** |
| **51 - 70%** | 🟠 | **中等** |
| **71 - 90%** | 🔴 | **差** |
| **> 90%** | ⚫ | **极差** |

#### 🏷️ 常见标签说明

*   **住宅 (Residential)**: 家庭宽带 IP，隐蔽性高，被封锁概率低。
*   **机房 (Datacenter)**: 数据中心 IP，速度快但容易被识别。
*   **原生 (Native)**: 指该 IP 归属于当地运营商，通常解锁流媒体 (Netflix, Disney+) 效果最好。
*   **广播 (Broadcast)**: IP 地理位置与注册地不符。

## ⚙️ 配置项

查看 `config.yaml.example` 获取所有可用配置项的说明。

## 检测与恢复

默认使用极速模式，同时查询 Ping0 和 IPPure。双源检测先获取出口 IP，再分别限制 Ping0 检测为 6 秒、IPPure API 检测为 5 秒或 IPPure 浏览器检测为 40 秒。每家独立记录成功、失败或超时；一家失败不会截断另一家的结果。

`source: ping0` 或 `source: ippure` 使用单源模式。极速单源检测在主源失败且 `fallback` 开启时尝试另一家；获取 IP、主源和备用源共用 3 秒时限，超时会直接结束。选择 Ping0 单源浏览器模式时仍使用极速检测。IPPure 单源浏览器检测失败或超时后，若开启 `fallback`，会使用 Ping0 的极速检测作为备用，备用检测另限时 3 秒。IPPure 不提供共享人数，API 模式不提供 Bot 比例。

批量检测、单点重测和命令行检测会先读取原模式和所选代理组的当前节点。读取失败时不开始检测。检测结束后恢复原节点和模式；点击停止后，等待当前节点检测和恢复完成，再开始下一轮。恢复失败时会显示错误，需要你在 Clash 中手动恢复。强制结束进程或断电后需要手动检查设置。

## 开发验证

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

回归测试使用模拟节点，不连接本机 Clash，也不切换实际节点。`requirements.lock` 固定运行依赖版本；修改 `requirements.txt` 后可运行 `uv pip compile --universal --python-version 3.10 requirements.txt -o requirements.lock` 更新。

## 🤝 贡献参与

欢迎提交 Pull Request 来改进这个项目！

## ⚠️ 免责声明

本工具仅供教育和测试使用。请遵守当地法律法规，并合理使用代理服务。

## 🌟 Star 记录

[![Star History Chart](https://api.star-history.com/svg?repos=tombcato/clash-ip-checker&type=Date)](https://star-history.com/#tombcato/clash-ip-checker&Date)






