# AGENTS.md — AI 协作指南

给接手本项目的 AI 助手的工作说明。玩家向说明见 README.md，设计与规划见 `design/`。

## 项目一句话

复古像素风机甲格斗游戏（仿街霸 6 Modern 范式的键盘格斗），纯 Python + pygame，
**零外部资源**（角色/场景/音效/BGM 全程序化生成）。Windows 11 + Python 3.10 + pygame 2.1.2，
用仓库内 `build/.venv/Scripts/python.exe` 运行（系统 python 无 pygame）。

## 常用命令

```bash
# 全量回归（35 项，必过；约 60-90s，大头是 [20]/[30] 两个 AI 对战回归）
build/.venv/Scripts/python.exe main.py --selftest

# 调参用：缩小/放大平衡回归与对阵矩阵的局数
MECHDUEL_BALANCE_N=400 MECHDUEL_MATRIX_K=20 build/.venv/Scripts/python.exe main.py --selftest

# 无头冒烟（不跑 selftest 时验证窗口主循环各场景）
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy MECHDUEL_SMOKE=150 \
  MECHDUEL_SMOKE_SCENE=select build/.venv/Scripts/python.exe main.py
#   场景可选：select / keyconfig / training；加 --demo 直接进对战

python main.py                 # 真机运行
```

测试数据文件（keymap.json / stats.json）已 gitignore，**不要提交**；
selftest 不得产生这两个文件（[19] 用例用临时路径）。

## 文件地图

| 文件 | 职责 | 红线 |
|---|---|---|
| `main.py` | 入口：场景机、Fight（回合流程/判定/回放/街机链）、selftest | 规划上限 1500 行，当前约 1860（超限，继续新增功能优先落独立模块） |
| `settings.py` | **所有数值/键位/调色板/难度表/MOVE_DEFS 的单一来源** | 禁止把数值写进逻辑代码 |
| `mech.py` | Mech 状态机（15+ 态）、take_damage 判定链、MOVE_DEFS 消费 | 新状态需同步 current_frame_name/朝向锁 |
| `effects.py` | 弹体（直线/强化/弧线/延时雷）、粒子、Callout 弹字、震屏 | 只收数值参数，不 import 机甲 spec |
| `ai.py` | AI 控制器：输出虚拟 input（与真人同构），概率全部来自 AI_DIFFICULTY 表 | |
| `ui.py` | HUD/菜单/选人/键位/结算（纯渲染） | |
| `sfx.py` | 程序合成音效 + 3 首 chiptune BGM | |
| `assets.py` | 字符画→Surface；`build_background(theme)` 场地主题 | |
| `scene_flow.py` | 选人/键位设置/手柄/演示轮换/战绩 IO（阶段 8 自 main 拆出） | |
| `design/` | DESIGN_ROADMAP（总规划+进度）、MOVESET_COMBO_DESIGN（出招/连段设计）、NETPLAY_ASSESSMENT | 改动后同步进度勾选 |

## 核心设计约定（动代码前必读）

1. **AI 与真人输入同构**：AI 只写 `mech.input` 字典。新输入源（录像回放/联机/训练假人）
   都走同一条路——这是 [31] 回放一致性和平衡回归能无头跑的原因，不要破坏。
2. **判定先收集后结算**：`_combat` 中近战/投技同帧对拼必须先标记再统一结算
   （顺序结算会产生先手方偏置，历史上造成过 59% 胜率失衡）。
3. **伤害衰减在受击方**：`take_damage` 内按 `combo_count` 缩放；被防/受身/超时 30 帧重置。
4. **MOVE_DEFS 数据驱动**：新招式 = 加表行，不要在状态机里加硬编码分支。
5. **数值调整只改 settings.py**，改完跑 [20]（总胜率 45-55%）和 [30]（分对阵 35-65%，
   报警是警示不是失败）。超必杀差异化后生态对 violet 追踪弹伤害极其敏感
   （Lv1 dmg 4↔5 可全局翻转），动 violet 数值务必跨 2-3 组种子看趋势。
6. **新增常量后立即检查所有引用文件的 import**（历史上连犯两次 NameError）。

## 加内容的标准流程

