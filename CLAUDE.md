# CLAUDE.md — Matrix 分层事件概率推理系统

## 项目概述

Matrix 是一个多层概率推理系统，由信息采集 → 事件抽取 → 分层推理 → 结论聚合四个阶段组成。系统从外部信息源采集原始内容，逐层推导事件概率，最终输出带置信区间的预测结论。

**核心设计原则**：每个 Agent 只做一件简单的事，复杂判断由层级结构涌现而来。

-----

## 技术栈

|层    |技术                                                        |
|-----|----------------------------------------------------------|
|语言   |Python 3.11+                                              |
|网页抓取 |httpx（直接抓取）+ Jina Reader API（清洗提取）+ Playwright（JS渲染页面）    |
|LLM  |Anthropic Claude Haiku（`claude-haiku-4-5`），所有 Agent 统一使用  |
|数据库  |Supabase（PostgreSQL + RLS）                                |
|推理图配置|YAML 文件                                                   |
|调度   |Python asyncio（MVP），后期可迁移至 BullMQ                         |
|前端   |Next.js 14 App Router + TypeScript + Tailwind + React Flow|
|部署   |Vercel（前端）+ 本地/VPS（Python 后端）                             |

-----

## 目录结构

```
matrix/
├── CLAUDE.md                    # 本文件
├── README.md
├── .env                         # 环境变量（不提交）
├── .env.example
│
├── graphs/                      # 推理图配置（YAML）
│   └── hormuz_blockade_7d.yaml  # MVP 示例图
│
├── backend/                     # Python 后端
│   ├── main.py                  # 入口：手动触发运行
│   ├── config.py                # 环境变量加载
│   │
│   ├── crawl/                   # 信息采集层
│   │   ├── __init__.py
│   │   ├── httpx_crawler.py     # 直接 HTTP 抓取
│   │   ├── jina_crawler.py      # Jina Reader API 抓取
│   │   ├── playwright_crawler.py # JS 渲染页面抓取
│   │   └── crawler_router.py    # 根据 URL 选择抓取策略
│   │
│   ├── agents/                  # Agent 层
│   │   ├── __init__.py
│   │   ├── parse_agent.py       # Observation 抽取 Agent
│   │   ├── reasoning_agent.py   # 推理层 Agent（混合计算）
│   │   └── conclusion_agent.py  # 结论 narrative 生成 Agent
│   │
│   ├── engine/                  # 推理图引擎
│   │   ├── __init__.py
│   │   ├── graph_loader.py      # 加载 YAML 配置
│   │   ├── graph_runner.py      # 执行推理图（调度各层）
│   │   └── probability.py       # 公式计算 + 置信区间
│   │
│   ├── db/                      # 数据库操作
│   │   ├── __init__.py
│   │   ├── client.py            # Supabase 客户端
│   │   ├── observations.py      # Observation CRUD
│   │   ├── event_nodes.py       # EventNode CRUD
│   │   └── conclusions.py       # Conclusion CRUD
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py
│       └── id_gen.py            # 生成 run_id / node_id
│
└── frontend/                    # Next.js Dashboard
    ├── app/
    │   ├── page.tsx             # 结论总览页
    │   ├── graph/[id]/page.tsx  # 推理图可视化页
    │   └── api/
    │       ├── run/route.ts     # POST 触发运行
    │       └── conclusions/route.ts
    ├── components/
    │   ├── ConclusionCard.tsx
    │   ├── GraphView.tsx        # React Flow 推理图
    │   └── NodeDetail.tsx
    └── lib/
        └── supabase.ts
```

-----

## 环境变量

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
JINA_API_KEY=jina_...          # Jina Reader API Key
```

-----

## 数据库 Schema

在 Supabase SQL Editor 中执行以下建表语句：

```sql
-- 推理图定义
CREATE TABLE graphs (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  config JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 推理运行记录
CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  graph_id TEXT REFERENCES graphs(id),
  status TEXT DEFAULT 'pending',  -- pending | running | done | failed
  started_at TIMESTAMPTZ DEFAULT NOW(),
  finished_at TIMESTAMPTZ
);

