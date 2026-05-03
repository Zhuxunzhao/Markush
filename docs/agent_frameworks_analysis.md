# 主流 Agent 框架调研：适用于 Markush 专利分析多智能体系统

> 调研日期：2026-04-18
> 项目背景：Multi-Agent for Markush — 化学专利 Markush 结构侵权分析 & 可专利性评估系统

---

## 一、项目现状与核心需求

### 当前架构

项目已实现自定义多智能体框架，包含：
- **6 个专业 Agent**：ClaimAnalyzer、SubsMatcher、RequirementsExaminer、PriorArtSearcher、NoveltyAnalyzer、ReportGenerator
- **6 个领域工具**：PatentScraper、MarkushGrapher、ChemicalOCR、RDKitMatcher、NNMatcher、LLMClient
- **2 条 Pipeline**：侵权分析（infringement）、可专利性分析（patentability）
- **自定义 BaseAgent**：统一的 system_prompt → user_prompt → LLM 调用 → 结构化解析模式

### 框架选型关键需求

| 需求 | 说明 |
|------|------|
| 领域工具封装 | 必须能包装 RDKit、T5 神经网络匹配器、专利爬虫等非标准工具 |
| 顺序+并行编排 | Pipeline 以顺序为主，RDKit 和 NN Matcher 需并行执行 |
| 结构化输出 | 大量使用 Pydantic 类型（MarkushStructure、InfringementResult 等） |
| 多 LLM 支持 | 已支持 OpenAI / Anthropic / Google，框架不能限制 provider |
| 轻量级 | 项目是任务型 pipeline，不是对话型 chatbot，不需要重量级框架 |
| 迁移成本 | 现有代码已可运行，框架必须带来明确收益才值得迁移 |

---

## 二、框架逐一评估

### 1. LangGraph（LangChain）⭐⭐⭐⭐⭐ 最推荐

| 项目 | 详情 |
|------|------|
| 版本 | v1.1.8（2026-04-17） |
| 成熟度 | 生产就绪，Klarna、Uber、J.P. Morgan 在用 |
| Stars | ~29.5k |

**适合本项目的原因：**

- **图编排模型完美匹配**：Pipeline 中 RDKit + NNMatcher 并行 → SubsMatcher 融合的模式，用 StateGraph 可以自然表达为分支-汇合图
- **状态管理强大**：每个节点（Agent）的输出自动流入共享 State，天然适合 pipeline 中间结果传递
- **自定义工具无障碍**：`@tool` 装饰器或 `BaseTool` 子类，RDKit、MarkushGrapher 等工具可直接封装
- **结构化输出**：通过 Pydantic 模型 + output parser 原生支持
- **多 LLM**：通过 LangChain 生态支持所有主流 provider
- **检查点和恢复**：长 pipeline 中途失败可从断点恢复，对专利分析这种耗时任务很有价值
- **LangSmith 可观测性**：调试 Agent 推理过程非常方便

**潜在问题：**
- 学习曲线较陡，图定义对简单顺序任务略显冗余
- 与 LangChain 生态耦合，引入额外依赖

**迁移建议：** 将现有 `infringement.py` 和 `patentability.py` 重构为 StateGraph，每个 Agent 作为一个 node，工具调用在 node 内部完成。预计迁移工作量中等，但收益显著（状态管理、错误恢复、可观测性）。

---

### 2. CrewAI ⭐⭐⭐⭐ 强烈推荐

| 项目 | 详情 |
|------|------|
| 版本 | v1.14.2（2026-04-17） |
| 成熟度 | 生产就绪，社区最大（49.1k stars） |
| Stars | ~49.1k |

**适合本项目的原因：**

- **角色定义直觉化**：每个 Agent 定义 role、goal、backstory，与现有 `system_prompt` 模式高度吻合
- **Sequential Process**：直接对应现有 pipeline 的顺序执行模式
- **Pydantic 结构化输出**：原生支持
- **自定义工具**：`@tool` 装饰器，封装 RDKit 等工具简单直接
- **上手最快**：API 设计简洁，迁移成本最低
- **内置 Memory 和 Knowledge**：可缓存专利分析中间结果

**潜在问题：**
- 并行执行支持不如 LangGraph 灵活（RDKit + NNMatcher 并行需要额外处理）
- 不支持任意图拓扑，复杂分支逻辑需要用 Flows 实现
- Flows 功能增加了额外复杂度

**迁移建议：** 最低成本迁移方案。现有 Agent 几乎可以 1:1 映射为 CrewAI Agent + Task。适合快速验证框架价值。

---

### 3. OpenAI Agents SDK ⭐⭐⭐ 推荐

