# 图表规格 Catalog

本文档用于固定数探机器人的图表和表格展示规范。后续新增图表类型、调整视觉风格、复核展示问题时，优先修改并遵循本文档。

## 总原则

- 图表服务于快速读数，不做装饰性设计。
- 同一种图表类型保持固定尺寸、颜色、网格、标注和排序规则。
- 图表样式、颜色、TopN、字体、尺寸由 `src/data_agent/visualization/chart_policy.json` 固定；LLM 不决定视觉样式。
- 查询结果先通过 `infer_chart_spec(...)` 归类，再由 `render_chart(...)` 按 policy 渲染。
- 若图表无法准确表达数据，例如混合单位但没有合适拆分，优先展示表格，不为了美观强行画图。
- 百分比指标必须以百分比形式展示，例如 `0.1234` 展示为 `12.34%`。
- 金额、销量、Sessions 等数量型指标使用千分位。
- 图表标题应短，图表内不放长解释；口径说明放在卡片正文。
- 当分类标签较长，例如 ASIN、SKU、campaign name，优先使用横向柱状图，避免 x 轴拥挤。

## 固定视觉策略

- 整体风格参考成熟 BI 工具的工作台图表：白底、浅网格、低装饰、清晰标签、固定语义色。
- 主色：蓝色 `#2563EB`，用于金额、花费和默认主指标。
- 销售/正向指标：绿色 `#16A34A`。
- 比率指标：橙色 `#F97316`，例如 ACoS、TACOS、CTR、转化率。
- 数量指标：青色 `#14B8A6`，例如 orders、sessions、clicks、impressions。
- 下滑/损失指标：红色 `#DC2626`。
- 字体优先使用 CJK 友好的 sans-serif 字体，避免中文标题或轴标签乱码。
- 不使用渐变、3D、阴影或装饰性背景。通用自动图表避免双轴；只有固定 recipe 且字段组合明确时才允许双轴。

## Visualization Recipes

查询结果会先经过 recipe matcher；命中特定字段组合时走专用渲染，不再退回通用 line/bar。

### monthly_mom_sales_units

适用字段：

- `month`
- `sales` / `revenue`
- `units`
- `sales_change_pct` / `sales_mom_change_pct`
- `units_change_pct` / `units_mom_change_pct`

展示规则：

- 使用 ggplot-like 双 y 轴组合图。
- 左 y 轴展示销量，使用蓝色柱图。
- 右 y 轴展示销售额，使用绿色折线和圆点。
- 销量值和销量环比 pct 标注在柱内，使用白色文字避免遮挡折线。
- 销售额值和销售额环比 pct 标注在线点上方；销售额环比正数绿色、负数红色，空值不展示。
- 必须展示图例、左右轴标题和颜色绑定，避免用户误读两个单位。
- 表格图片和原始数据仍保留。

## 指标格式

| 指标类型 | 识别关键词 | 展示格式 | 示例 |
| --- | --- | --- | --- |
| 百分比 | `pct`, `rate`, `ratio`, `percent`, `percentage`, `cvr`, `conversion`, `acos`, `roas`, `ctr`, `tacos`，以及 `_pct` / `_percentage` 后缀 | `12.34%` | `0.1234 -> 12.34%` |
| 金额 | `sales`, `revenue`, `amount`, `price`, `cost`, `spend` | `$1,234.56` | `1234.56 -> $1,234.56` |
| 件数/次数 | `units`, `quantity`, `orders`, `sessions`, `clicks`, `impressions`, `views` | `1,234` | `1234 -> 1,234` |
| 其他数值 | 未匹配 | `1,234.56` | `1234.56 -> 1,234.56` |

## 柱状图

- 默认用于 Top N、排名、分类对比。
- 默认使用横向柱状图，分类标签在 y 轴，指标数值在 x 轴。
- 默认展示前 15 条，由 `chart_policy.json` 控制。
- 默认按指标值降序排序；如果指标名包含 `decline`、`drop`、`decrease`，应按下滑量降序。
- 数值标签展示在柱末端，使用指标格式化规则。
- 颜色按指标语义固定映射，例如 spend 用蓝色、sales 用绿色、rate 用橙色。
- 去掉上边框和右边框，保留浅色 x 轴网格。

## 折线图

- 默认用于按日期、周、月的趋势。
- 用户问题包含“趋势/走势/每天/每日/按日/daily”时优先使用折线图。
- 日趋势表格最多完整展示 31 行，以覆盖自然月 30/31 天；不要只展示前 10 天。
- x 轴按时间升序。
- 每个指标一条线，最多 4 条。
- 点标记保留，但标注只在最后一个点展示，避免拥挤。
- 百分比指标使用百分比 y 轴。
- 多指标单位不一致时，应拆图或只画主指标。

## 表格

- Feishu 结果表优先渲染为图片表格，展示完整列和网格线；原生 `column_set` 只作为图片上传失败时的 fallback。
- 表格图片和 Markdown/原生 fallback 使用同一套格式化规则。
- 百分比字段显示为百分比。
- 空值显示为 `-`。
- 长文本截断，完整内容可通过后续下钻查看。
- 列名只做下划线转空格，不截断（截断会让用户误判列含义）。
- 默认不截断列；所有返回列都应展示。行数仍遵循当前 intent 的 `table_max_rows`，避免超大图片不可读。
- 数值类型识别用 `numbers.Number`，覆盖 PostgreSQL `numeric` 类型经 psycopg 回到的 `Decimal`；否则 `acos / br_sales` 这类会以原始字符串 `0.9687 / 86732.9100` 显示。

## 图表 y 轴选取优先级

`choose_chart_columns(data, columns, prefer_y=...)` 按以下顺序决定 y 轴：

1. **用户问题指标意图**（`infer_metric_column(user_text, columns)`）：扫 `INTENT_HINTS` 关键词表（"广告花费" → `ad_spend`、"广告销售" → `ad_sales`、"转化率" → `conversion_rate` 等），命中且对应列存在就用。这是 LLM `ORDER BY` 写错时的纠正层。
2. **SQL 的 ORDER BY 第一列**（`parse_order_by_column(sql)`）：去掉表别名前缀和 ASC/DESC。
3. **结果里最后一列数值列**：兜底。

意图优先于 ORDER BY 是有意为之：用户说"广告花费最多"时，即便 LLM 误写 `ORDER BY br_sales DESC`，图也按 `ad_spend` 排。

## 当前暂不支持

- 双轴图。
- 堆叠图。
- 复杂交互图。
- 同一张图混合金额和百分比。

这些能力后续可以单独评估，不应通过临时拼接实现。
