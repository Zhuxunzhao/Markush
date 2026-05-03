# CLAUDE.md — Multi-Agent for Markush

## 项目简介

两条化学专利分析 pipeline：

| Pipeline | 入口 | 输出 |
|---|---|---|
| 侵权分析 | `infringement` | `InfringementResult` — 目标分子是否落入专利 Markush 保护范围 |
| 可专利性评估 | `patentability` | `PatentabilityResult` — 新颖性评分、先有技术重叠、申请建议 |

---

## 目录结构

```
Muti-Agent for Murkush/
├── main.py                      # CLI 入口
├── config.yaml                  # 全局配置（LLM、工具、pipeline）
├── requirements.txt
├── data/
│   └── molpatent-240.json       # 评测数据集（240条，61个US专利+9个WO专利）
├── schemas/
│   └── types.py                 # 所有共享 dataclass 和 enum
├── tools/
│   ├── llm_client.py            # 多 provider LLM 封装（OpenAI/Anthropic/Google）
│   ├── markush_grapher.py       # 图片 → CXSMILES（本地子进程或远程 HTTP）
│   ├── markushgrapher_infer.py  # 推理脚本（在 markushgrapher conda env 中运行）
│   ├── chemical_ocr.py          # 图片 → 文字 + bbox
│   ├── rdkit_matcher.py         # RDKit 子结构匹配
│   ├── patent_scraper.py        # 专利抓取入口
│   ├── google_patent_lookup.py  # 抓取 + 缓存逻辑
│   ├── substructure_match.py    # RDKit R 基团分解
│   ├── rdkit_utils/             # RDKit 辅助工具
│   ├── logger.py                # 结构化 pipeline 日志
│   └── async_utils.py           # 线程并行工具
├── agents/
│   ├── base.py                  # BaseAgent 抽象类
│   ├── claim_analyzer.py        # 解析权利要求
│   ├── subs_matcher.py          # 验证 R 基团映射
│   ├── requirements_examiner.py # R 基团约束检查 → is_protected
│   ├── novelty_analyzer.py      # 新颖性评分
│   ├── prior_art_searcher.py    # 先有技术检索
│   └── report_generator.py      # 生成 Markdown 报告
├── pipelines/
│   ├── infringement.py          # 侵权分析（7步）
│   └── patentability.py         # 可专利性评估（5步）
└── cache/
    └── google_patent/           # 每个专利的缓存目录
```

---

## 架构：Tools → Agents → Pipelines

**Tools**：无状态可调用工具，封装外部库或 HTTP 端点。
**Agents**：LLM 推理单元，`system_prompt → build_user_prompt() → LLMClient.chat() → parse_response()`。
**Pipelines**：按固定顺序编排工具和 Agent，返回类型化结果对象。

---

## 专利抓取与图片获取

### 文字抓取（source 优先级）
1. 本地磁盘缓存（`cache/google_patent/<id>/full_text.txt` 存在则直接读）
2. Google Patents（`google_patent_scraper`）
3. FreePatentsOnline（Google Patents 不可达时的 fallback）

### 图片获取（source 优先级）
1. Google Patents HTML 内嵌的 `patentimages.storage.googleapis.com` 直链
2. USPTO PDF 提取（US 专利专用，Google CDN 被封时的 fallback）
   - 下载：`https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/<patent_id>`
   - 用 PyMuPDF 提取所有内嵌光栅图 → `image_N.png`
   - MarkushGrapher 的 `is_markush` 字段负责过滤非 Markush 图片

**网络现状**：本机 Google 相关 CDN（`patentimages.storage.googleapis.com`）返回 403，上游网络封锁，本机无法解决。数据集中 87% 为 US 专利，USPTO PDF fallback 覆盖绝大多数。

### 缓存格式
```
cache/google_patent/<patent_id>/
├── full_text.txt          # 存在则触发缓存加载
├── abstract_text.txt
├── claim_text.txt
├── description_text.txt
├── url_404_list.json
└── image_1.png, image_2.png, ...
```

---

## Infringement Pipeline 步骤状态

| 步骤 | 组件 | 状态 |
|---|---|---|
| 1 | `PatentScraperTool` — 获取专利 | ✅ |
| 2 | `MarkushGrapherTool` — 图片 → CXSMILES | ✅（本地子进程模式） |
| 3 | `ClaimAnalyzerAgent` — 解析权利要求 | ✅ |
| 4 | `RDKitMatcherTool` — 子结构匹配 | ✅ |
| 5 | `SubsMatcherAgent` — R 基团映射验证 | ✅ |
| 6 | `RequirementsExaminerAgent` — 约束检查 | ✅ |
| 7 | `ReportGeneratorAgent` — 生成报告 | ✅ |

**端到端验证**：`WO2020252229A2` + `CCc1cncc(NCc2cccnc2)n1` → `is_protected=True, confidence=high` ✅

---

## 环境配置

三个 conda 环境：

| Env | Python | 用途 |
|---|---|---|
| `markush` | 3.12 | 主 pipeline（激活这个） |
| `markushgrapher` | 3.10 | MarkushGrapher 推理（子进程自动调用） |
| `chemicalocr` | 3.10 | ChemicalOCR（子进程自动调用） |

环境变量（`.env` 或直接 export）：
```bash
OPENAI_API_KEY=sk-...   # DashScope API key
```
`llm.base_url` 已在 `config.yaml` 中设置，无需另设 `OPENAI_API_BASE`。

---

## 运行

```bash
conda activate markush
source .env

# 侵权分析（完整流程）
python main.py infringement --patent_id WO2020252229A2 --smiles "CCc1cncc(NCc2cccnc2)n1"

# 侵权分析（跳过图片识别，直接提供 caption）
python main.py infringement --patent_id WO2020252229A2 --smiles "CCc1cncc(NCc2cccnc2)n1" \
    --caption "*c1cncc(NCc2cccnc2)n1<sep><a>0:R[1]</a>"

# 可专利性评估
python main.py patentability --cxsmiles "*C1CC(*)CC1<sep><a>0:R[1]</a><a>3:R[2]</a>" \
    --domain "kinase inhibitors"

# 保存结果
python main.py infringement --patent_id WO2020252229A2 --smiles "CCc1cncc(NCc2cccnc2)n1" \
    --output result.json
```

`conda activate` 不传递环境变量时：
```bash
conda run -n markush env OPENAI_API_KEY=sk-... python main.py infringement \
    --patent_id WO2020252229A2 --smiles "CCc1cncc(NCc2cccnc2)n1"
```

---

## MarkushGrapher 本地推理机制

`markushgrapher_infer.py` 在 `markushgrapher` conda 环境中作为子进程运行，与主环境隔离（两者的 `transformers` 版本冲突）：

```
[markush env] MarkushGrapherTool._predict_local_batch()
    → subprocess → [markushgrapher env] markushgrapher_infer.py
        Stage 1: PIL images → ChemicalOCR → bbox
        Stage 2: MarkushGrapher model → generate() → CXSMILES + is_markush
    → JSON stdout → list[MarkushStructure]
```
