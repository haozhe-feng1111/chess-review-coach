---
version: 1
slug: "frontend-src-components-analysisworkbench-tsx"
primary_target: "frontend/src/components/AnalysisWorkbench.tsx"
related_targets: ["frontend/src/app/games/[id]/page.tsx", "route:/games/[id]", "frontend/src/components/EnginePanel.tsx", "frontend/src/components/VariationTree.tsx", "frontend/src/components/Board.tsx"]
---

# 可走子的复盘工作台

模式：Operate。沿用现有深蓝视觉系统，扩展棋盘交互和分析功能；没有替换视觉世界。

## 用户要求与方向

棋盘可以走子；用户可调思考时间、深度、Threads、Memory；按用户截图的组织方式，左侧大棋盘，右侧引擎状态与候选线在上、可缩进展开的分支棋谱在下。移动端依次堆叠。先交付本机体验，待用户确认后才能提交 PR。

截图是棋盘、引擎、棋谱的布局与交互参考。继续使用项目现有中文排版、蓝灰棋盘、蓝色引擎及金色教练说明；不照搬截图的紫色棋盘和对局内容。真实数据来自所打开的棋谱、本机引擎和 Lichess 查询。测试对局必须明确标为 QA，不冒充用户棋局。

## 方向合约

- FORM：用户参考图已指定组织结构；现有应用中的操作表面扩展，不进行新视觉世界的概念抽签。棋盘占桌面左侧约一半宽度，与候选线和树形棋谱构成同一工作区。
- MATERIAL：原生网页控件、清晰线条和国际象棋棋子；不需要图片资产或物理材质模拟。
- TYPE：沿用中文系统字体；着法 13–15 px、状态 11–12 px、评价数字 22–25 px；棋谱和引擎数字具有明确层级。
- OWN-WORLD：现有 navy 系统；实战与试走区分；Stockfish 实时分析、已保存复盘证据及真人胜率都标明来源和含义。
- SIGNATURE：可直接试走的棋盘，点候选线进入变化，主线旁保留可折叠的嵌套分支；高亮当前落点与所选着法。

## 行为约束

合法走子涵盖易位、吃过路兵和选择升变棋子；原棋谱不被覆盖。分支保存到本机数据库，并可导出 PGN。并发编辑发现版本冲突时保留草稿并提供导出恢复。引擎参数必须实际应用，显示实际深度、用时和内存，评分固定为白方视角。暂停、切换局面和离开页面应停止旧分析。Hash 明确为置换表而非进程内存上限。真人数据跟随当前局面。

## 已实现的结构与状态

- 棋盘上方显示走棋方、实战或分析分支以及当前着法；下方依次是棋谱导航、翻转、推荐箭头、返回分叉处和可展开的坐标输入。
- 右侧容器上半部常驻实时评分、白方视角、引擎状态、实际搜索指标和可展开候选线。设置在本区内展开，按分析方式显示对应预算字段，保留 Threads、Hash、MultiPV 与「应用并重新分析」。参数范围与行为以 PRODUCT.md 和使用说明为准。
- 「分支棋谱 / 真人数据库」切换下半部；分支树的实战主线分白黑两列，变化缩进并支持嵌套折叠，蓝色标记当前着法。真人统计沿用文字明确的白／和／黑结果，不重复外层卡片边框。
- 导出 PGN 位于标签行；保存状态、错误重试和草稿备份紧邻内容。下方「回看实战」保留历史复盘证据和教练说明，与白方视角的实时评分明确分开。
- 工作台在 900px 及以下堆叠；420px 及以下收紧头部与导航、缩小主评分和分支缩进。顶部导航适配窄屏，不让应用标语挤占操作宽度。

当前规范见 `frontend/DESIGN.md`：蓝灰棋盘、细分隔线、1px 引擎／教练来源边线、评分及状态字号均按实际实现记录。棋盘的合法落点圆点和吃子圆环是功能提示。

## 验证边界

完成评审覆盖五项检查，结论为 ship，无未解决的实质问题。桌面 1440px 视口中棋盘为 638px；手机 390px 视口中为 358px，无横向页面溢出。六张最终截图已经核对：

- `output/playwright/workbench-desktop.png`
- `output/playwright/workbench-settings.png`
- `output/playwright/workbench-mobile.png`
- `output/playwright/workbench-mobile-panel.png`
- `output/playwright/workbench-mobile-settings.png`
- `output/playwright/workbench-mobile-database.png`

一次检测记录位于 `output/playwright/workbench-detector.json`。上述截图是完成证据，QA 对局与当时显示的设置不属于产品默认配置，也不是运行所需数据。

本次交付已通过后端 250 项测试、98 项契约检查、前端 lint／类型／构建、真实 Stockfish 18 的预算与资源及取消验证，以及浏览器合法点选／拖动、特殊走法、嵌套分支、重载、候选线导入、冲突导出恢复和 Lichess 检查。这是本次验证记录，不是后续版本的自动保证。

没有未决视觉设计项；本机体验仍待用户确认。本次改动保留在本地，用户确认前不推送、不更新已有 PR。