| 项目 | 详情 |
|------|------|
| 版本 | v0.14.2（2026-04-18） |
| 成熟度 | 生产就绪，Swarm 的正式继任者 |
| Stars | ~21.9k |

**适合本项目的原因：**

- **极简设计**：最少的抽象层，Python 原生编排
- **Agents-as-tools 模式**：可以将 SubsMatcher 作为 RequirementsExaminer 的工具，实现层级调用
- **Pydantic 结构化输出**：自动 schema 生成
- **Provider 无关**：虽然名为 OpenAI，实际支持 100+ LLM
- **内置 tracing**：调试方便

**潜在问题：**
- 仍为 v0.x，API 可能变化
- Handoff 模型对顺序 pipeline 不是最自然的表达方式
- 没有声明式 workflow 定义，全靠 Python 代码编排
- 与现有自定义框架差异不大，迁移收益有限

**迁移建议：** 如果团队偏好 OpenAI 生态，这是一个轻量级选择。但对本项目而言，相比现有自定义框架的增量价值不够明显。

---

### 4. AG2 / AutoGen（Microsoft）⭐⭐⭐ 有条件推荐

| 项目 | 详情 |
|------|------|
| 版本 | v0.12.0（approaching v1.0） |
| 成熟度 | Beta 阶段 |
| Stars | ~4.4k（AG2 repo） |

**适合本项目的原因：**

- **跨框架互操作**：可以混合使用 AG2 + LangChain + OpenAI 的 Agent，未来扩展灵活
- **Group Chat 模式**：多 Agent 协作讨论，适合需要多轮推理的复杂专利分析场景
- **代码执行沙箱**：安全执行 RDKit 代码

**潜在问题：**
- 仍为 pre-v1.0，API 不稳定，即将有 breaking changes
- 品牌混乱（AutoGen → AG2），社区分裂
- 对话式范式与本项目的任务型 pipeline 不太匹配
- 文档在过渡期不够一致

**迁移建议：** 等 v1.0 稳定后再考虑。目前风险较高。

---

### 5. Agno（原 Phidata）⭐⭐⭐ 有条件推荐

| 项目 | 详情 |
|------|------|
| 版本 | v2.5.17（2026-04-15） |
| 成熟度 | 生产就绪 |
| Stars | ~39.5k |

**适合本项目的原因：**

- **三层架构**：Agent → Team → Workflow，与项目的 Agent → Pipeline 结构对应
- **生产运行时**：水平扩展、多租户隔离，如果未来要做 SaaS 服务很有价值
- **100+ 内置集成**：减少工具封装工作
- **MCP 支持**：可扩展工具生态

**潜在问题：**
- 品牌重塑（Phidata → Agno）导致文档和社区过渡期混乱
- Team 编排模式文档不如 LangGraph/CrewAI 完善
- 对本项目当前阶段（研究/原型）来说，生产运行时功能过重

**迁移建议：** 如果项目未来要产品化/SaaS 化，Agno 的运行时能力值得关注。当前阶段不是最优选择。

---

### 6. Semantic Kernel（Microsoft）⭐⭐ 一般推荐

| 项目 | 详情 |
|------|------|
| 版本 | Python v1.41.2 |
| 成熟度 | 核心 SDK 生产就绪，Agent 编排仍为实验阶段 |
| Stars | ~27.7k |

**不太适合的原因：**
- Agent 编排功能仍为实验阶段，不够稳定
- C# 是第一语言，Python 功能可能滞后
- 框架偏重，对本项目来说过度设计
- 与 Azure 生态耦合较深

**唯一亮点：** 5 种内置编排模式（Sequential、Concurrent、Handoff、Group Chat、Magentic）是所有框架中最丰富的。

---

### 7. CAMEL-AI ⭐⭐ 不推荐

| 项目 | 详情 |
|------|------|
| 版本 | v0.2.90 |
| 成熟度 | 研究导向 |
| Stars | ~16.7k |

**不适合的原因：**
- 研究导向，不适合生产使用
- 角色扮演范式更适合模拟场景，不适合确定性 pipeline
- 结构化输出支持不明确
- 社区和文档不如主流框架

---

### 8. MetaGPT ⭐ 不推荐

| 项目 | 详情 |
|------|------|
| 版本 | v0.8.1（2024-04 发布，已停更一年+） |
| Stars | ~67.2k（虚高） |

**不适合的原因：**
- 已停止更新超过一年
- 专注于软件开发 SOP，不适合化学专利分析领域
- 灵活性极差，难以自定义 pipeline
- Stars 虚高，实际活跃度很低

---

### 9. Swarm（OpenAI）❌ 不推荐

已被 OpenAI Agents SDK 正式取代，不再维护。仅作为教学参考。

---

