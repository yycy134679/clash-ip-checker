# 🚀 Clash Node Automator (Auto-IPCheck)

[中文](README.md) | [English](README_EN.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-GPL--3.0-green)

An intelligent automation tool for **Clash Verge** (and compatible cores). It tests each proxy node through both [Ping0](https://ping0.cc/) and [IPPure](https://ippure.com/) by default, shows each provider's score and IP details separately, and adds the results to node names. Scores are never averaged into a combined risk score.

![Demo Image](assets/clash-node-checked.png)

> **Note**: Browser Mode uses **Playwright** for fingerprint-based detection and IPPure's Bot ratio. Fast Mode uses the provider APIs and does not return a Bot ratio.

## ✨ Features

- **Dual-Source Checks (Default)**: Queries Ping0 and IPPure, then displays `Ping0 risk` and `IPPure score` separately. One provider failing does not discard the other provider's result.
- **⚡ Fast Mode (New!)**: Enabled by default and uses direct API checks for faster runs. Change it in the Web interface, or set `fast_mode: false` in `config.yaml` for the CLI.
- **Auto-Switching**: Automatically cycles through your Clash proxies.
- **Deep IP Analysis**: Checks risk scores, IP type (Residential/Data Center), IP source (Native/Broadcast), shared users, and IPPure's Bot ratio in Browser Mode.
- **High-Fidelity Detection (Optional)**: Uses **Playwright** in Browser Mode for accurate fingerprinting detection including Bot Score.
- **Smart Filtering**: Skips invalid nodes (e.g., "Expire Date", "Traffic Reset") automatically.
- **Config Injection**: Generates a new Clash Config (`_checked.yaml`) with emojis and stats appended to node names.
- **Global Mode Force**: Saves the current mode and selected node, uses Global mode during testing, and restores both afterward.

## 🛠️ Prerequisites

- **Python 3.10+**
- **Clash Verge** (or any Clash client with External Controller enabled)
- **Playwright** (for Browser Mode)
- **curl_cffi** (for Fast Mode)

## 📦 Installation

1.  **Clone the Repository**
    ```bash
    git clone https://github.com/tombcato/clash-ip-checker.git
    cd clash-ip-checker
    ```

2.  **Install Dependencies**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements.lock
    # Browser Mode only
    playwright install chromium
    # If playwright install fails, try: python -m playwright install chromium
    ```

3.  **Configure**
    - **Rename `config.yaml.example` to `config.yaml`**.
    - Edit `config.yaml` and fill in your details:
        - `fast_mode`: ⚡ Enable Fast Mode (True/False).
        - `source`: `both` (default), `ping0`, or `ippure`.
        - `fallback`: Allow a retry with the other provider in single-source mode. See the limits under Detection and recovery.
        - `yaml_path`: The absolute path to your current Clash configuration file.
          > **Windows Tip**: Use single quotes `'` around the path (e.g., `'C:\Users\...'`) to avoid having to double-escape backslashes.
        - `clash_api_secret`: Your API key (if any).

## 🚀 Usage

1.  Open your Clash Client (e.g., Clash Verge), switch to the profile you want to test, get its absolute YAML path, and configure `yaml_path` in `config.yaml`.
    ![Get YAML Path](assets/clash-open-yaml.png)
    ![Path via VSCode](assets/clash-open-yaml-vscode.png)
    ![Path via Notepad](assets/clash-open-yaml-jsb.png)
2.  Enable **External Controller** in Settings.
3.  Run the script:
    ```bash
    python clash_automator.py
    ```
    *Fast Mode is enabled by default and does not launch Chromium. For Browser Mode, install Chromium and set `fast_mode: false` in `config.yaml`.*

4.  The script will:
    - Connect to Clash API.
    - Switch to "Global" mode.
    - Test each proxy one by one through Ping0 and IPPure.
    - Generate a new file named `your_config_checked.yaml`.
5.  Import the new `_checked.yaml` into Clash to see the results!
    ![Import Config](assets/clash-import.png)

## 📝 Output Example

Your proxy nodes will be renamed to provide instant visibility into their quality:

### 🔍 Result Interpretation

Dual-source mode uses each provider's numeric score:

```text
【Ping0 20%｜IPPure 35%】
【Ping0 超时｜IPPure 35%】
```

* The first value is Ping0's risk score; the second is IPPure's score. Lower is better.
* If one provider fails or times out, the other provider's result remains visible.
* If both fail, the suffix is `【Ping0 失败｜IPPure 失败】`.
* If the two providers see different exit IPs, the UI shows `⚠️ IP mismatch` and keeps both IPs.
* Scores are not averaged, and there is no combined risk score.

Single-source mode keeps the original Emoji format. The meaning of the second Emoji depends on the source and mode:

* Ping0 Fast Mode: `【🟢🟡 住宅|原生】`. The first Emoji is the risk score; the second is shared users.
* IPPure Browser Mode: `【🟢🟡 住宅|原生】`. The first Emoji is the score; the second is the Bot ratio.
* IPPure API Mode: `【🟢 住宅|原生】`. There is no second Emoji because the API does not return a Bot ratio.
* `住宅 / 机房` is the **IP type**; `原生 / 广播` is the **IP source**. They are separate fields.

#### 📊 Score Legend

| Range | Emoji | Meaning | Recommendation |
| :--- | :---: | :--- | :--- |
| **0 - 10%** | ⚪ | **Excellent** | Extremely pure, suitable for all uses |
| **11 - 30%** | 🟢 | **Great** | Suitable for strict risk controls |
| **31 - 50%** | 🟡 | **Good** | Normal browsing, most services available |
| **51 - 70%** | 🟠 | **Moderate** | May be blocked by strict sites |
| **71 - 90%** | 🔴 | **Bad** | Frequent CAPTCHAs, high risk |
| **> 90%** | ⚫ | **Terrible** | Likely blocked by high-security sites |

#### 🏷️ Attribute Tags

*   **Residential**: Home broadband IP, high stealth, low probability of blocking.
*   **Data Center**: Hosted on cloud providers. Fast but often blocked by streaming.
*   **Native**: IP belongs to a local ISP. Best for streaming unlocking (Netflix, Disney+).
*   **Broadcast**: IP location does not match registration country.

## ⚙️ Configuration

See `config.yaml.example` for all available options.

## Detection and recovery

By default, Fast Mode queries Ping0 and IPPure concurrently. Dual-source checks first obtain the exit IP, then limit Ping0 to 6 seconds and IPPure to 5 seconds for its API or 40 seconds for its browser check. Each provider records success, failure, or timeout independently.

Configs with `source: ping0` or `source: ippure` use single-source mode. In Fast Mode, `fallback` retries the other provider if the primary fails; obtaining the IP and checking both providers share a 3-second limit, after which the check ends. Selecting Ping0 with Browser Mode still uses the fast check. If an IPPure single-source browser check fails or times out and `fallback` is enabled, Ping0 is tried in Fast Mode with a separate 3-second limit. IPPure does not provide shared-user counts, and API mode does not provide a Bot ratio.

Batch checks, single-node rechecks and CLI checks save the original mode and selected node before changing them. If that snapshot fails, the check does not start. Stop waits for the current check and restoration to finish before allowing another run. Restoration failures are shown and require manual recovery in Clash. Check the settings manually after a forced process termination or power loss.

## Development checks

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Tests use simulated nodes and never connect to the local Clash instance. Runtime dependencies are pinned in `requirements.lock`; regenerate it with `uv pip compile --universal --python-version 3.10 requirements.txt -o requirements.lock` after dependency changes.

## 🤝 Contributing

Contributions are welcome! Please submit a Pull Request.

## ⚠️ Disclaimer

This tool is for educational and testing purposes only. Use it responsibly and in accordance with the terms of service of the proxies and websites you access.
