---
name: 国际象棋复盘教练 · 复盘界面
description: 沿用现有中文分析界面，以清晰来源、棋谱和数值支持复盘。
colors:
  background: "#0b1220"
  panel: "#111a2b"
  panel-soft: "#16223a"
  border: "#24314c"
  text: "#e6ebf5"
  muted: "#93a1bd"
  engine: "#4f9cf9"
  coach: "#d9a441"
  selected: "#245e9f"
  engine-text: "#a9cdfb"
  board-dark: "#4a5a78"
  board-light: "#c8d2e3"
  outcome-white: "oklch(96.8% 0.007 247.896)"
  outcome-draw: "oklch(70.4% 0.04 256.788)"
  outcome-black: "oklch(27.9% 0.041 260.031)"
typography:
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: "1.75rem"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: "1.25rem"
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: "1rem"
  notation:
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace'
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: "1rem"
  engine-score:
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace'
    fontSize: "25px"
    fontWeight: 600
    lineHeight: "32px"
  engine-score-compact:
    fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace'
    fontSize: "22px"
    fontWeight: 600
    lineHeight: "32px"
  tree-move:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "15px"
    fontWeight: 400
    lineHeight: "24px"
  branch-move:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "24px"
  status:
    fontFamily: '-apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif'
    fontSize: "11px"
    fontWeight: 400
rounded:
  control: "0.25rem"
  workbench-control: "6px"
  workbench-field: "5px"
  board: "0.5rem"
  soft-panel: "0.625rem"
  panel: "0.75rem"
  tag: "9999px"
spacing:
  tight: "0.25rem"
  control: "0.5rem"
  compact: "0.75rem"
  workbench: "14px"
  panel: "1rem"
  section: "1.25rem"
components:
  panel:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "{spacing.panel}"
  panel-soft:
    backgroundColor: "{colors.panel-soft}"
    rounded: "{rounded.soft-panel}"
    padding: "{spacing.compact}"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "0.5rem 0.75rem"
  button-outline-hover:
    backgroundColor: "{colors.panel-soft}"
  field:
    backgroundColor: "{colors.panel-soft}"
    textColor: "{colors.text}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "{spacing.control}"
  tag:
    backgroundColor: "{colors.panel-soft}"
    textColor: "{colors.muted}"
    rounded: "{rounded.tag}"
    padding: "0.1rem 0.55rem"
  button-workbench:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.text}"
    rounded: "{rounded.workbench-control}"
    padding: "7px 12px"
  button-workbench-hover:
    backgroundColor: "{colors.panel-soft}"
  button-primary:
    backgroundColor: "{colors.selected}"
    textColor: "#ffffff"
    rounded: "{rounded.workbench-control}"
    padding: "7px 12px"
  field-workbench:
    backgroundColor: "{colors.panel-soft}"
    textColor: "{colors.text}"
    rounded: "{rounded.workbench-field}"
    padding: "6px 8px"
  tree-move:
    typography: "{typography.tree-move}"
    rounded: "{rounded.control}"
    padding: "5px 8px"
  tree-move-active:
    backgroundColor: "{colors.selected}"
    textColor: "#ffffff"
    typography: "{typography.tree-move}"
    rounded: "{rounded.control}"
---

# Design System: 国际象棋复盘教练 · 复盘界面

## Overview

**Creative North Star: "证据优先的复盘工作台"**

这是对现有前端的记录，主要证据来自可走子的分析工作台、引擎候选线、分支棋谱、复盘证据和真人统计。沿用深蓝底色、紧凑中文排版及有边界的分析区域；新增内容应接入这一界面，而不另建视觉风格。

界面让用户在棋盘、着法和解释之间核对信息。颜色帮助辨认来源，正文和数值承担内容。页面的功能标题使用现有中文系统字体，不引入展示性大标题。

**Key Characteristics:**
- 深蓝背景与逐层稍亮的容器。
- 蓝色标识引擎证据，金色标识教练说明。
- 蓝灰棋盘、蓝色当前着法和可折叠分支形成连续工作区。
- 评分使用等宽字，走法保持清晰层级，统计有明确文字标签。
- 紧凑控件与可见边框，优先阅读和操作。

## Colors

以冷深蓝中性色构成大部分面积，蓝色与金色保留各自的来源含义。

### Primary
- **引擎蓝**（`engine`）：引擎证据左边线、引擎相关强调和真人统计控件的键盘焦点。
- **选中蓝**（`selected`）：当前树形着法及「应用并重新分析」操作的实色背景。
- **引擎浅蓝**（`engine-text`）：工作中状态、引擎标签和工作台键盘焦点。

