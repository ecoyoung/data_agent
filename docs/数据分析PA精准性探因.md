# 数据分析PA精准性探因

*Exported on 2026/6/1 17:05:55 · Created Unknown*

---

## Data Agent 落地状态（2026-07-20）

本文档总结的是 PA/数探准确性方法论。当前 Data Agent 没有照搬其中 Shopify、会员、站点等业务规则，而是按本项目 `intermediate_amazon_` Amazon 中间表族做了定制落地：

- `src/data_agent/data_catalog/hints.json`：按表族维护 AI_HINT，当前覆盖 3P orders、Business Report、AMS advertised product、AMS campaigns 和 scope identity。
- `src/data_agent/data_catalog/relationships.json`：机器可读 JOIN 关系，当前覆盖 orders + AMS advertised product、orders + AMS campaigns、Business Report + AMS advertised product。
- `src/data_agent/agent/scope_resolver.py`：LLM 前确定性解析品牌/项目别名，例如 `BKN US` -> `beekeeper_us`，裸 `BKN` 先澄清 US/CA/整体。
- `src/data_agent/agent/prompt_builder.py`：按用户问题和候选表裁剪 AI_HINT，并用 `exclude_patterns` 做表路由减分，避免上下文污染。
- `src/data_agent/agent/sql_checker.py`：执行前校验中间表 JOIN 关系、字段存在性、业务规则和权限风险。
- `src/data_agent/agent/sql_executor.py`：运行时用当前 DB 用户做 SELECT 权限预检，Catalog 权限快照过期时也能兜底。

当前项目采用的原则是：方法论可借鉴，业务规则必须来自本项目真实中间表结构和真实失败案例。

---

## 🧑 User

总结核心内容

---

## 🤖 Assistant

- **Tool:** `filesystem_read_text_file`

---

## 🤖 Assistant

- **Tool:** `filesystem_read_file`

---

## 🤖 Assistant

- **Tool:** `filesystem_search_files`

---

## 🤖 Assistant

- **Tool:** `filesystem_search_files`

---

## 🤖 Assistant

- **Tool:** `filesystem_search_files`

---

## 🤖 Assistant

- **Tool:** `filesystem_read_file`

---

## 🤖 Assistant

## 《为什么数据分析PA和数探查数这么准》核心总结

这篇文章是 DTC 数据分析团队对内部 AI 查数系统（**数据分析PA** 和 **数探**）精准度的技术复盘，核心回答了 **"为什么AI查数这么准？"**

### 一、核心结论（一句话）

> **"准"不是因为AI模型多聪明，而是因为在AI和数据库之间构建了一层机器可读的业务知识层（Data Catalog），把人查数的思考过程变成了机器可执行的规则链。**

---

### 二、Text-to-SQL普遍困境：四个"不知道"

AI不是不会写SQL，而是不懂业务。行业痛点集中在：

1. **不知道查哪张表** — 几十张表靠猜
2. **不懂字段业务语义** — brand vs shop_brand 傻傻分不清
3. **不知道隐性业务规则** — brand必须小写、转化率不能用AVG
4. **不知道什么时候该问用户** — "SKU"是单品还是组合包？不问就猜错

---

### 三、核心解法：Data Catalog + AI_HINT

#### 两层检索架构（渐进式披露）

| 层级 | 内容 | 作用 |
|------|------|------|
| **第一层** | `tables_metadata.json` | 语义索引，通过关键词精准定位目标表（几百token） |
| **第二层** | `tables/{表名}.md` | 深度文档，包含字段定义、业务规则、AI_HINT |

#### 最关键设计：AI_HINT（HTML注释嵌入指令）

每张表文档顶部用HTML注释嵌入三类标签，对人"隐形"、对AI完全可见：

