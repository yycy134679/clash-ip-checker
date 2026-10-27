# Repository Guidelines

## 项目结构

- `web.py` 启动 FastAPI Web 服务；`routers/` 提供页面和 API 路由，`state.py` 管理运行状态，`schemas.py` 定义请求模型。
- `clash_automator.py` 是命令行入口；`core/` 负责 Clash 控制与 IP 检测，`core/sources/` 存放检测源，`utils/` 存放配置加载工具。
- `templates/` 和 `static/` 存放 Web 界面；`assets/` 存放项目图片，`docs/` 存放项目展示网站。回归测试位于 `tests/`。

## 安装、运行与测试

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python web.py
```

开发依赖包含锁定的运行依赖。Web 界面地址为 `http://127.0.0.1:8080`。命令行模式使用 `config.yaml`，可从 `config.yaml.example` 复制后填写，再运行 `python clash_automator.py`。浏览器检测模式还需运行 `python -m playwright install chromium`。

运行回归测试：

```bash
python -m unittest discover -s tests -v
```

修改 `requirements.txt` 后，使用 `uv pip compile --universal --python-version 3.10 requirements.txt -o requirements.lock` 更新锁定文件。

## 编码与测试约定

Python 使用四空格缩进，函数和变量使用 `snake_case`，类使用 `PascalCase`。沿用相邻代码的风格；仓库目前没有配置统一的格式化或 lint 工具。测试使用标准库 `unittest` 和 FastAPI 的 `TestClient`；测试文件和方法分别以 `test_` 开头。新增行为或修复问题时，补充覆盖关键路径和失败情况的测试。现有测试使用模拟对象，不连接本机 Clash。仓库未设定覆盖率门槛。

## 提交与 Pull Request

提交历史包含 `feat:` 等前缀和普通描述。建议使用简短、明确的提交说明，例如 `feat: 支持新的检测源`。Pull Request 请说明变更目的、主要行为和测试结果；有关联 issue 时附上链接，界面变更附上截图。

## 配置与安全

本地 `config.yaml` 可能包含 Clash 密钥和订阅信息；不要提交真实配置或导出的节点数据。实际检测会切换 Clash 节点，修改检测流程时应保留结束后恢复原模式和节点的行为。