- **新机甲**：settings 三处（`MECH_SPECS`+`super_levels`、`MOVE_DEFS`、`MECH_PALETTES`
  + 可选 `BOLT_PALETTES`）+ `MECH_ORDER`；UI（选人卡位/菜单排布）已公式化自适应。
  参考 [32] 的数据链断言；加完跑矩阵确认不入报警带。
- **新招式**：`MOVE_DEFS` 加行即可（旗标见 settings 注释）。
- **新场地**：`assets.THEMES` 加色板 + `settings.STAGES/STAGE_ORDER`。
- **新状态机分支**：同步 `current_frame_name`、朝向锁列表、`punishable`、`ANIMS`（如需）。

## 已知坑（.workbuddy/memory 的提炼，别再踩）

- **FakeKeys 键位串线**：selftest 的假键盘对双方玩家同源。`K_s` 会喂给 P1 的防御键——
  「P1 攻击 vs P2 防御」用例必须用 P1 键+P2 键组合（如 `K_j + K_DOWN`），
  否则 P1 的指令被自家防御优先级吞掉。
- **hitstop 吞测试按键**：命中顿帧期间 `step()` 直接返回，连按的键永远不 fresh。
  测取消/连段前先空 step 排空 `HITSTOP_FRAMES`。
- **双击判定读快照**：帧首先 `self._prev_taps = dict(self._tap_age)` 再记录本帧，
  判定（冲刺/绿冲）只读 `_prev_taps`——直接读 `_tap_age` 会把"本帧按下"当"上一次"，
  起跳帧会被冲刺吞掉。
- **镜像格统计**：[30] 矩阵镜像对阵按**先后手**计数（按机体会双侧记同一边，恒 0%）。
- **MECH_ORDER 长度敏感**：[18] 选人环绕、demo_pair、矩阵格数都随机体数走，加机体要同步。
- **K<20 时矩阵单元噪声 ±10%+**：别对单轮波动过度反应，看跨轮趋势再调参。
  [30] 种子固定（9000+k/9500+k），跨种子趋势用临时探针换 base 跑。
- **竖直弹必须显式 vx=0**：`Projectile` 不传 vx 会默认继承 facing×RANGED_SPEED，
  天降类弹体会横漂脱靶（[35] 落地时踩过）。
- **改流程/键位表后必须全量重跑 selftest**：[2] REPLAY 流程、[13] 键位断言都曾因
  改动后未重跑而陈旧。

## selftest 编号速查

[1]-[5] 基础循环/输入/格挡/超时 · [6]-[9] 投技/chip/空攻/后撤 · [10]-[11] 取消/受身 ·
[12]-[14] 超必杀×2/破防 · [15]-[16] 跳越/空中射击 · [17] 训练 · [18] 选人 ·
[19] 键位重映射 · [20] 平衡总回归（报警不失败） · [21]-[24] 连段地基 · [22] 拖尾 ·
[25]-[27] 出招表/特殊技/取消阶梯 · [28]-[29] 相位槽/三层超杀 · [30] 分对阵矩阵 ·
[31] 录像回放一致 · [32] 第四机甲 · [33] 街机流程 · [34] 同按合并/重击变体/击倒/格挡时停 ·
[35] 超必杀差异化（天降/追踪/瞬步/瞬移/霸体/贯穿）。

## 当前状态与遗留（2026-08-30）

- 路线图阶段 0-8 全部完成（见 DESIGN_ROADMAP.md 第五节勾选与第六节规划）；
  超必杀差异化落地（设计见 MOVESET_COMBO_DESIGN.md 第八节）——四机机制动词
  正交（冲撞抓取/贯穿/天降覆盖/追踪瞬步），官方矩阵 10 格全带零报警。
- 遗留：① verdant vs violet ~40%、azure vs violet ~45% 带缘（跨种子趋势，暂稳定）；
  ② Fight 判定/回放的细拆评估后暂缓（main.py 内聚 + 测试守门）；
  ③ 联机若立项，按 NETPLAY_ASSESSMENT.md 清单（先做 InputSource 抽象）。
- 提交规范：中文 `feat:/docs:/chore:/refactor:` 前缀，一批功能一提交；
  提交前 selftest 必须全绿。
