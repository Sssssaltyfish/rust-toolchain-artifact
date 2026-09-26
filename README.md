# Rust toolchain artifacts

每日同步 Rust 官方构建的工具链，并发布为 GitHub Actions artifact。默认平台为 **Linux x86_64（`x86_64-unknown-linux-gnu`）**。

[运行记录与下载](https://github.com/Sssssaltyfish/rust-toolchain-artifact/actions/workflows/sync.yml)

## 频道和最新版本

分别读取官方的 `channel-rust-stable.toml`、`channel-rust-beta.toml`、`channel-rust-nightly.toml`，以各自 manifest 为准。不使用 GitHub Releases 的统一 `latest`，不混用频道，也不在最新版本缺少完整工具链时自动回退到旧版。

| 频道 | 官方 manifest |
| --- | --- |
| stable | https://static.rust-lang.org/dist/channel-rust-stable.toml |
| beta | https://static.rust-lang.org/dist/channel-rust-beta.toml |
| nightly | https://static.rust-lang.org/dist/channel-rust-nightly.toml |

- 每天 **07:23 UTC / 北京时间 15:23** 检查所有频道。GitHub 定时任务可能延迟。
- 修改同步脚本、测试或工作流并推送到默认分支 `master` 时，强制验证并重新上传 stable，让代码和保存策略的修改立即生效。
- Actions → **Sync Rust toolchains** → **Run workflow** 可选择 `stable`、`beta`、`nightly` 或 `all`。`force` 可强制重新上传。
- 已有相同频道、版本、日期、manifest 的有效 artifact 时跳过；剩余保存期不超过 7 天时重新上传，以使长期不变的 stable 仍有可用下载。
- **每个频道、每个平台只保留最近两个不同的发行快照，每份最长保存 90 天**（公开仓库允许的上限）。较旧版本可能因数量上限而提前删除；nightly 通常只留最近两天的成功快照。
- 只有新产物通过校验、安装测试并成功上传后才清理旧产物；同版本的重复上传只留最新一份。清理只作用于本项目该频道和平台的命名空间，保留最新产物与一个回退快照。
- 手动指定版本使用独立的 `rust-pinned-` 前缀，每个频道和平台保留最近请求的 **一份**，最长 90 天；不会挤掉自动跟踪的最新版本和回退快照，也不会被每日自动同步刷新。
- 不创建 GitHub Release。仓库设置可能进一步限制保存期；保存期修改只影响新上传的 artifact。公开仓库连续 60 天没有仓库活动时，GitHub 可能禁用定时工作流，需要在 Actions 中重新启用。

## 存储与仓库可见性

仓库保持公开：工具链本身来自公开的 Rust 官方发布，工作流使用标准 GitHub 托管 Ubuntu runner。公开仓库适用 GitHub 的免费 Actions 使用规则；不要把它理解成永久、无限制的归档服务。

首次 stable 1.98.1 artifact 实测为 203,460,255 字节（约 194 MiB）。以此估算，三个频道各保留两个自动快照，常态总量约 1.14 GiB；若三个频道也各有一份手动指定版本，总共九份约 1.71 GiB。上传替换期间会暂时增加，实际大小随版本变化。若 nightly 每天一份、全部留 90 天，仅 nightly 就约 17 GiB，因此同时限制份数与保存期限。

私有仓库虽然最长可留 400 天，但不会因此获得更多免费存储：GitHub Free 的 artifact 额度为 500 MB，Pro 为 1 GB，Team 为 2 GB，并与 GitHub Packages 共用；超额费用按存储量与时间累计。仅三个频道各一份完整工具链就可能超过 Free 额度，所以本项目不为了延长保存期改成私有仓库。

规则核对日期：2026-09-26。参考 [Actions 计费](https://docs.github.com/en/billing/concepts/product-billing/github-actions)、[保存期限](https://docs.github.com/en/organizations/managing-organization-settings/configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-organization)。具体账单、剩余额度和预算以仓库所有者的 Billing 页面为准。

## 手动指定版本

在 [工作流页面](https://github.com/Sssssaltyfish/rust-toolchain-artifact/actions/workflows/sync.yml) 点击 **Run workflow**，选好 `channel` 并填写可选的 `version`：

| channel | version | 同步目标 |
| --- | --- | --- |
| stable | 留空 | 最新 stable |
| stable | `1.98.1` | 指定 stable 发行版本 |
| stable | `2026-09-03` | 指定 stable 发行日期 |
| beta | `beta-2026-09-20` | 当日 beta 快照 |
| nightly | `nightly-2026-09-26` | 当日 nightly 快照 |
| nightly | `2026-09-26` | 同上，可省略频道前缀 |
| all | 留空 | 三个频道各自最新版本 |

指定日期必须确实存在该频道的官方 manifest；若不存在则失败，不回退到相邻日期。beta/nightly 用日期固定快照，不接受仅含 `1.99.0-beta.7` 或 `1.100.0-nightly` 的不完整快照选择器。`all` 不能与非空 `version` 组合，频道与版本前缀必须一致。

指定版本会使用固定版本或固定日期的官方 manifest，仍执行相同的校验和安装测试，`metadata.json` 会记录请求值与实际版本。`force=false` 时可复用已存在的相同 artifact，运行摘要提供下载链接。

## 产物内容与校验

artifact 命名：`rust-<channel>-<version>-<date>-<target>-<manifest SHA-256 前12位>`。

每个 artifact 包含：

- 官方原始完整安装包 `.tar.xz`，保留内部权限和目录结构。
- 对应频道的完整 TOML manifest。
- `metadata.json`：频道、版本、日期、平台、官方来源和校验值。
- `SHA256SUMS`：上述文件的 SHA-256。

工作流先校验官方 manifest 的 SHA-256，再从 manifest 指定的固定日期 URL 下载完整工具链，流式校验安装包 SHA-256。上传前还会安装其中的 rustc、cargo、标准库，核对 `rustc --version` 与 manifest 完全一致，并用 Cargo 离线编译和运行示例程序。校验或测试失败则不发布。

从成功运行的 **Artifacts** 区下载并解压 ZIP。若最新检查跳过了上传，运行摘要会链接到已有 artifact。GitHub 要求登录后下载 Actions artifact。

在解压后的 artifact 目录中运行：

```bash
sha256sum --check SHA256SUMS
archive=$(python3 -c 'import json; print(json.load(open("metadata.json"))["archive"])')
tar -xJf "$archive"
cd "${archive%.tar.xz}"
./install.sh --prefix="$HOME/.local/rust-official" --disable-ldconfig
export PATH="$HOME/.local/rust-official/bin:$PATH"
rustc --version
cargo --version
```

安装包是官方完整工具链，组件和许可证以包内内容为准；运行它仍需目标 Linux 系统满足 Rust 的原生依赖要求。

## 本地验证

需要 Python 3.11+，无第三方 Python 依赖：

```bash
python3 -m unittest discover -s tests -v
python3 scripts/sync.py --channel stable --resolve-only
python3 scripts/sync.py --channel stable --version 1.98.1 --resolve-only
python3 scripts/sync.py --channel nightly --version nightly-2026-09-26 --resolve-only
python3 scripts/sync.py --channel stable --output-dir dist
```

测试任务使用只读权限；同步任务授予 `contents: read` 和 `actions: write`，使用内置 `GITHUB_TOKEN` 查询并清理旧 artifact，无需额外 secret。不同频道独立运行、独立并发控制，一条频道失败不会取消其他频道。
