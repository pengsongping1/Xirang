# Xirang · 息壤

> 一个会记得、会长大、会换人格、会把经验变成“技能基因”的本地 agent。

**当前版本：`0.2.0a1` Public Alpha / Public Preview。**  
适合发布给开发者和早期用户试用；它已经能做真实本地任务，但还不是免配置、面向大众的稳定桌面助手。

Xirang（息壤）是一个命令行里的个人 agent。它不是一次性聊天窗口，也不是只会执行工具的脚本壳。你每天打开它、聊几句、让它做几件事，它会保存你们上次说到哪，把连续性记忆带回上下文，把成功路径长成本地技能，还能让不同人格组成家族、继承技能、继续进化。

最重要的是：**它默认本地生长，不自动上传。**  
你的记忆、人格、家谱、会话和技能都在 `~/.xirang/`，能读、能改、能删、能备份。

```bash
xirang
▸ 继续昨天那个基因回流设计
◆ 我记得：我们决定不上传整个孩子，只回流脱敏后的技能基因片段。接下来可以做成熟度评分和离线合并流程。
```

---

## 为什么它新鲜

大多数 agent 是“会话”。Xirang 更像一块会生长的土：

- **会续命**：默认接回 `last` 会话；每轮成功对话都会写入 daily journal，几天后仍可召回“上次说到哪了”的线索。
- **会换脑**：一句话蒸馏人格，随时切换表达方式、工作风格和思考视角。
- **会生孩子**：人格可以 birth / mutate / mate，形成家族树。
- **会遗传技能**：孩子优先用自己的 skill gene，找不到就向父代、母代、祖先“呼救”。
- **会自学变快**：成功工具轨迹会变成 recipe 和 skilllet；相似任务下次不从零开始。
- **会共操桌面**：显式开启 `/copilot` 后，可以截图、观察鼠标位置、移动、点击、输入、热键，像一个坐在旁边的协作者。
- **会安全回流**：用户贡献的是脱敏后的 genome proposal，不是完整对话、隐私记忆或整个人格。

一句话：**Xirang 把“陪伴感”和“能力进化”放在一起，但把安全边界留在本地。**

---

## 一分钟开始

```bash
cd xirang
./one_minute_install.sh
source .venv/bin/activate
xirang --setup openrouter
xirang --doctor
xirang --doctor-live
xirang --bench-dry-run
```

如果你已经有 key：

```bash
./one_minute_install.sh openrouter YOUR_API_KEY
```

推荐从 `openrouter` 开始：配置简单，默认模型是 `qwen/qwen3-coder:free`。也可以用本地模型：

```bash
xirang --setup ollama
xirang --provider ollama
```

支持的 provider：

- `anthropic`
- `openai`
- `deepseek`
- `ollama`
- `lmstudio`
- `openrouter`
- `groq`
- `together`
- `fireworks`
- `openai_compat`

常用启动方式：

```bash
xirang                                  # 打开 REPL，默认续上 last
xirang -p "hello"                       # 跑一条就走
xirang --fresh                          # 不续上次，从零开始
xirang --resume morning-notes           # 续指定会话
xirang --profile deep                   # 更深的输出/工具迭代预算
```

---

## 核心体验

### 1. 记得住上次

Xirang 有两层连续性：

- `sessions/`：完整会话存档，默认自动续 `last`
- `memory/recurrent/`：每日对话 journal + 滚动摘要，用来回答“昨天 / 上次 / 继续”

```text
/memory recent
/memory search 上次我们聊到哪里了
/session list
/session load monday-morning
```

你可以聊一天，然后第二天直接打开：

```bash
xirang
▸ 昨天最后那个设计继续
```

它会优先把最近的 recurrent / coda 记忆注入上下文，而不是只靠当前窗口历史。

### 2. 一句话换人格

```bash
xirang --distill "像费曼给本科生讲课，先画图再列公式"
xirang --distill "像查理·芒格，多模型、反向思考、重视激励"
xirang --distill "扮演一位只做 code review 的资深 Rust 工程师，话少"
```

人格保存在：

```text
~/.xirang/personas/<slug>.md
```

它是普通 Markdown，可手改、可分享、可删除。

常用命令：

