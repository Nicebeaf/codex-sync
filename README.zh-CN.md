# Codex Sync

[English](README.md)

Codex Sync 是一个开源 Codex plugin，用于在 macOS 和 Windows 电脑之间安全共享用户自己创建的 Skills，并在接收设备上检查受支持的本机依赖是否就绪。它只使用**你自己选择并控制**的私有共享目录，例如 iCloud Drive、OneDrive、Dropbox、Syncthing 或 NAS。

Codex Sync 不提供云服务、共享账号或作者运营的存储空间。每个人都使用自己的私有共享目录；同步内容不会发送给作者。

Codex Sync 是独立维护的社区项目，不是 OpenAI 官方产品、服务或仓库，与 OpenAI 没有隶属、赞助或背书关系。

## 项目与隐私边界

私有 `Store` 是你通过自己的传输服务选择并控制的文件夹。Codex Sync 不托管 Store，也不运营传输服务。整个 Store（包括同步文件和运行元数据）都应按私有数据处理。

Codex Sync **不提供端到端加密（E2EE）**。Store 在同步过程中的保护程度，取决于传输服务本身的访问控制和加密能力。

凭据文件名和疑似密钥内容过滤只是尽力而为的纵深防御检查，**不能绝对保证**检测或排除每一个秘密。同步前请检查 `status`，也不要把凭据放进 Skill 目录。

## 使用条件

- macOS 或 Windows 10/11
- Python 3.9 以上版本
- 两台电脑都能访问的私有共享目录
- 支持 plugin 的 Codex 版本；已使用 Codex CLI `0.149.0-alpha.4.1` 验证

如果 `codex plugin --help` 不可用，请安装独立 Skill。

## 同步范围

新配置默认使用 `skills` 范围，只共享：

- `~/.agents/skills`
- `~/.codex/skills`，排除 `.system`

两个 Skill 根目录中的 `codex-sync` 本体，以及 `.codex-sync-*` 安装暂存/备份目录，也不会参与同步。请通过本仓库或插件 marketplace 在每台电脑上分别安装、更新 Codex Sync；私有 Store 用来共享用户的其他 Skills，不负责分发当前正在执行的同步运行时。

`~/.codex/rules` 和 `~/.codex/AGENTS.md` 属于设备级配置，默认不参与共享，也不会因为另一台电脑的更新而被替换。只有显式选择 `--scope all` 才会同步它们。

Memories 必须显式开启。选择器会尝试排除已知凭据文件名和疑似密钥内容，以及任务会话、历史记录、数据库、日志、插件缓存、浏览器状态、生成图片、自动任务、设备标识和软链接。这些是过滤器而非绝对保证；用户仍须检查 `status`，不得把凭据保存在 Skill 目录内。

## 安全机制

- 三方比较可以区分本机修改、共享目录修改和双方同时修改。
- Skills 采用双向并集：任一台电脑新增的 Skill 都会进入共享集合；删除不会传播。
- `status` 会生成可审核的 Plan ID；`sync --plan` 只执行这一份计划，计划变化就停止。
- 固定的 Store ID 可防止设备误加入另一个同名共享目录。
- Receipt 会绑定一次成功同步与共享目录清单，另一台电脑可据此确认预期更新已经可见。
- `sync-now` 自动寻找上一台电脑的最新 Receipt、验证共享清单并完成同步，不需要手工复制 Plan ID 或 Receipt。
- `sync-now` 发现冲突时会在改动所选文件之前停止，双方现有版本保持原样。
- 依赖状态与计划均为只读；本机安装需要另一份精确的 Dependency Plan ID，并在每个受支持项目安装后重新验证。
- 冲突文件会保存两个版本，不会自动覆盖。
- 替换文件前自动备份。
- Snapshot history 和 restore 提供可检查的恢复入口。
- 删除操作不会同步到另一台机器。
- 共享目录锁会阻止同一存储上的重叠写入。
- 云盘同步可能存在延迟，两台电脑仍应串行执行同步。
- 单文件上限 20 MiB；每一侧单次最多 10,000 个文件、总计 512 MiB。

## 作为 Plugin 安装

从公开 GitHub marketplace 安装：

```bash
codex plugin marketplace add Nicebeaf/codex-sync
```

在 ChatGPT 桌面版打开 Plugins，选择 **Codex Sync** marketplace，安装 **Codex Sync**，然后新建任务。Codex CLI 用户可以运行 `/plugins` 安装，随后新建会话。