### 10. Claude Agent SDK（Anthropic）⭐⭐ 不推荐作为框架

**定位说明：** 这不是一个多智能体框架，而是 Claude 模型的 SDK。提供优秀的工具调用和结构化输出能力，但没有内置的多 Agent 编排。

**适合的场景：** 如果只用 Claude 模型，且愿意自己写编排逻辑（类似现有方案）。

**不适合的原因：** 锁定 Anthropic 模型，无 Agent 编排原语，与现有自定义框架相比没有额外价值。

---

## 三、综合对比

| 框架 | 推荐度 | 编排灵活性 | 工具封装 | 结构化输出 | 多LLM | 迁移成本 | 额外收益 |
|------|--------|-----------|---------|-----------|-------|---------|---------|
| **LangGraph** | ⭐⭐⭐⭐⭐ | 最高（图） | 优秀 | 原生 | 全支持 | 中 | 状态管理/检查点/可观测 |
| **CrewAI** | ⭐⭐⭐⭐ | 中高 | 优秀 | 原生 | 多数支持 | 低 | 快速上手/内置Memory |
| **OpenAI Agents** | ⭐⭐⭐ | 中 | 优秀 | 原生 | 100+ | 低 | Tracing/Sandbox |
| **AG2** | ⭐⭐⭐ | 高 | 良好 | 一般 | 全支持 | 中高 | 跨框架互操作 |
| **Agno** | ⭐⭐⭐ | 中高 | 优秀 | 原生 | 多数支持 | 中 | 生产运行时 |
| **Semantic Kernel** | ⭐⭐ | 高（实验） | 良好 | 良好 | 多数支持 | 高 | 编排模式丰富 |
| **CAMEL-AI** | ⭐⭐ | 中 | 一般 | 不明确 | 中 | 高 | 研究价值 |
| **MetaGPT** | ⭐ | 低 | 有限 | 特定领域 | 中 | 高 | 无 |
| **Swarm** | ❌ | 低 | 基础 | 无 | OpenAI only | - | 已废弃 |
| **Claude SDK** | ⭐⭐ | 无（DIY） | 优秀 | 优秀 | Anthropic only | - | 非框架 |

---

## 四、最终建议

### 方案 A：采用 LangGraph（推荐）

适合场景：项目需要长期维护、pipeline 会变得更复杂、需要错误恢复和可观测性。

```
优势：
├── 图编排天然支持并行分支（RDKit ∥ NNMatcher → SubsMatcher）
├── 自动检查点：长时间专利分析中途失败可恢复
├── LangSmith 集成：可视化每个 Agent 的推理过程
└── 社区活跃，长期维护有保障

迁移路径：
1. 保留现有 tools/ 目录不变
2. 将 BaseAgent 适配为 LangGraph node
3. 将 infringement.py → StateGraph 定义
4. 将 patentability.py → StateGraph 定义
5. 用 TypedDict 替代现有 State 传递方式
```

### 方案 B：采用 CrewAI（快速验证）

适合场景：想快速验证框架价值、团队对 Agent 框架不熟悉、优先降低迁移风险。

```
优势：
├── 迁移成本最低：Agent 定义几乎 1:1 映射
├── 上手最快：API 直觉化
├── 社区最大：遇到问题容易找到解决方案
└── 内置 Memory/Knowledge 可缓存专利数据

迁移路径：
1. 每个 Agent → CrewAI Agent（role=现有 system_prompt）
2. 每个 Pipeline 步骤 → CrewAI Task
3. Pipeline → Crew（process=sequential）
4. 工具 → @tool 装饰器封装
```

### 方案 C：保持现有自定义框架 + 局部增强

适合场景：项目处于研究阶段、pipeline 结构稳定、不想引入额外依赖。

```
优势：
├── 零迁移成本
├── 完全控制，无框架约束
├── 依赖最少
└── 对化学领域的特殊需求可以灵活处理

建议增强：
1. 添加 Pydantic 严格校验（如果还没有）
2. 添加简单的日志/tracing 机制
3. 为 RDKit + NNMatcher 添加 asyncio 并行执行
4. 添加 pipeline 中间结果缓存
```

### 我的判断

> 如果项目即将进入工程化/产品化阶段 → **选 LangGraph**，它的状态管理、检查点恢复和可观测性对长 pipeline 的价值最大。
>
> 如果想先低成本试水 → **选 CrewAI**，迁移最快，验证框架是否真的带来收益。
>
> 如果项目仍在研究/论文阶段 → **保持现有框架**，把精力放在算法和实验上，不要为了用框架而用框架。

---

*本文档基于 2026 年 4 月各框架最新版本信息编写。框架生态变化较快，建议在实际选型时再次确认版本状态。*