```text
/persona use feynman
/persona mode teacher
/persona refine 更像产品战略顾问，少一点抒情，多一点判断
/persona fork feynman :: 保留解释力，但更像 CTO
/persona mode-add debate :: 先辩证拆两边，再给结论
```

人格主要影响**表达层和工作风格**，不故意削弱推理和工具能力。

### 3. Agent 家族：出生、变异、恋爱

Xirang 的人格可以形成家谱：

```text
/persona birth 会写代码、很温柔、但关键时刻很果断的孩子
/persona mutate 更叛逆，更会探索未知工具
/persona mate feynman :: 生一个既会讲清楚原理，又会做工程判断的孩子
```

查看家族：

```text
/persona lineage
/persona children
/persona family
```

每个孩子都会记录：

- `parent_slug`
- `other_parent_slug`
- `family_name`
- `refinement_notes`

这不是为了噱头，而是为了让能力可以沿着人格谱系沉淀：不同性格的 agent 可以长出不同技能，后代可以继承最近祖先的经验。

### 4. 技能基因：不用外部 skill，也能自己变强

Xirang 完成工具任务后，会记录两种经验：

- `recipe`：轻量工具路径，小抄式复用
- `skilllet`：更完整的本地技能基因，带 owner、schema、成功次数和工具链

```text
/recipes
/skilllets
/skilllets family
```

如果当前激活了人格，skilllet 会写到这个人格名下。孩子遇到任务时会按顺序寻找：

1. 自己的技能
2. 父代技能
3. 母代技能
4. 更远祖先技能
5. 共享技能

这就是 Xirang 的“技能遗传”。

### 5. 基因回流：用户促进进化，但不上传隐私

Xirang 不鼓励上传整个孩子、完整会话或私人记忆。  
真正适合回流的是：**脱敏后的技能基因片段**。

用户本地长期使用后，可以导出 genome proposal：

```text
/genome status
/genome propose
/genome propose child
/genome propose child :: exports/child-genome.xirang.json
/genome review exports/child-genome.xirang.json
```

proposal 会保留：

- 任务指纹
- 工具链
- 参数键结构
- 成功/失败次数
- 成熟度评分
- 风险等级

proposal 不保留：

- 原始完整对话
- 私人记忆
- API key
- 本地敏感路径
- 完整人格家谱

维护者可以离线合并：

```bash
python3 scripts/merge_genome_proposals.py contributions/ --out-dir community/reviewed
```

输出：

```text
community/reviewed/
├── community_genome/
└── genome_pack.json
```

安全规则：

- 只接受 Xirang 已知工具名
- 自动去掉 `source_samples`
- 脱敏明显 secret / Bearer token / 本地路径
- 重写危险 slug，阻断 `../` 路径投毒
- 高风险工具链需要人工 sandbox review

### 6. 人机共操：不只会写代码，也能坐到“键盘旁边”

有些工作不适合纯 CLI：写 `docx`、点网页、操作桌面软件、复制粘贴、保存文件、在已有窗口里继续协作。Xirang 现在有一个可选 `desktop` 工具，让 agent 能在你明确授权后操作本机桌面。

启用方式（二选一）：

```bash
pip install ".[desktop]"
XIRANG_DESKTOP_ENABLE=1 xirang
```

或者在 REPL 里显式开始本次共操会话：

```text
/copilot start 一起编辑当前打开的 docx
/copilot status
/copilot observe 3
/copilot invite 帮我加入当前写作任务，先观察窗口，再等我下一步
/copilot stop
```

能力范围：

- `status`：查看是否启用、屏幕尺寸、鼠标位置
- `screenshot`：截屏到本地文件
- `move` / `click` / `double_click` / `drag` / `scroll`：移动鼠标和点击
- `type_text` / `press` / `hotkey`：输入文字、按键、组合键
- `watch`：短时间、显式、截图式观察屏幕变化和鼠标位置

安全边界：

- 默认关闭，需要 `XIRANG_DESKTOP_ENABLE=1`
- `/copilot start` 只开启当前 Xirang 进程的显式会话
- 没有后台键盘监听器，不偷录用户输入
- `watch` 有时间和帧数上限，只在明确调用时截图
- `plan` 模式会阻止 desktop；`ask` 模式会要求确认