GitHub marketplace 能让任何人公开安装，但不会自动进入通用 Plugins Directory；进入通用目录还需要单独完成[插件提交审核](https://developers.openai.com/plugins/deploy/submission)。

发布前测试本地仓库：

```bash
git clone https://github.com/Nicebeaf/codex-sync.git
codex plugin marketplace add ./codex-sync
```

## 只安装独立 Skill

运行仓库根目录的安装脚本。它会把独立 Skill 复制到 `~/.codex/skills/codex-sync`，删除克隆目录后仍可使用：

```bash
sh install.sh
```

Windows PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

如果 `$codex-sync` 没有立即出现，请重启 Codex。

每台要使用 Codex Sync 的电脑都需要分别运行安装流程；同步 Store 会主动排除 Codex Sync 运行时本体。

## 日常同步只需三步

完成一次初始化后，以后每次换电脑只需要：

1. 在电脑 A 的 Codex 中说：`使用 codex-sync 快速同步`。
2. 等待 iCloud、OneDrive、Dropbox、Syncthing 或 NAS 显示同步完成。
3. 在电脑 B 的 Codex 中说：`使用 codex-sync 快速同步`。

对应的直接命令：

macOS：

```bash
SYNC="$HOME/.codex/skills/codex-sync/scripts/codex_sync.py"
python3 "$SYNC" sync-now
```

Windows PowerShell：

```powershell
$SYNC = "$HOME\.codex\skills\codex-sync\scripts\codex_sync.py"
py $SYNC sync-now
```

`sync-now` 会自动读取最近一次成功交接的 Receipt。没有冲突时直接完成并产生下一张 Receipt；有冲突时停止，不改动所选文件，然后再进行一次明确的冲突选择。

## 每次快速同步后的依赖就绪

成功的 `sync-now` 只复制 Skill 文件。在接收设备上使用同步过来的 Skill 前，先检查本机依赖。依赖管理器会扫描 `~/.agents/skills` 与 `~/.codex/skills`（排除 `.system`），只读取各 Skill 的 `dependencies.json`，并静态识别常见 Python import；扫描和计划阶段不会执行 `SKILL.md`、URL 或脚本。

使用上面的三步 Codex 口令时，Codex 会在 `sync-now` 后接着运行 `deps status`，不会增加新的人工传输步骤。依赖齐全就直接结束；发现缺项时，Codex 只展示一次精确计划并询问一次是否安装。下面四条是对应的直接 CLI 命令：`status` 是必须先做的检查；`plan` 会打印一份新的 Dependency Plan ID、每条支持的安装命令、必需阻塞项、可选缺项和旧 Skill 提示。只有用户已经看见并明确批准这份精确 Plan ID 和命令列表后，才可运行 `install`。`verify` 只重新执行本机依赖探针，**不是**完整的 Skill 业务流程测试。

```bash
# macOS
SYNC="$HOME/.codex/skills/codex-sync/scripts/codex_sync.py"
python3 "$SYNC" deps status
python3 "$SYNC" deps plan
python3 "$SYNC" deps install --plan "<DEPENDENCY_PLAN_ID>"
python3 "$SYNC" deps verify
```

```powershell
# Windows PowerShell
$SYNC = "$HOME\.codex\skills\codex-sync\scripts\codex_sync.py"
py $SYNC deps status
py $SYNC deps plan
py $SYNC deps install --plan "<DEPENDENCY_PLAN_ID>"
py $SYNC deps verify
```

安装只作用于当前设备：不会写入私有 Store、Receipt 或任何被同步的 Skill 内容。包管理器安装不是事务性的，可能要求系统权限，或要求接受软件源/EULA。manifest、catalog、支持的 manager 和迁移方式见[依赖参考](plugins/codex-sync/skills/codex-sync/references/dependencies.md)。

没有 manifest 的旧 Skill 会标记为 `legacy_unmanaged`；不会猜测文档里写的依赖。未知或未受管的 Python import、无效 manifest、不支持的平台或需要手动配置的依赖，结果只能是 `partial` 或 `blocked`；在声称已就绪前，应由 Skill 作者补齐说明或迁移。

## 首次连接两台电脑

可以直接让 Codex 使用本 Skill，也可以运行仓库内脚本。下列示例中的变量只用于简化命令和传递交接值。

### 1. 第一台电脑创建共享目录

`create` 只接受全新或空的私有目录。保存命令打印的 `STORE_ID`，第二台电脑必须用它核对共享目录身份。

```bash
SYNC=plugins/codex-sync/skills/codex-sync/scripts/codex_sync.py
python3 "$SYNC" create --store "STORE_PATH" --device mac --scope skills
python3 "$SYNC" doctor
```

### 2. 审核精确计划后再同步

终端人工查看可使用普通输出；Codex 或程序读取应使用 JSON。`sync` 必须收到已审核的 Plan ID；审核后只要任何内容发生变化，它就拒绝执行新计划。

```bash
python3 "$SYNC" status
python3 "$SYNC" status --json
python3 "$SYNC" sync --plan "<PLAN_ID>"
```

成功的 `sync` 会打印 `RECEIPT`。请保存它：Receipt 代表已经完成的共享目录清单，不只是一个时间戳。

### 3. 第二台电脑加入

等待私有传输完成，再使用准确的 Store ID 加入。第二台必须使用不同设备名，并在审核与同步时要求看到第一台的 Receipt。

```bash
SYNC=plugins/codex-sync/skills/codex-sync/scripts/codex_sync.py
python3 "$SYNC" join \
  --store "STORE_PATH" \
  --device windows-pc \
  --expect-store-id "<STORE_ID>" \
  --scope skills
python3 "$SYNC" doctor
python3 "$SYNC" devices
python3 "$SYNC" status --json --expect "<RECEIPT>"
python3 "$SYNC" sync --plan "<PLAN_ID>" --expect "<RECEIPT>"
```

第二台同步成功后会打印下一次交接使用的 Receipt。

初始化完成后改用上面的 `sync-now` 三步流程。Receipt 能证明预期清单已经可见，但不能让存在传播延迟的云盘支持并发同步。

### 已有 0.2 配置切换为只共享 Skills

0.2 创建的配置会保留旧的 `all` 范围，避免升级时静默改变行为。在**两台电脑**更新到 0.4 或更高版本后分别运行一次：

```bash
python3 "$SYNC" configure --scope skills
```

切换范围只改变后续同步清单，不会删除本机或共享目录里已有的 rules、`AGENTS.md` 或 Skills。下一次交接必须由两台电脑使用相同范围；Receipt 会拒绝范围不一致的同步。

GitHub/Marketplace 是 Codex Sync 这个 Skill 的安装与更新来源；你自己的私有 Store 才是两台电脑之间共享自定义 Skills 的位置。

### 4. 查看并恢复 Snapshot

```bash
python3 "$SYNC" snapshot
python3 "$SYNC" history
python3 "$SYNC" restore --id "<SNAPSHOT_ID>" --dry-run
python3 "$SYNC" restore --id "<SNAPSHOT_ID>" --plan "<RESTORE_PLAN_ID>"
```

Snapshot 只保存在本机 `~/.codex-sync/snapshots`，不会写入共享 Store。预览会打印 Restore Plan ID；目标文件随后发生变化时，正式恢复会拒绝覆盖。恢复前还会先保留当前本地状态，恢复过程不要求共享目录可用。

## 命令模型

- `create --scope skills`：创建全新的共享 Store，并默认只共享 Skills。
- `join --expect-store-id --scope skills`：仅在 Store 身份和同步范围一致时加入已有 Store。
- `configure --scope skills|all`：切换只共享 Skills 或兼容旧版全范围；不会删除文件。
- `status` / `status --json`：只读查看当前计划。
- `sync --plan`：只执行已审核的精确计划。
- `sync-now`：自动验证最新 Receipt 并完成无冲突同步；这是日常推荐命令。
- 成功的 `sync --plan` 或 `sync-now` 会打印下一台电脑使用的 Receipt。
- `devices`：查看该 Store 登记的 Codex Sync 设备。
- `snapshot` / `history` / `restore`：保存、查看并恢复本地同步状态。
- `resolve`：双方版本均已保留后，明确选择一个冲突版本。

## 与相关工具的定位差异

截至 2026 年 8 月，以下项目解决了相邻问题。Codex Sync 刻意保持窄范围：默认通过用户自己的私有传输，在多台电脑间双向共享 Skills，并检查计划、Store 身份、云盘交接、冲突与恢复。

| 项目 | 公开定位 | Codex Sync 的差异 |
| --- | --- | --- |
| [skills-manager](https://github.com/xingkongliang/skills-manager) | 桌面端 Skill 库、广泛 Agent 支持、私有 Git 备份与多设备 Skills 同步 | Codex Sync 不做 Skill 库或 GUI；默认只共享 Codex Skills，rules 与 `AGENTS.md` 仅在显式 `all` 范围下参与。 |
| [skillshare](https://github.com/runkids/skillshare) | 通过 Git 为多种 AI 工具管理 Skills 与其他资源，并提供审计 | Codex Sync 专注于现有私有传输中的 Codex 双向状态，并拒绝未经审核的计划。 |
| [skills-hub](https://github.com/qufei1993/skills-hub) | 桌面端安装、整理、更新和部署多工具 Skills | Codex Sync 关注跨电脑安全与恢复，不做发现和批量 Skill 管理。 |
| [vsync](https://github.com/nicepkg/vsync) | 从指定真源向其他工具做单向配置转换 | Codex Sync 处理多台电脑各自发生的修改，冲突时保留双方，而不是指定一个工具覆盖其他工具。 |
| [ai-config-sync-manager](https://github.com/slash9494/ai-config-sync-manager) | 在同一台电脑上转换 Claude Code 与 Codex 配置 | Codex Sync 不转换宿主格式，而是验证电脑之间的私有交接。 |

以上只是公开定位对比，不表示某个项目在所有场景都更好。主要需求是通用 Skill 管理或跨工具转换时，应优先选择对应工具。

## 开发和测试

需要 macOS 或 Windows 10/11，以及 Python 3.9 以上版本；运行时只使用 Python 标准库。

```bash
python3 -m py_compile plugins/codex-sync/skills/codex-sync/scripts/codex_sync.py
python3 tests/test_codex_sync.py
python3 tests/test_dependencies.py
python3 tests/test_package.py
```

## 发布到自己的 GitHub

```bash
git init
git add .
git commit -m "Initial open-source release"
gh repo create codex-sync --public --source . --remote origin --push
```

发布前检查仓库，禁止加入真实 Codex 数据、共享目录内容、`auth.json`、`config.toml`、会话、数据库或本地备份。

安全说明见 [SECURITY.md](SECURITY.md)，许可证为 [MIT License](LICENSE)。
