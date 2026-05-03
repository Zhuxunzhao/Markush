# Multi-Agent for Markush

多智能体化学专利分析系统，用于Markush结构的侵权分析和可专利性评估。

## 功能

- **侵权分析** - 判断目标分子是否落入专利的Markush保护范围
- **可专利性评估** - 评估拟申请Markush结构的新颖性和现有技术风险

## 环境配置

### 虚拟环境说明

当前仓库支持两种部署方式：

1. **本地 `.venv` + vendored MarkushGrapher**（推荐，适合租卡迁移）
2. **你已有的 conda 环境**（兼容旧工作流）

### 安装步骤

```bash
# 主项目环境
bash scripts/setup_main_env.sh
source .venv/bin/activate

# MarkushGrapher 推理环境
PYTHON_BIN=python3.10 bash scripts/setup_markushgrapher_env.sh

# 下载推理模型（仅 inference 必需文件）
third_party/MarkushGrapher/.venvs/markushgrapher/bin/python scripts/download_markush_assets.py

# 解压专利缓存图片/文本
bash scripts/extract_patent_cache.sh

# 加载API密钥
source .env
```

完整租卡部署说明见 [docs/DEPLOY_RENTAL_GPU.md](docs/DEPLOY_RENTAL_GPU.md)。

## 快速开始

### 使用启动脚本（推荐）

```bash
# 常驻 MarkushGrapher GPU 服务（图片识别需要先启动）
bash scripts/start_markushgrapher_service.sh

# 侵权分析
./run.sh infringement --patent_id US10676478 --smiles "CC(=O)Oc1ccccc1C(=O)O"

# 可专利性评估
./run.sh patentability --cxsmiles "*C1CC(*)CC1<sep><a>0:R[1]</a><a>3:R[2]</a>" --domain "激酶抑制剂"
```

### 手动运行

```bash
conda activate markush
source .env
python main.py infringement --patent_id US10676478 --smiles "CC(=O)Oc1ccccc1C(=O)O"
```

### 启动 Web 界面

```bash
conda activate markush
source .env
pip install -r requirements.txt

./run_web.sh
```

启动后访问：`http://127.0.0.1:8000`

Web 界面提供：
- 侵权分析 / 可专利性评估双模式
- 多 Agent 执行链路看板
- 实时日志事件流
- 结果摘要与报告面板

## 配置说明

### API密钥配置

`.env` 文件包含：
```bash
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 模型配置

`config.yaml` 中配置：
- LLM模型：qwen-max（阿里云百炼）
- MarkushGrapher：仓库内 vendored 模式（`third_party/MarkushGrapher/`）
- RDKit和神经网络匹配器

## 项目结构

```
Muti-Agent for Murkush/
├── main.py              # CLI入口
├── config.yaml          # 全局配置
├── requirements.txt     # Python依赖
├── .env                 # API密钥
├── run.sh              # 启动脚本
├── run_web.sh          # Web 启动脚本
├── agents/             # LLM智能体
├── tools/              # 工具模块
├── pipelines/          # 分析管线
├── schemas/            # 数据类型定义
├── scripts/            # 环境安装/模型下载/缓存解压脚本
└── third_party/        # vendored MarkushGrapher 源码
```

补充目录：
- `docs/`：补充分析文档与架构材料
- `web/`：FastAPI UI 代码、静态资源与上传目录
- `data/`：评测数据集
- `cache/`：专利抓取缓存与图片资源（含 `google_patent.tar.gz`）
- `outputs/`：示例输出与运行产物归档

## 详细文档

参见 [CLAUDE.md](CLAUDE.md) 获取完整的架构说明和API文档。

## MarkushGrapher部署

仓库已内置 `MarkushGrapher` 推理源码到 `third_party/MarkushGrapher/`。

出于 GitHub 文件大小限制，模型权重不直接随 git 推送，使用以下脚本补齐：

```bash
PYTHON_BIN=python3.10 bash scripts/setup_markushgrapher_env.sh
third_party/MarkushGrapher/.venvs/markushgrapher/bin/python scripts/download_markush_assets.py
```

这会下载：
- ChemicalOCR inference 权重
- MarkushGrapher-2 inference 权重
- MolScribe checkpoint