这让 Xirang 可以进入一种更自然的协作方式：用户继续用鼠标键盘工作，agent 通过截图和位置理解当前状态；需要时，它可以接过鼠标做一小步，然后把控制权还给用户。

---

## 工程广度补强

为了让 Xirang 不只“有想法”，还真能解决实际问题，现在默认工具链已经覆盖几类高频工程任务：

- `http_request`：直接调 REST API、Webhook、健康检查、抓 JSON，不必每次都手写 `curl`
- `json_query`：查看接口返回、提取嵌套字段、列键名、排查 JSON 结构
- `sqlite_query`：只读查看本地 SQLite 数据库，适合桌面应用缓存、日志库、导出库
- `csv_query`：总结 CSV/TSV、看表头、按列筛选，适合运营报表和导出数据

这意味着它现在更适合处理这些真实工作：

- 调第三方 API，拿回 JSON 后继续解析
- 看本地 App 数据库，查用户、消息、埋点、缓存
- 处理 CSV 报表、筛选运营数据、快速核对结果
- 在 CLI、浏览器、桌面三层之间来回切换完成任务

失败退出码也做了修正：

- `xirang -p "..."` 如果调用模型失败，会返回非零退出码
- `xirang --doctor-live` 如果连通性失败，也会返回非零退出码

这对 shell 脚本、CI、守护进程和自动恢复都更友好。

---

## Xirang 的本地目录

```text
~/.xirang/
├── personas/           # 人格、孩子、家谱，每个一个 .md
├── memory/             # 长期记忆，含 daily journal 和 MEMORY.md 索引
├── sessions/           # 可恢复会话，每份一个 .json
├── recipes.jsonl       # 工具路径小抄
├── skilllets/          # 本地技能基因，带 owner，可继承
├── exports/            # family bundle / genome proposal
├── audit/              # 工具执行审计
└── .history            # REPL 历史
```

所有状态都是本地文件。你不需要相信黑盒数据库。

---

## 安全边界

Xirang 默认是本机个人 agent，所以它可以读写文件、跑命令、调用工具。你可以切换执行模式：

```bash
xirang --mode plan
/mode ask
/audit 20
```

模式说明：

- `default` / `auto`：直接执行工具，适合个人本机使用
- `safe`：只允许低风险工具，适合先看数据、查 JSON、看 SQLite / CSV
- `plan`：只读模式，只允许读文件、grep、glob
- `ask`：低风险工具自动放行，中高风险确认；非 TTY 默认拒绝

`xirang --doctor` 会检查：

- provider / model / key
- base URL
- API / LLM catalog
- local genome 数量
- 高风险基因数量

`xirang --doctor-live` 会真的向 provider 发一条“你好”，验证 key 和服务是否在线。

失败退出码：

- `xirang -p "..."` 失败时返回非零退出码
- `xirang --doctor-live` 失败时返回非零退出码
- `xirang --bench` 只要有 benchmark 失败也会返回非零退出码

贡献和安全规则见 `CONTRIBUTING.md` 与 `SECURITY.md`。
发布说明见 `CHANGELOG.md` 与 `docs/RELEASE_NOTES_0.2.0a1.md`。

---

## 浏览器和真实网页

默认工具已经能处理大多数终端任务。遇到 JS 页面、点击、表单、截图时，可以安装 Playwright：

```bash
pip install playwright
playwright install chromium
```

之后 Xirang 的系统提示会引导它按任务选择：

- `bash curl`：静态页面
- `write_and_run python`：解析、转换、批处理
- `browser`：需要点击/填表/截图/抽取渲染后文本

实际效果仍取决于当前 LLM 和 provider 是否正常在线；`xirang --doctor-live` 可以先做一次真实连通性检查。

如果你要操作的不只是网页，而是整个桌面应用，用 `desktop` 工具；它和 `browser` 是两层能力：

- `browser`：网页内导航、点击、填表、抽取文本
- `desktop`：系统桌面级鼠标、键盘、截图、短时观察

---

## 常用命令速查

### 启动

```bash
xirang
xirang -p "列出这个仓库里超过 500 行的 Python 文件"
xirang --fresh
xirang --resume last
xirang --profile fast
xirang --profile deep
```

### Provider