-- 原始观测
CREATE TABLE observations (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES runs(id),
  source TEXT,
  content TEXT NOT NULL,
  url TEXT,
  confidence FLOAT DEFAULT 0.5,
  tags TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 事件节点（每次 run 的快照）
CREATE TABLE event_nodes (
  id TEXT,
  run_id TEXT REFERENCES runs(id),
  graph_id TEXT,
  layer INT NOT NULL,
  label TEXT NOT NULL,
  probability FLOAT NOT NULL,
  formula_prob FLOAT,
  llm_delta FLOAT,
  reasoning TEXT,
  inputs JSONB DEFAULT '[]',  -- [{node_id, weight, probability, label}]
  observation_ids TEXT[] DEFAULT '{}',  -- P1 层关联的 obs
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (id, run_id)
);

-- 结论
CREATE TABLE conclusions (
  id TEXT,
  run_id TEXT REFERENCES runs(id),
  graph_id TEXT,
  label TEXT NOT NULL,
  probability FLOAT NOT NULL,
  confidence_band JSONB,  -- [low, high]
  narrative TEXT,
  supporting_event_ids TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (id, run_id)
);
```

-----

## 核心模块实现规范

### 1. 抓取策略路由（crawler_router.py）

**三种抓取方式的使用场景：**

|方式         |使用场景             |特点                       |
|-----------|-----------------|-------------------------|
|httpx      |静态页面、RSS、API     |最快，无需 API key            |
|Jina Reader|需要清洁 Markdown 的页面|`https://r.jina.ai/{url}`|
|Playwright |JS 渲染的 SPA 页面    |最慢，用于兜底                  |

**路由逻辑：**

```python
async def fetch(url: str, source_config: dict) -> str:
    """
    source_config 示例：
    {
      "url": "https://...",
      "method": "jina",   # httpx | jina | playwright | auto
      "tags": ["military", "iran"]
    }
    
    method=auto 时的判断逻辑：
    1. 先用 httpx 抓，检查响应是否含有足够文本内容（> 500 chars）
    2. 如内容不足（可能是 JS 渲染），切换到 Jina
    3. 如 Jina 也失败（非公开页面等），切换到 Playwright
    """
```

**Jina Reader 调用方式：**

```python
# 方式一：直接前缀（无需 API Key，有速率限制）
url = f"https://r.jina.ai/{target_url}"

# 方式二：带 API Key（推荐，更稳定）
headers = {
    "Authorization": f"Bearer {JINA_API_KEY}",
    "Accept": "text/plain",           # 返回纯文本
    "X-Return-Format": "markdown",    # 返回 Markdown
}
response = await httpx_client.get(
    f"https://r.jina.ai/{target_url}",
    headers=headers,
    timeout=30
)
```

-----

### 2. Parse Agent（parse_agent.py）

输入：原始抓取文本  
输出：Observation 列表

```python
PARSE_PROMPT = """
你是一个信息抽取 agent。从以下文本中抽取与"{topic}"相关的关键事实陈述。

要求：
- 每条陈述必须是一个独立的客观事实或事件
- 不要推断，只陈述文本中明确提到的内容
- 每条陈述附一个置信度（0~1），反映文本对该陈述的支持程度
- 最多抽取 5 条最相关的陈述

文本内容：
{text}

仅输出以下 JSON，不要任何其他内容：
{
  "observations": [
    {"content": "<陈述>", "confidence": <float>, "tags": ["<tag1>", "<tag2>"]}
  ]
}
"""
```

-----

### 3. 概率计算（probability.py）

```python
def formula_prob(inputs: list[dict]) -> float:
    """
    inputs: [{"probability": 0.7, "weight": 0.4}, ...]
    加权平均
    """
    total_weight = sum(i["weight"] for i in inputs)
    if total_weight == 0:
        return 0.5
    return sum(i["probability"] * i["weight"] for i in inputs) / total_weight


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def final_prob(formula: float, delta: float) -> float:
    delta_clamped = clamp(delta, -0.15, 0.15)
    return clamp(formula + delta_clamped)


def confidence_band(probability: float, layer: int) -> tuple[float, float]:
    """
    误差随层数累积。
    σ_layer = 0.05 × (1.2 ^ (layer - 1))
    band = P ± 1.96σ
    """
    sigma = 0.05 * (1.2 ** (layer - 1))
    low = clamp(probability - 1.96 * sigma)
    high = clamp(probability + 1.96 * sigma)
    return (round(low, 3), round(high, 3))
```

-----

### 4. Reasoning Agent（reasoning_agent.py）

P2+ 层每个节点调用一次 Haiku：

```python
REASONING_PROMPT = """
你是一个事件推理 agent。你的任务是对一个命题的发生概率做语义修正。

【当前命题】
{label}

【输入事件及其概率】
{inputs_text}

【结构公式估算的基础概率】
{formula_prob:.2f}

【你的任务】
判断该基础概率是否需要语义修正。
请考虑：输入事件之间是否存在协同或对冲关系？是否有未被公式捕捉的语义因素？

修正范围：严格限制在 -0.15 ~ +0.15 之间。

仅输出以下 JSON，不要任何其他内容：
{{"delta": <float>, "reason": "<一句中文说明>"}}
"""
```

**调用规范：**

- 模型：`claude-haiku-4-5`
- max_tokens：200
- temperature：0（确保稳定性）
- 解析失败时 delta 默认为 0，不中断流程

-----

### 5. 推理图执行器（graph_runner.py）

```python
async def run_graph(graph_id: str, run_id: str):
    """
    执行顺序（严格按层串行，层内并行）：
    
    1. 加载图配置
    2. 采集阶段：并行抓取所有 sources
    3. Parse 阶段：并行调用 Parse Agent
    4. 写入 observations
    5. 逐层执行：
       for layer in layers:
           tasks = [process_node(node, run_id) for node in layer.nodes]
           await asyncio.gather(*tasks)   # 层内并行
    6. 执行 conclusions
    7. 更新 run status = done
    """
```

**关键约束：**

- 层与层之间必须串行（下一层依赖上一层结果）
- 同一层内的节点并行执行
- 任意节点失败不中断整体流程，该节点 probability 记为 null，跳过
- 每次运行创建新 run_id，历史数据永久保留

-----

### 6. YAML 推理图配置格式

```yaml
graph_id: hormuz_blockade_7d
name: 霍尔木兹海峡封锁风险（7天）
version: 1

# 信息来源配置
sources:
  - url: "https://www.reuters.com/world/middle-east/"
    method: jina          # httpx | jina | playwright | auto
    tags: ["military", "iran", "hormuz"]
  - url: "https://oilprice.com/"
    method: httpx
    tags: ["energy", "oil", "shipping"]
  - url: "https://www.aljazeera.com/news/"
    method: jina
    tags: ["military", "diplomacy"]

# 推理图配置
topic: "霍尔木兹海峡封锁风险"  # 用于 Parse Agent 的过滤词

layers:
  - id: P1
    label: 基础事件层
    nodes:
      - id: e_iran_rhetoric
        label: 伊朗对外强硬声明频率上升
        # P1 层 inputs 为空，从 observations 聚合
        # observation_tags 用于从 obs 中筛选相关信号
        observation_tags: ["military", "iran"]

      - id: e_us_navy_presence
        label: 美军在波斯湾军事存在增强
        observation_tags: ["military", "hormuz"]

      - id: e_tanker_anomaly
        label: 油轮通行出现异常
        observation_tags: ["shipping", "hormuz"]

      - id: e_diplomacy_stalled
        label: 外交渠道受阻
        observation_tags: ["diplomacy", "iran"]

      - id: e_energy_panic
        label: 能源市场出现恐慌信号
        observation_tags: ["energy", "oil"]

  - id: P2
    label: 一阶推论层
    nodes:
      - id: e_military_escalation
        label: 地区军事对峙升级
        inputs:
          - node: e_iran_rhetoric
            weight: 0.4
          - node: e_us_navy_presence
            weight: 0.4
          - node: e_diplomacy_stalled
            weight: 0.2

      - id: e_transport_risk
        label: 能源运输风险显著上升
        inputs:
          - node: e_us_navy_presence
            weight: 0.3
          - node: e_tanker_anomaly
            weight: 0.4
          - node: e_energy_panic
            weight: 0.3

      - id: e_diplomacy_insufficient
        label: 国际外交缓解力度不足
        inputs:
          - node: e_diplomacy_stalled
            weight: 0.6
          - node: e_iran_rhetoric
            weight: 0.4

  - id: P3
    label: 二阶推论层
    nodes:
      - id: e_blockade_precursor
        label: 封锁行动出现明显前兆
        inputs:
          - node: e_military_escalation
            weight: 0.5
          - node: e_transport_risk
            weight: 0.5

      - id: e_diplomacy_window_closed
        label: 外交缓解窗口实质性关闭
        inputs:
          - node: e_military_escalation
            weight: 0.4
          - node: e_diplomacy_insufficient
            weight: 0.6

conclusions:
  - id: c_blockade_7d
    label: 未来7天霍尔木兹海峡通行受阻概率
    inputs:
      - node: e_blockade_precursor
        weight: 0.5
      - node: e_diplomacy_window_closed
        weight: 0.3
      - node: e_transport_risk
        weight: 0.2

  - id: c_blockade_30d
    label: 未来30天封锁正式启动概率
    inputs:
      - node: e_blockade_precursor
        weight: 0.4
      - node: e_diplomacy_window_closed
        weight: 0.4
      - node: e_military_escalation
        weight: 0.2
```

-----

## 实现顺序（严格按此顺序，不要跳步）

### Phase 1：基础设施

1. 创建项目目录结构
1. 配置 `.env` 和 `config.py`
1. 在 Supabase 执行建表 SQL
1. 验证 Supabase 连接（`db/client.py`）

### Phase 2：采集层

1. 实现 `httpx_crawler.py`（直接抓取 + 超时处理）
1. 实现 `jina_crawler.py`（Jina Reader API 调用）
1. 实现 `playwright_crawler.py`（JS 渲染，仅兜底用）
1. 实现 `crawler_router.py`（auto 策略路由）
1. 实现 `parse_agent.py`（Observation 抽取）
1. 单元测试：用一个 URL 跑通抓取 → 解析 → 写入 observations 的完整链路

### Phase 3：推理层

1. 实现 `graph_loader.py`（解析 YAML → Python 对象）
1. 实现 `probability.py`（公式计算、clamp、置信区间）
1. 实现 `reasoning_agent.py`（Haiku 调用 + delta 解析）
1. 实现 `graph_runner.py`（层级调度）
1. 实现 `conclusion_agent.py`（narrative 生成）
1. 端到端测试：用 hormuz_blockade_7d.yaml 跑一次完整推理

### Phase 4：前端 Dashboard

1. 搭建 Next.js 项目，配置 Supabase client
1. 实现结论总览页（Conclusion 卡片列表）
1. 实现推理图可视化页（React Flow DAG）
1. 实现手动触发运行按钮（调用 Python backend API）
1. 节点点击 → 显示详情面板（formula_prob、llm_delta、reasoning、溯源）

-----

## 关键约束与禁止事项

**绝对不能做：**

- ❌ 不能让 LLM delta 超过 ±0.15（硬限制，代码层面 clamp）
- ❌ 不能跨层读取（P3 不能直接读 P1 的节点）
- ❌ 不能在同一层内建立依赖（同层节点不能互相引用）
- ❌ 不能删除历史 run 数据（只追加）
- ❌ 不能让单次 run 的 Haiku 调用超过 50 次（成本控制）

**必须保证：**

- ✅ 每个节点失败时有 fallback（delta=0，probability=formula_prob）
- ✅ 所有 Haiku 调用必须有 timeout（30s）和 retry（最多 2 次）
- ✅ 每次 run 结束后更新 runs.status 和 runs.finished_at
- ✅ 所有概率值存储时保留 3 位小数（round to 3）
- ✅ P1 层节点必须有 observation_ids 字段，记录依据

-----

## 前端视觉规范

参考 firms.jp 深色编辑风格：

```
背景色：#0D0D0D
卡片背景：#141414
边框：#222222
主文字：#F0F0F0
次要文字：#666666
等宽字体：DM Mono 或 Space Mono
标题字体：DM Serif Display

概率颜色编码：
  P > 0.7  → #EF4444（红，高风险）
  0.4 < P ≤ 0.7 → #F59E0B（黄，中性）
  P ≤ 0.4  → #22C55E（绿，低风险）

React Flow 节点颜色：
  P1 层：#1E293B（深蓝灰）
  P2 层：#1E3A2F（深绿）
  P3 层：#2D1F3D（深紫）
  结论层：#3D1F1F（深红）
  边（arrow）：#333333，hover 时 #666666
```

-----

## 常见问题处理

**Jina 返回内容过长（> 10000 chars）：**
截取前 8000 chars 传给 Parse Agent，不影响抽取质量。

**Haiku 返回非合法 JSON：**
用 try/except 捕获，delta 默认为 0，reason 记为 “parse_failed”，继续执行。

**某 source URL 抓取失败（网络超时等）：**
跳过该 source，记录 warning，不中断整体 run。

**P1 层某节点关联的 observations 为空：**
probability 设为 0.5（中性默认值），llm_delta 设为 0，reasoning 记为 “no_observations”。

**YAML 配置中节点引用了不存在的 node id：**
graph_loader 加载时做完整性校验，抛出 ValueError 明确指出哪个引用缺失。

-----

## 后续扩展预留

代码中预留但 MVP 不实现：

- `source_config.method = "rss"` — RSS feed 解析
- `source_config.method = "api"` — 结构化 API（如金融数据）
- `graph_config.schedule` — 定时运行 cron 表达式
- `node_config.weight_decay` — 权重衰减（时效性调整）
- `run_config.compare_with_run_id` — 与历史 run 对比

-----

*CLAUDE.md v0.1 | 对应 PRD v0.1 | Matrix MVP*