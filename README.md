# Matrix

Matrix 是一个分层事件概率推理系统（采集 -> 抽取 -> 推理 -> 结论聚合）。本仓库包含：

- `backend/`: Python 3.11+ 推理引擎与采集执行器
- `frontend/`: Next.js 14 Dashboard
- `graphs/`: YAML 推理图配置

## 1. 快速开始

### 后端

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
python -m backend.main --graph-id hormuz_blockade_7d
# or start API server for frontend trigger button
uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload
```

### 前端

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

默认访问 `http://localhost:3000`。

## 2. 环境变量

参考根目录 `.env.example`。

后端读取：

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`（默认 `minimax/minimax-m1`）
- `OPENROUTER_MODELS`（逗号分隔，供前端模型下拉）
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `JINA_API_KEY`

前端读取：

- `SUPABASE_URL`（推荐，服务端读取）
- `SUPABASE_SERVICE_KEY`（推荐，服务端读取）
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `BACKEND_RUN_ENDPOINT`
- `BACKEND_OBSERVE_ENDPOINT`
- `BACKEND_MODELS_ENDPOINT`
- `BACKEND_RUN_TIMEOUT_MS`（默认建议 `300000`）
- `BACKEND_OBSERVE_TIMEOUT_MS`（默认建议 `180000`）
- `RUN_OBSERVE_FIRST`（默认 `true`，`/run` 前先生成 Observation）
- `OBSERVE_BOT_COUNT`（默认 `5`）
- `OBSERVE_RESULTS_PER_BOT`（默认 `5`）

## 3. 数据库

在 Supabase SQL Editor 里执行 [sql/init_schema.sql](/Users/akira/codebase/matrix/sql/init_schema.sql)。

如果你已经在历史版本中建过表，再执行一次 [sql/add_running_guard.sql](/Users/akira/codebase/matrix/sql/add_running_guard.sql) 以启用“同一图同一时刻仅允许一个 running run”的约束。

本地检查：

```bash
../venv/bin/python -m backend.scripts.check_supabase
```

把图配置写入 `graphs` 表：

```bash
../venv/bin/python -m backend.scripts.seed_graph --graph-id hormuz_blockade_7d
```

## 4. 当前脚手架能力

- 支持三种抓取策略：`httpx` / `jina` / `playwright` / `auto`
- 支持 Parse Agent、Reasoning Agent、Conclusion Agent
- 支持按层串行、层内并行执行推理图
- 支持失败 fallback，不中断全局 run
- 前端可查看结论列表与图节点详情（基础版）
- 支持 Observation 模式：输入命题后自动启动搜索 bots，抓取并抽取 Observation（默认 5 bots × 每 bot 5 条）
- 支持 Observation -> P1 闭环：`/run` 可先跑 Observation，再按 `observation_tags` 自动聚合到 P1 节点
- Observation 支持时间窗口过滤（最近 N 个月）与信源约束（域名白名单）
- 前端支持左侧导航 + 右侧 Tab：`Observation / Forcast / Result / Settings`

## 5. 后续建议

1. 为 `backend/engine/graph_runner.py` 增加更细粒度单测
2. 在 `frontend` 完成 React Flow 样式与交互增强
3. 增加后端 HTTP API（FastAPI）供前端直接触发

## 6. 从“Supabase已配置”继续的完整命令

```bash
# 1) 激活你常用的 venv（你当前可用这个）
source ../venv/bin/activate

# 2) 校验依赖
pip install -r backend/requirements.txt

# 3) 执行 SQL（在 Supabase 控制台粘贴 sql/init_schema.sql）

# 4) 检查表可访问
python -m backend.scripts.check_supabase

# 5) 写入图配置
python -m backend.scripts.seed_graph --graph-id hormuz_blockade_7d

# 6) 启动后端 API
uvicorn backend.api:app --host 0.0.0.0 --port 8000 --reload

# 7) 新终端启动前端
cd frontend && npm install && npm run dev
```