```text
/llm
/llm presets
/llm use openrouter
/llm provider ollama
/llm model gpt-4o-mini
/brain deep
```

### 人格

```text
/persona distill <一句话>
/persona use <名字>
/persona show [名字]
/persona refine <描述>
/persona fork <描述>
/persona birth <描述>
/persona mutate <描述>
/persona mate <名字> :: <孩子描述>
/persona family [名字]
/persona export [名字]
/persona import <路径>
```

### 记忆与会话

```text
/memory add <名字> :: <内容>
/memory recent [N]
/memory search <查询>
/memory status
/session save [名字]
/session load <名字>
/session list
/session new
```

### 技能与基因

```text
/recipes
/skilllets
/skilllets family
/genome status [owner]
/genome propose [owner]
/genome review <路径>
```

### 数据与接口

这些一般由 agent 自动调用，但你也可以直接描述任务让它使用：

- HTTP / webhook / API：优先 `http_request`
- JSON 响应解析：优先 `json_query`
- SQLite 本地库：优先 `sqlite_query`
- CSV / TSV 导出：优先 `csv_query`

### 自动化与 Benchmark

```text
/cron add heartbeat :: @every 5m :: 输出一行当前状态
/cron list
/cron run heartbeat
/webhook add alerts :: 收到告警后总结事件并给出下一步
/webhook list
/bench dry-run
```

```bash
xirang --scheduler
xirang --serve-webhooks --webhook-host 127.0.0.1 --webhook-port 8765
xirang --run-due-jobs
xirang --bench
xirang --bench-dry-run
python3 benchmarks/run_bench.py --dry-run
```

支持的调度格式：

- `@every 30s`
- `@every 5m`
- `@hourly`
- `@daily`
- `@weekly`
- `@once 2026-04-24 09:30`

### 桌面共操

```bash
pip install ".[desktop]"
XIRANG_DESKTOP_ENABLE=1 xirang
```

```text
/copilot start 一起写这个文档
/copilot observe 5
/copilot invite 加入当前窗口，先判断我在编辑什么
让我们一起编辑这个文档。先截图看看当前窗口，然后把标题选中改成“Xirang 发布计划”。
观察 5 秒我正在怎么操作，然后接着帮我点保存。
/copilot stop
```

### 安全、审计、成本

```text
/mode safe
/mode plan
/mode ask
/audit 20
/cost
/clear
/exit
```

---

## Python 包结构

```text
xirang/
├── agent.py      # 主循环：记忆 → recipe/skilllet → LLM → 工具 → 保存
├── cli.py        # REPL + slash 命令
├── config.py     # provider、profile、home、迁移
├── llm.py        # Anthropic + OpenAI-compatible
├── tools.py      # 原子工具注册表
├── browser.py    # 可选 Playwright 浏览器工具
├── desktop.py    # 可选桌面鼠标/键盘/截图共操工具
├── copilot.py    # 显式人机共操会话：start / observe / invite / stop
├── permissions.py # default/safe/plan/ask 风险感知执行模式
├── audit.py      # 工具执行审计
├── persona.py    # 人格蒸馏、家族、出生、变异、双亲
├── skilllet.py   # 本地技能基因、继承、匹配
├── recipe.py     # 工具路径指纹和 jsonl 小抄
├── memory.py     # 分层记忆、daily journal、连续性召回
├── session.py    # 会话保存和恢复
├── bundle.py     # family bundle、genome proposal、community genome pack
├── automation.py # cron-like job、scheduler、webhook ingestion
├── benchmark.py  # 本地 benchmark harness
├── setup.py      # setup / doctor
├── pricing.py    # token 计价
└── ui.py         # Rich UI
```

---

## 迁移说明

如果你之前用的是旧名字 `morrow`，首次启动时 Xirang 会自动把：

```text
~/.morrow → ~/.xirang
MORROW_* → XIRANG_*
```

旧数据不会被自动删除。

---

## 项目愿景

Xirang 想做的不是“更多工具”，而是一个会留下痕迹的 agent：

- 今天它帮你解决一个小问题
- 明天它记得这个问题
- 一周后它把类似问题变成熟练技能
- 一个月后不同人格长出不同能力
- 最后，用户可以选择把脱敏后的技能基因回流给社区

**它不是一次性回答器，是一块会长东西的土。**