| 类型 | 行为 | 例子 |
|------|------|------|
| **business_rule** | **强制执行**，不问用户 | brand必须lower()、订单三段拼接去重 |
| **ask_user_about** | **必须追问**确认 | SKU粒度、渠道口径、会员类型 |
| **auto_mapping** | **自动翻译**不打扰 | "付费会员"→prime_type IN(...) |

每张表还配有**正反示例**和"禁区"标注，防止AI根据训练数据中的常见模式写出错误SQL。

---

### 四、PA vs 数探：同源不同形

两者共享同一套 Data Catalog，区别在于：

| | **数据分析PA** | **数探** |
|----|------|------|
| 定位 | 深度分析系统化流程 | 快速对话即时响应 |
| 架构 | 5个Action Agent（需求澄清→SQL设计→查询→报告生成→更新）+ 独立sql-checker | 飞书群AI员工，@一下即出结果 |
| 特点 | 多轮澄清、独立验证、硬边界约束 | 快速、对话式、带记忆、即时可视化 |
| 场景 | 复杂分析、系统化看板、深度报告 | 日常查数、快速验证、"帮我看一眼" |

---

### 五、"准"的本质：系统性错误预防

**准确率 = 正确的表 × 正确的规则 × 消除歧义的澄清**

文章列举了7类典型错误（选错表、字段大小写、缺少分区过滤、订单重复计算、错误JOIN、术语歧义、聚合粒度错误），并且Data Catalog给每一类都设了防线。

---

### 六、深层思考：一次技术平权

这不是"替代分析师"，而是"释放分析师"：

- **过去**：分析师是"查数工具人"，价值在写SQL
- **现在**：AI承接80%重复取数需求
- **未来**：分析师进化为"知识工程师"——把业务规则编码成AI可执行的规则体系

> **最好的AI应用，不是让AI更聪明，而是让人的智慧以AI可理解的方式流动起来。**

这个模式可以复制到财务、法务、HR等职能——把专业知识从人脑搬到文件系统，用AI作为放大器，突破"一对一服务"的瓶颈。

---

## 🧑 User

这个Data Catalog需要人工维护吗？更新频率是多久一次？

---

## 🤖 Assistant

好问题。根据文档内容，我来拆解一下：

## Data Catalog 的维护方式

### 是不是人工维护？

**是的，但这是有意为之的设计，而非妥协。**

文档第7章明确把这一点定义为分析师角色的进化方向——从"查数工具人"升级为 **"知识工程师"**。维护 Data Catalog 本身就是分析师不可替代的核心价值：

> *"每写一条 AI_HINT，就让所有使用数探和 PA 的人受益；每补一条 ask_user_about，就预防了未来所有用户可能踩的坑。"*

### 更新频率呢？

文档没有直接写"每X天更新一次"，但从上下文可以推断出**事件驱动 + 持续迭代**的模式：

| 触发场景 | 需要更新的内容 | 频率 |
|----------|---------------|------|
| **新增数据表** | tables_metadata.json + 新表的 .md 文档 + 跨表关系 | 按需，表上线时 |
| **发现 AI 写错 SQL** | 补 AI_HINT business_rule / 加反面示例 | 发现问题即修复 |
| **用户问法有歧义** | 新增 ask_user_about 澄清触发器 | 对话复盘后补充 |
| **业务口径变更** | 更新字段定义、映射规则 | 业务变更时 |
| **查询模式积累** | 补充 use_cases、keywords 提高匹配精度 | 持续优化 |

本质上不是"定期维护"，而是 **"按需迭代"** ——每一次 AI 犯错或用户反馈，都是一次知识沉淀的机会。文中也提到：

> *"分析师的核心价值是：理解业务规则，并把这种理解编码成 AI 可执行的知识。"*

### 一句话总结

**人工维护，事件驱动，持续迭代。** 没有固定的时间周期，而是随着业务变化和 AI 犯错—修复循环不断进化。这恰恰是它的护城河——不是靠自动化一劳永逸，而是把"人的业务理解"持续注入系统。

---
