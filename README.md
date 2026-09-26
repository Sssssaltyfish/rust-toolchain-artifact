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
- 修改同步脚本、测试或工作流并推送到默认分支 `master` 时，检查 stable。
- Actions → **Sync Rust toolchains** → **Run workflow** 可选择 `stable`、`beta`、`nightly` 或 `all`。`force` 可强制重新上传。
- 已有相同频道、版本、日期、manifest 的有效 artifact 时跳过；剩余保存期不超过 7 天时重新上传，以使长期不变的 stable 仍有可用下载。
- 每份 artifact 保存 **30 天**，不创建 GitHub Release。仓库设置可能进一步限制保存期。公开仓库连续 60 天没有仓库活动时，GitHub 可能禁用定时工作流，需要在 Actions 中重新启用。

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
python3 scripts/sync.py --channel stable --output-dir dist
```

工作流仅授予 `contents: read` 和 `actions: read`，使用内置 `GITHUB_TOKEN` 查询已存在的 artifact，无需额外 secret。不同频道独立运行、独立并发控制，一条频道失败不会取消其他频道。