### Secondary
- **教练金**（`coach`）：教练解释左边线和说明标签；不作为真人历史结果的胜负色。

### Neutral
- **夜蓝底色**（`background`）、**分析面板**（`panel`）、**内层面板**（`panel-soft`）：背景与内容层次。
- **边界蓝灰**（`border`）：容器边框、表格分隔和普通控件轮廓。
- **浅色正文**（`text`）与**辅助蓝灰**（`muted`）：主要内容和说明、来源、表头。
- **深蓝灰棋格**（`board-dark`）与**浅蓝灰棋格**（`board-light`）：棋盘交替底色，坐标使用相反棋格色；深蓝灰也用于分析区滚动条。
- **白方浅色**、**和棋灰色**、**黑方深色**（`outcome-white`、`outcome-draw`、`outcome-black`）：仅用于历史白胜、和棋、黑胜比例，保留 Tailwind 的原生 OKLCH 值。

**The Source Color Rule.** 引擎证据和教练说明使用各自的颜色及文字来源；真人历史结果使用独立的白、灰、深色比例条。

## Typography

**Body Font:** 优先中文系统字体，使用 frontmatter 中的完整回退顺序。
**Label/Mono Font:** 中文标签、候选线走法和分支树沿用系统字体；实时评分、候选线分数及真人统计中的 SAN 使用等宽字体。

### Hierarchy
- **Title**：页面及应用标题，使用已有的小幅字号提升。
- **Body**：内容与状态说明；面板标题使用同一字号并加至半粗体（600）。连续解释采用较松行高（1.625）。
- **Label**：筛选标签、表头、比例、来源和辅助文字。
- **Notation**：常见走法中的 SAN 使用半粗等宽字；引擎数值按所在行的正文大小显示。统计数字启用等宽数字排列。
- **Engine Score**：实时主评分使用最大的数值层级，窄屏改用 compact 规格；候选线分数使用半粗等宽字（13px）。
- **Tree Move / Branch Move**：实战主线比嵌套分支稍大；分支着法与候选线、设置字段同属紧凑阅读层级（13px）。
- **Status**：引擎状态、资源、回合表头、导出和保存反馈使用辅助层级；保留完整文字，不将此小字号用于正文或输入标签。

**The Written Meaning Rule.** 颜色旁保留可读文字；结果始终写出白胜、和棋、黑胜，不依赖用户推断条段含义。

## Layout

应用内容居中，最大宽度（80rem），左右留白（1rem）。工作台在（900px 以上）用两列呈现，棋盘列与分析列比例为（1.08:1），间距沿用 section；在（900px 及以下）依次堆叠，棋盘列最大宽度（620px）。实战复盘说明独立位于工作台下方，在（64rem 起）可分两列；详情证据在（40rem 起）可分两列。

页首允许换行，导航文字不拆开。窄屏应用标题为（1rem），从（40rem 起）恢复 title 规格并显示辅助标语。在（420px 及以下），工作台主评分缩小，状态另起行，边缘控件收紧，树分支减小缩进。

间距沿用四分之一 rem 的基础步长及常用半步；工作台内部复用 workbench 内边距。设置保留两列字段；分支树和数据库各自纵向滚动。树在桌面高（355px），堆叠时高（320px）；数据库最大高（480px）。候选线默认保留一行，用户可展开完整线路。具体工作区组织和状态见局部说明，不把该页列宽推广为所有页面的规则。

## Elevation & Depth

分析容器依靠背景明度和细边框区分层级，不使用投影。引擎和教练内容分别使用同源颜色的浅透明底色及左边线（1px）。嵌套分支用缩进、细边线和浅透明底色表达层级。升变选择浮层使用投影（`0 12px 30px #0008`）区分覆盖关系；不推广到普通面板。

界面没有装饰性渐变、发光或奖励动画。棋盘的合法落点圆点及吃子圆环由径向渐变绘制，是功能标记；不受装饰背景的限制。走子动画关闭，局面与选中状态直接更新。

## Shapes

主要面板使用 panel 圆角；嵌套内容使用 soft-panel 圆角；真人统计控件、树形着法和结果条使用 control 圆角。工作台按钮与输入使用各自略大的圆角，棋盘使用 board 圆角并裁剪边缘。标签保留胶囊形状。常规边框为细线（1px），表格用水平分隔线维持行的对应关系。

## Components

