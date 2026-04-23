# Xirang 0.2.0a1 — local-first self-evolving agent public alpha

> 息壤 / Xirang：一个会记得、会长大、会换人格、会积累技能基因的本地 agent。

`0.2.0a1` 是 Xirang 的第一次公开 Alpha 版本。

它不是一次性聊天壳，也不是只会调工具的脚本封装，而是一个更接近“本地个人工作台”的 agent：

- 能保存连续性记忆，接回昨天的话题
- 能蒸馏人格、生成孩子人格、形成家族谱系
- 能把成功路径沉淀成可继承的本地 skill genes
- 能导出脱敏后的 genome proposal，而不是上传你的完整私有状态
- 能在显式授权下进行桌面 co-pilot
- 能做本地自动化、webhook 接入和 benchmark 自检

## Highlights

### 1. Local Memory That Actually Carries Context

Xirang 现在具备分层本地记忆：

- Prelude
- Recurrent
- Coda
- Archive

这让它能更自然地理解：

- “继续上次”
- “昨天我们聊到哪了”
- “把前面那个方案接着做完”

## 2. Persona Families and Inherited Skill Genes

人格不再只是 prompt 风格，而是可演化的本地实体：

- distill
- refine
- fork
- birth
- mutate
- mate

孩子人格可以优先使用自己的 skilllet，也可以继承父代、母代、祖先和共享基因。

## 3. Sanitized Genome Proposal Flow

Xirang 不鼓励上传完整孩子、完整对话、私人记忆或本地敏感信息。

它导出的 proposal 只包含适合回流的脱敏能力片段，例如：

- 任务指纹
- 工具链
- 参数键结构
- 成功/失败统计
- 成熟度和风险等级

## 4. Real-World Engineering Breadth

这次 Alpha 不再只强调理念，也补上了更实用的工程面：

- `http_request`
- `json_query`
- `sqlite_query`
- `csv_query`
- `dispatch_subagent_batch`
- cron-like automation
- webhook ingestion
- benchmark harness
- risk-aware execution modes

## 5. Explicit Desktop Co-Pilot

Xirang 可以在显式授权下进行本地桌面协作，包括：

- screenshot
- move
- click
- double click
- drag
- scroll
- type text
- hotkey

默认关闭，需要显式开启；它不是后台监控工具，也不会偷偷记录键盘输入。

## Validation

Release prep validation passed:

- `python3 -m py_compile xirang/*.py scripts/*.py benchmarks/run_bench.py`
- `python3 tests/test_smoke.py`
- `PYTHONPATH=. XIRANG_HOME="$(mktemp -d)" XIRANG_PROVIDER=ollama python3 -m xirang --bench-dry-run`
- `python3 -m build`
- `python3 -m twine check dist/*`

Smoke result:

```text
All 43 tests passed.
```

## Known Limits

This is a **public alpha**, not a stable GA release.

Current limits:

- not a packaged consumer desktop app yet
- not a full OpenClaw-style multi-channel gateway / daemon platform yet
- desktop control depends on optional dependencies and OS GUI permissions
- benchmark coverage is useful but still small
- browser / desktop real-world templates can grow further

## Install

```bash
pip install xirang
```

Or from source:

```bash
git clone <your-repo-url>
cd xirang
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
xirang --setup openrouter
xirang --doctor
```

Optional desktop support:

```bash
pip install ".[desktop]"
XIRANG_DESKTOP_ENABLE=1 xirang
```

## Recommended Links

- Changelog: `CHANGELOG.md`
- Release notes: `docs/RELEASE_NOTES_0.2.0a1.md`
- Publishing guide: `docs/PUBLISHING.md`
- Security policy: `SECURITY.md`
- Contributing guide: `CONTRIBUTING.md`