### Buttons
- 普通操作使用透明底、细轮廓和文字；真人统计的刷新按钮采用 frontmatter 的 outline 规格，悬停填入内层面板色。
- 工作台按钮使用分析面板底色，最小高度（36px），文字为（12px / 20px）；应用设置使用实色选中蓝。可用按钮悬停后改用内层底色和辅助色边框。
- 禁用按钮降低透明度（0.5）并显示禁用指针。独立统计区域的焦点使用引擎蓝；嵌入工作台后随工作台及复盘说明统一使用引擎浅蓝轮廓（2px，外偏移 3px）。
- 新工作台的方向、暂停、播放与折叠图标使用内联 SVG，图标按钮带可读名称；不采用字体符号替代图标。
- 连接 Lichess 是文字明确的边框链接，使用引擎蓝轮廓和浅蓝文字。它是授权状态下的操作，不是常驻主按钮。

### Inputs / Fields
- 原生选择框和月份输入框共用深色内层底色、细边框及完整宽度。标签保持可见，输入框允许在网格内收缩。
- 月份输入采用浏览器深色控件；错误提示出现在结果区域，保留用户选项。
- 引擎设置和坐标走法输入采用 field-workbench 规格，最小高度（36px）、字号（13px）及深色原生控件；标签始终可见或提供辅助技术名称。设置在引擎区内展开，修改后由明确的应用操作提交。

### Chips
- 小型来源或概念标签采用胶囊边框、紧凑内边距和单行文字。
- 引擎与教练变体分别使用同源浅色文字和半透明边框，文字仍说明来源。

### Cards / Containers
- 外层面板组织独立信息，内层面板承接补充内容。引擎与教练内容保留各自左边线；不把每一行数据再套成卡片。
- 工作台右列是一个连续容器：引擎区、标签、当前内容和状态区用细分隔线组织。嵌入的真人统计去掉自己的外边框、圆角和内边距，避免双层面板。

### Navigation
- 页首沿用文字链接和辅助色；悬停变亮。复盘动作仍围绕棋盘和选中着法展开，新统计面板不增加独立顶级导航。
- 工作台用「分支棋谱 / 真人数据库」标签切换下半区；当前标签使用浅色正文与底边线（2px）。键盘可切换标签，导出 PGN 保留在同一操作行。

### Interactive Board
- 棋盘保留坐标和黑白棋子；上一步的两格使用透明金色，选中起点使用透明蓝色，合法落点分别用圆点和吃子圆环提示。
- 棋格的键盘焦点在格内描边（3px），不挤动棋盘。升变时出现有名称的选择浮层，提供四种棋子与取消；具体规则由产品和使用说明维护。

### Engine & Variation Tree
- 实时主评分、白方视角、状态、实际深度及耗时位于引擎区上部。候选线分数占固定列，着法可逐步点击，右侧 SVG 控件展开整条线路。
- 主线按「回合 / 白方 / 黑方」排列。分支沿细线缩进，当前着法使用实色选中蓝；更深层不无限增加缩进。折叠按钮保留首着法和明确状态。
- 当前着法使用 `aria-current`，折叠使用 `aria-expanded`，保存反馈使用状态文本；错误与恢复动作保持可见。来源、评分视角和保存反馈不依赖颜色表达。

### Historical Outcomes
- 比例条按白胜、和棋、黑胜从左到右，条段共享外框。数值文本保证比例在无颜色时仍可理解。
- 表格的每个走法均使用同一套纵向三行标签；整体样本的标签允许横向排列并换行。
- 样本量、使用率和结果比例各有明确位置，棋谱使用等宽字。详细分母、状态和移动端规则留在局部说明。

## Do's and Don'ts

### Do:
- **Do** 沿用深蓝容器及引擎蓝、教练金的来源含义。
- **Do** 在统计中同时呈现样本量、文字结果和比例条。
- **Do** 让同类走法行保持相同的结果顺序和排版。
- **Do** 保留表单标签与真人统计区域的键盘焦点。
- **Do** 让棋盘当前局面、候选线与选中着法保持对应，并标明分析与保存状态。
- **Do** 在手机尺寸保留完整棋盘、可操作的设置及分支层级。

### Don't:
- **Don't** 把真人历史结果渲染成引擎评分或教练判断。
- **Don't** 用颜色替代白胜、和棋、黑胜文字。
- **Don't** 添加装饰性渐变、发光或奖励动画；棋盘的合法走子圆点和圆环是功能标记。
- **Don't** 把截图中的引擎参数、分数、对局内容或测试名称当作固定配置。

未纳入规范：旧线路组件的 Unicode 图标和截图里的演示参数、测试棋局；新工作台采用内联 SVG。11px 已作为工作台辅助状态字号单独记录，不推广为正文默认值。
