# -*- coding: utf-8 -*-
"""《钢铁对决 MECH DUEL》全局配置：分辨率、按键映射、战斗数值、调色板。

所有可调参数集中于此，方便平衡性调整与扩展。
"""

# ---------------------------------------------------------------- 窗口与帧率
INTERNAL_W, INTERNAL_H = 480, 270   # 内部像素分辨率（复古 16:9）
SCALE = 3                           # 运行时整数倍放大
WINDOW_W, WINDOW_H = INTERNAL_W * SCALE, INTERNAL_H * SCALE
FPS = 60
TITLE = "MECH DUEL 钢铁对决"

# ---------------------------------------------------------------- 场地
GROUND_Y = 236          # 地面（机甲脚底基准线）
ARENA_LEFT = 20         # 左右墙
ARENA_RIGHT = INTERNAL_W - 20
ROUND_TIME = 60         # 每局秒数
ROUNDS_TO_WIN = 2       # 三局两胜

# ---------------------------------------------------------------- 玩家按键
# P1：A/D 移动  W 跳  S 防御  J 轻斩  U 重击  K 光束  L 投技  I 超必杀
#     （双击 A/D 冲刺/后撤；方向+键 = Modern 特殊技，见 MOVE_DEFS）
import pygame as _pg

P1_KEYS = {
    "left":   _pg.K_a,
    "right":  _pg.K_d,
    "jump":   _pg.K_w,
    "block":  _pg.K_s,
    "melee":  _pg.K_j,
    "heavy":  _pg.K_u,
    "ranged": _pg.K_k,
    "throw":  _pg.K_l,
    "super":  _pg.K_i,
}
P2_KEYS = {
    "left":   _pg.K_LEFT,
    "right":  _pg.K_RIGHT,
    "jump":   _pg.K_UP,
    "block":  _pg.K_DOWN,
    "melee":  _pg.K_KP1,
    "heavy":  _pg.K_KP5,
    "ranged": _pg.K_KP2,
    "throw":  _pg.K_KP3,
    "super":  _pg.K_KP4,
}
# 默认键位备份（按键设置界面「恢复默认」用）
DEFAULT_P1_KEYS = dict(P1_KEYS)
DEFAULT_P2_KEYS = dict(P2_KEYS)
KEYMAP_FILE = "keymap.json"     # 按键重映射持久化文件


def save_keymap(path=KEYMAP_FILE):
    """把当前键位表写入 JSON（阶段4 按键重映射）。"""
    import json
    data = {"p1": {a: int(c) for a, c in P1_KEYS.items()},
            "p2": {a: int(c) for a, c in P2_KEYS.items()}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def load_keymap(path=KEYMAP_FILE):
    """启动时读取重映射键位；文件不存在/损坏返回 False 并保留默认。"""
    import json
    import os
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for act, code in data.get("p1", {}).items():
            if act in P1_KEYS:
                P1_KEYS[act] = int(code)
        for act, code in data.get("p2", {}).items():
            if act in P2_KEYS:
                P2_KEYS[act] = int(code)
        return True
    except Exception:
        return False


# 选人界面固定顺序
MECH_ORDER = ["garnet", "azure", "verdant", "violet"]

# ---------------------------------------------------------------- 机甲规格
# 三机甲共用像素骨架，配色与数值不同；每台各有专属超必杀与专属特性
MECH_SPECS = {
    "garnet": {
        "name": "GARNET",
        "cn_name": "红莲",
        "palette": "p1",
        "hp": 106,
        "walk_speed": 1.35,      # px / frame
        "jump_power": 6.0,       # 提高跳跃高度，保证能越过对手头顶（体高 56px）
        "air_jumps": 0,
        "melee_damage": 10,
        "melee_range": 40,       # 判定盒前端离中心的距离
        "knockback": 3.6,
        "bolt_color": "hot",     # 光束弹配色（红橙）
        "throw_damage": 18,      # 投技伤害（无视格挡）
        "super_name": "熔核冲击",  # 超必杀：向前冲撞，命中重创击飞（伤害走 GARNET_SUPER_DMG）
        "super_levels": {
            1: {"name": "熔核冲击", "total": 40, "active": (8, 24),
                "rush": 6.0, "dmg": 30},                    # = GARNET_SUPER_DMG
            2: {"name": "地裂冲击", "total": 44, "active": (8, 24),
                "rush": 6.0, "dmg": 34, "wave": True},
            3: {"name": "熔核天崩", "total": 48, "active": (8, 24),
                "rush": 6.0, "dmg": 50, "grab": True},
        },
    },
    "azure": {
        "name": "AZURE",
        "cn_name": "苍鳍",
        "palette": "p2",
        "hp": 105,
        "walk_speed": 1.7,
        "jump_power": 6.3,       # 提高跳跃高度，保证能越过对手头顶（体高 56px）
        "air_jumps": 0,
        "melee_damage": 10,
        "melee_range": 40,
        "knockback": 3.2,
        "bolt_color": "cool",    # 光束弹配色（青蓝）
        "throw_damage": 15,      # 投技伤害（无视格挡）
        "super_name": "苍蓝齐射",  # 超必杀：连发三道强化光束（伤害走 AZURE_SUPER_BOLT_DMG）
        "super_levels": {
            1: {"name": "苍蓝齐射", "total": 40, "shots": (10, 18, 26), "dmg": 8},
            2: {"name": "疾影齐射", "total": 44, "shots": (10, 18, 26), "dmg": 9,
                "drift": 0.8},
            3: {"name": "苍穹风暴", "total": 74,
                "shots": tuple(range(10, 70, 5)), "dmg": 4},   # 12 段 ×4
        },
    },
    "verdant": {
        "name": "VERDANT",
        "cn_name": "翠岚",
        "palette": "p3",
        "hp": 118,
        "walk_speed": 1.55,
        "jump_power": 6.6,       # 全场最高跳跃
        "air_jumps": 1,          # 专属机动：空中二段跳
        "melee_damage": 12,
        "melee_range": 40,
        "knockback": 3.4,
        "bolt_color": "acid",    # 光束弹配色（酸绿）
        "throw_damage": 16,
        "super_name": "翠暴轰炸",  # 超必杀：两发弧线榴弹（伤害走 VERDANT_SUPER_BOLT_DMG）
        "super_levels": {
            1: {"name": "翠暴轰炸", "total": 40, "shots": (12, 24), "dmg": 12},
            2: {"name": "连天翠暴", "total": 46, "shots": (10, 16, 22, 28),
                "dmg": 9},
            3: {"name": "世界树降临", "total": 66,
                "shots": tuple(range(10, 42, 4)), "dmg": 6},   # 8 段 ×6
        },
    },
    "violet": {
        "name": "VIOLET",
        "cn_name": "紫电",
        "palette": "p4",
        "hp": 102,
        "walk_speed": 1.8,       # 全场最快移速
        "jump_power": 6.2,
        "air_jumps": 0,
        "melee_damage": 10,
        "melee_range": 40,
        "knockback": 3.0,
        "bolt_color": "violet",  # 光束弹配色（电紫）
        "throw_damage": 16,
        "super_name": "紫电狂涛",  # 超必杀：五连追踪小电弹
        "super_levels": {
            1: {"name": "紫电狂涛", "total": 42,
                "shots": (10, 15, 20, 25, 30), "dmg": 5},
            2: {"name": "雷霆万钧", "total": 44, "active": (8, 24),
                "rush": 6.4, "dmg": 36},
            3: {"name": "九天雷罚", "total": 64,
                "shots": tuple(range(10, 60, 5)), "dmg": 5},  # 10 段 ×5
        },
    },
}

# ---------------------------------------------------------------- 战斗数值
GRAVITY = 0.28                  # px/frame^2
MELEE_WINDUP = 9                # 前摇帧
MELEE_ACTIVE = 7                # 判定帧
MELEE_RECOVER = 12              # 后摇帧
MELEE_COOLDOWN = 18             # 攻击结束后的硬直冷却
RANGED_COOLDOWN = 36
RANGED_DAMAGE = 6
RANGED_COST = 35                # 能量消耗
RANGED_SPEED = 4.2              # 光束弹速度
ENERGY_MAX = 100
ENERGY_REGEN = 0.22             # 每 frame 回复
BLOCK_REDUCE = 0.2              # 格挡后受到伤害比例（80% 减免）
HURT_STUN = 15                  # 受击硬直帧
HITSTOP_FRAMES = 5              # 命中顿帧
KO_SLOW_FRAMES = 80             # KO 慢镜头时长
PUSHBOX_W = 22                  # 机体推挤盒宽度
MIN_SEPARATION = 26             # 两机甲最小间距
JUMP_SEP_Y = 30                 # 推挤生效的最大高度差（跳过对手的关键窗口）
JUMP_BOOST = 1.3                # 起跳水平动量加成（空中速度上限同步放宽）

# ---------------------------------------------------------------- 阶段1：投技/冲刺/后撤/空中攻击
# 投技：抓取范围内地面目标，无视格挡（可被跳跃/后撤步躲开）
THROW_RANGE = 36                # 抓取距离（中心距）
THROW_TOTAL = 26                # 投技整套帧数（落空也有大硬直，可被惩罚）
THROW_HIT_T = 8                 # 第几帧判定抓取
THROW_COOLDOWN = 45             # 投技冷却
THROW_VX = 4.4                  # 被投者水平飞出速度
THROW_VY = -4.6                 # 被投者浮空初速
THROWN_LAND_STUN = 18           # 被投落地附加硬直
# 冲刺 / 后撤步：双击同方向触发
TAP_WINDOW = 14                 # 双击判定窗口（帧）
DASH_FRAMES = 14                # 前冲帧数（第 4 帧起可取消出攻击）
DASH_SPEED = 3.2
BACKSTEP_FRAMES = 16            # 后撤步帧数
BACKSTEP_SPEED = 3.8
BACKSTEP_INVULN = (2, 11)       # 无敌帧区间 [起, 止)
# 空中攻击：跳跃中按下近战键 → 下劈
AIR_MELEE_TOTAL = 20
AIR_MELEE_ACTIVE = (4, 14)      # 判定帧区间
AIR_MELEE_MULT = 0.75           # 伤害倍率（基于 melee_damage）

# ---------------------------------------------------------------- 阶段2：取消连段/浮空受身/超必杀/破防
# 取消连段：斩击命中后，后摇期间可取消出光束/跳跃（未命中不可取消）
CANCEL_ALLOWED = "hit"          # 仅命中后允许取消
# 浮空追打（juggle）：空中目标被命中 → 向上刷新浮空
JUGGLE_VY = -2.8
# 受身：落地硬直中按跳跃键提前起身，带起身无敌
WAKE_INVULN = 20                # 受身起身无敌帧
# 超必杀：独立 SUPER 槽（3 层 ×100），命中/受击/格挡积攒，Lv1-3 依次消耗 100/200/300
SUPER_MAX = 300
SUPER_COST = 100
SUPER_GAIN_HIT = 18             # 命中积攒
SUPER_GAIN_TAKE = 12            # 受击积攒
SUPER_GAIN_BLOCK = 6            # 格挡积攒
SUPER_TOTAL = 40                # 超必杀动作总帧数
SUPER_INVULN_FRAMES = 20        # 发动后无敌帧（含定格演出时间）
SUPER_FLASH_FRAMES = 26         # 发动瞬间全局定格（演出）
GARNET_SUPER_DMG = 30             # 熔核冲击冲撞伤害
GARNET_SUPER_ACTIVE = (8, 24)   # 冲撞判定帧区间
AZURE_SUPER_SHOTS = (10, 18, 26)  # 三连光束发射帧
AZURE_SUPER_BOLT_SPEED = 5.2
AZURE_SUPER_BOLT_DMG = 8          # 三连光束单发伤害
# 破防槽（防御槽）：满槽起手，格挡消耗，耗尽则防御崩坏（大硬直，期间无法防御）
GUARD_MAX = 100
GUARD_REGEN = 0.15              # 每帧回复
GUARD_GAIN_MELEE = 22           # 格挡一次近战
GUARD_GAIN_BOLT = 11            # 格挡一发光束
GUARD_BREAK_STUN = 55           # 破防硬直帧

# ---------------------------------------------------------------- 阶段5A：连段地基（受防硬直/伤害衰减/惩罚反击/投拆）
# 设计依据 design/MOVESET_COMBO_DESIGN.md §2
BLOCK_STUN = 12                 # 受防硬直帧（被防轻斩约 -6、重击约 -12：防守方获得有限反击窗而非立即惩罚）
BLOCK_PUSH = 2.2                # 被防推距初速 px/frame
COMBO_SCALE_STEP = 0.15         # 连段每段伤害衰减
COMBO_SCALE_MIN = 0.40          # 衰减下限
COMBO_RESET_FRAMES = 30         # 脱离受击 30 帧重置连段
PUNISH_MULT = 1.2               # 惩罚反击伤害倍率（命中后摇/落空投/破防硬直）
PUNISH_STUN_BONUS = 4           # 惩罚反击附加硬直（地面受击路径）
THROW_TECH_WINDOW = 6           # 拆投判定窗（抓取判定前 N 帧内按投）
THROW_TECH_PUSH = 3.0           # 拆投双方后退距离 px
THROW_TECH_LAG = 6              # 拆投后投方附加硬直帧（-6 帧不利）


def combo_scale(count):
    """连段第 count+1 段的伤害倍率（count 为受击方此前已承受段数）。"""
    return max(COMBO_SCALE_MIN, 1.0 - COMBO_SCALE_STEP * count)


# ---------------------------------------------------------------- 阶段6A：MOVE_DEFS 出招表（数据驱动）
# 每技一行：windup/active/recover 帧 + dmg + 属性旗标。mech.py 读表出招，新增技=加行。
# 键位指令（Modern 范式）：U=重击 →+U=前重 ←+U=后重 空中U=空中重；
#   冲刺中J=dash_light（机体专属突进技）；→+K=fwd_bolt ←+K=back_bolt；
#   轻+束同按+前方向=OD 强化技（6B 接入，耗 1 格 Drive）。
# 旗标：launch=命中击倒/浮空；guard_mult=对防御槽伤害倍率；lunge/rush=判定相突进速度；
#   armor=全程霸体（吃半伤不中断）；pull=命中拉近 px；bolt=弹体参数（speed/vy/grav/
#   dist 射程/delay 静置延时/shots 连发数/interval 连发间隔/mine 落地布雷）。
SPECIAL_CD = 30                  # 特殊技结束后的射击系共享冷却
MOVE_DEFS = {
    "garnet": {
        "heavy":      {"name": "重击",     "windup": 14, "active": 5,  "recover": 20, "dmg": 18, "range": 44, "launch": True},
        "fwd_heavy":  {"name": "烈突",     "windup": 16, "active": 6,  "recover": 24, "dmg": 22, "range": 48, "guard_mult": 1.5, "lunge": 1.2},
        "back_heavy": {"name": "横扫",     "windup": 15, "active": 6,  "recover": 22, "dmg": 18, "range": 46, "launch": True},
        "air_heavy":  {"name": "踏压",     "windup": 8,  "active": 8,  "recover": 8,  "dmg": 15, "range": 36, "launch": True},
        "dash_light": {"name": "装甲冲撞", "windup": 12, "active": 8,  "recover": 22, "dmg": 13, "range": 40, "armor": True, "launch": True, "rush": 3.2},
        "fwd_bolt":   {"name": "熔核喷发", "windup": 10, "active": 4,  "recover": 18, "dmg": 10, "bolt": {"speed": 3.2, "dist": 90}},
        "od":         {"name": "熔核喷发EX", "windup": 8, "active": 6, "recover": 18, "dmg": 14, "bolt": {"speed": 3.4, "dist": 140, "shots": 2, "interval": 6}},
        "back_bolt":  None,
    },
    "azure": {
        "heavy":      {"name": "重击",     "windup": 12, "active": 5,  "recover": 18, "dmg": 18, "range": 42, "launch": True},
        "fwd_heavy":  {"name": "突蹴",     "windup": 13, "active": 6,  "recover": 20, "dmg": 21, "range": 46, "lunge": 1.4},
        "back_heavy": {"name": "对空斩",   "windup": 10, "active": 6,  "recover": 18, "dmg": 16, "range": 42, "launch": True},
        "air_heavy":  {"name": "俯冲刃",   "windup": 7,  "active": 8,  "recover": 6,  "dmg": 14, "range": 34, "launch": True},
        "dash_light": {"name": "相位刺",   "windup": 10, "active": 6,  "recover": 16, "dmg": 14, "range": 40, "rush": 3.6},
        "fwd_bolt":   {"name": "裂地光刃", "windup": 12, "active": 4,  "recover": 22, "dmg": 7,  "bolt": {"speed": 4.4, "dist": 200}},
        "od":         {"name": "相位刺EX", "windup": 8,  "active": 8,  "recover": 18, "dmg": 18, "range": 52, "rush": 4.0, "launch": True},
        "back_bolt":  None,
    },
    "verdant": {
        "heavy":      {"name": "重击",     "windup": 13, "active": 5,  "recover": 19, "dmg": 19, "range": 43, "launch": True},
        "fwd_heavy":  {"name": "鞭腿",     "windup": 15, "active": 6,  "recover": 21, "dmg": 22, "range": 45, "launch": True, "lunge": 1.1},
        "back_heavy": {"name": "扫击",     "windup": 14, "active": 6,  "recover": 20, "dmg": 17, "range": 44, "launch": True},
        "air_heavy":  {"name": "种子散布", "windup": 6,  "active": 10, "recover": 8,  "dmg": 4,  "range": 30, "bolt": {"speed": 0, "vy": 0.6, "delay": 45, "drop": True, "shots": 2, "interval": 6}},
        "dash_light": {"name": "藤蔓勾拉", "windup": 11, "active": 6,  "recover": 18, "dmg": 14, "range": 42, "pull": 34, "launch": True},
        "fwd_bolt":   {"name": "弧线榴弹", "windup": 12, "active": 4,  "recover": 18, "dmg": 10, "bolt": {"speed": 3.4, "vy": -4.0, "grav": 0.24}},
        "od":         {"name": "弧线榴弹EX", "windup": 10, "active": 4, "recover": 18, "dmg": 9,  "bolt": {"speed": 2.8, "vy": -4.0, "grav": 0.24, "shots": 2, "interval": 8}},
        "back_bolt":  {"name": "种子地雷", "windup": 12, "active": 4,  "recover": 20, "dmg": 8,  "bolt": {"speed": 0, "delay": 60, "mine": True}},
    },
    "violet": {
        "heavy":      {"name": "雷击",     "windup": 12, "active": 5,  "recover": 19, "dmg": 18, "range": 42, "launch": True},
        "fwd_heavy":  {"name": "雷突",     "windup": 13, "active": 6,  "recover": 20, "dmg": 20, "range": 46, "lunge": 1.5},
        "back_heavy": {"name": "电扫",     "windup": 11, "active": 6,  "recover": 18, "dmg": 15, "range": 42, "launch": True},
        "air_heavy":  {"name": "雷坠",     "windup": 7,  "active": 8,  "recover": 6,  "dmg": 13, "range": 34, "launch": True},
        "dash_light": {"name": "雷殛突进", "windup": 9,  "active": 6,  "recover": 14, "dmg": 13, "range": 40, "rush": 4.2, "launch": True},
        "fwd_bolt":   {"name": "电光球",   "windup": 11, "active": 4,  "recover": 18, "dmg": 8,  "bolt": {"speed": 3.8, "dist": 160}},
        "od":         {"name": "雷暴EX",   "windup": 9,  "active": 4,  "recover": 18, "dmg": 8,  "bolt": {"speed": 4.0, "dist": 160, "shots": 3, "interval": 4}},
        "back_bolt":  None,
    },
}

# ---------------------------------------------------------------- 阶段6B：相位槽（Drive）+ 三层超必杀
DRIVE_MAX = 120                  # Drive 槽（HUD 6 格）
DRIVE_REGEN = 0.05               # 每帧缓回
DRIVE_COST = 20                  # 1 格：OD 强化技 / Drive Rush
DRIVE_REVERSAL_COST = 40         # 2 格：逆转反技
DRIVE_HIT_LOSS = 12              # 受击流失
DRIVE_BLOCK_LOSS = 6             # 被防流失
DRIVE_PARRY_GAIN = 25            # 完美格挡回复
DRIVE_HIT_GAIN = 6               # 命中回复
PARRY_WINDOW = 5                 # 完美格挡判定窗（按防后 N 帧内被击）
PARRY_STAGGER = 12               # 被完美格挡后攻击方踉跄帧
PARRY_RUSH_WINDOW = 30           # 完美格挡后免费绿冲窗口（帧）
RUSH_FRAMES = 20                 # Drive Rush 时长
RUSH_SPEED = 4.5
DIM_CHARGE_MIN = 12              # Drive 冲击最小蓄力帧
DIM_CHARGE_MAX = 45              # 蓄力上限（自动出手）
DIM_DMG = 28
DIM_RANGE = 50
DIM_GUARD_MULT = 3.0             # 被防时对防御槽伤害倍率
DREV_DMG = 14                    # 逆转反技
DREV_RANGE = 42
DREV_FRAMES = (8, 4, 16)
WALL_SPLASH_STUN = 40            # 墙崩眩晕帧（GBREAK 复用）
REVERSAL_DEF = {"name": "逆转反技", "windup": 8, "active": 4, "recover": 16,
                "dmg": DREV_DMG, "range": DREV_RANGE, "launch": True}

# ---------------------------------------------------------------- 阶段3：第三机甲专属超必杀 / AI 难度
VERDANT_SUPER_SHOTS = (12, 24)    # 两发榴弹发射帧
VERDANT_SUPER_BOLT_DMG = 12       # 单发榴弹伤害
VERDANT_SUPER_VY = -4.8           # 榴弹初速（向上）
VERDANT_SUPER_GRAV = 0.24         # 榴弹重力（弧线弹道）
# AI 难度三档：反应概率 / 决策间隔 / 失误率全部入表，架构不动
AI_LEVELS = ("easy", "normal", "hard")   # 菜单 TAB 轮换顺序
AI_DIFFICULTY = {
    "easy":   {"react_melee": 0.015, "react_bolt": 0.020, "grab_block": 0.015,
               "grab_near": 0.35, "dodge_throw": 0.015, "decide": (16, 30),
               "mistake": 0.30, "super_p": 0.20, "melee_p": 0.30, "block_p": 0.25,
               "heavy_p": 0.10, "special_p": 0.08, "od_p": 0.0, "impact_p": 0.0,
               "parry_p": 0.0},
    "normal": {"react_melee": 0.035, "react_bolt": 0.050, "grab_block": 0.060,
               "grab_near": 0.60, "dodge_throw": 0.060, "decide": (8, 16),
               "mistake": 0.10, "super_p": 0.45, "melee_p": 0.50, "block_p": 0.20,
               "heavy_p": 0.20, "special_p": 0.15, "od_p": 0.02, "impact_p": 0.03,
               "parry_p": 0.01},
    "hard":   {"react_melee": 0.075, "react_bolt": 0.100, "grab_block": 0.120,
               "grab_near": 0.75, "dodge_throw": 0.140, "decide": (5, 11),
               "mistake": 0.04, "super_p": 0.60, "melee_p": 0.65, "block_p": 0.10,
               "heavy_p": 0.30, "special_p": 0.22, "od_p": 0.05, "impact_p": 0.06,
               "parry_p": 0.03},
}

# ---------------------------------------------------------------- 阶段7：场地 / 战绩
STAGE_ORDER = ("night", "dawn")  # 菜单 E 键轮换
STAGES = {
    "night": {"name": "废墟月夜"},
    "dawn":  {"name": "熔炉黎明"},
}
STATS_FILE = "stats.json"        # 战绩存档（对局数/胜场/常用机体）

# ---------------------------------------------------------------- 阶段4：KO 高光回放
REPLAY_FRAMES = 100             # 回溯快照帧数
REPLAY_HOLD = 2                 # 每帧快照播放驻留（慢放倍率的倒数）

# ---------------------------------------------------------------- 颜色
COLORS = {
    "black":       (12, 10, 18),
    "white":       (236, 240, 244),
    "hud_frame":   (240, 240, 240),
    "hud_bg":      (24, 22, 34),
    "hp_p1":       (232, 76, 61),
    "hp_p2":       (66, 134, 234),
    "hp_ghost":    (250, 214, 90),
    "energy":      (96, 220, 160),
    "energy_low":  (90, 90, 110),
    "timer":       (250, 220, 120),
    "banner":      (250, 240, 220),
    "banner_sh":   (30, 16, 40),
    "accent1":     (255, 102, 85),
    "accent2":     (96, 176, 255),
    "dust":        (150, 140, 150),
    "spark_hot":   (255, 190, 80),
    "spark_cool":  (120, 230, 255),
    "smoke":       (110, 110, 125),
}

# 机甲像素图调色板（字符 -> RGBA）。O=描边 A=主装甲 B=暗部 L=亮部
# J=关节灰 C=传感器 S=光剑刃 G=武器深色 E=能量色 W=白色高光
MECH_PALETTES = {
    "p1": {   # GARNET 红莲
        "O": (24, 14, 20),
        "A": (200, 62, 50),
        "B": (128, 34, 34),
        "L": (240, 126, 92),
        "J": (96, 100, 112),
        "C": (255, 214, 64),
        "S": (255, 170, 190),
        "G": (56, 58, 70),
        "E": (255, 150, 60),
        "W": (250, 240, 235),
    },
    "p2": {   # AZURE 苍鳍
        "O": (12, 16, 28),
        "A": (62, 126, 206),
        "B": (34, 68, 138),
        "L": (128, 188, 244),
        "J": (96, 100, 112),
        "C": (255, 96, 150),
        "S": (170, 235, 255),
        "G": (52, 56, 70),
        "E": (110, 225, 255),
        "W": (240, 250, 255),
    },
    "p3": {   # VERDANT 翠岚
        "O": (10, 22, 16),
        "A": (66, 160, 92),
        "B": (30, 92, 58),
        "L": (140, 214, 150),
        "J": (96, 100, 112),
        "C": (255, 214, 64),
        "S": (190, 255, 200),
        "G": (52, 58, 66),
        "E": (150, 255, 170),
        "W": (242, 255, 244),
    },
    "p4": {   # VIOLET 紫电
        "O": (18, 10, 26),
        "A": (140, 84, 200),
        "B": (84, 44, 130),
        "L": (196, 150, 240),
        "J": (96, 100, 112),
        "C": (255, 214, 64),
        "S": (225, 170, 255),
        "G": (52, 52, 66),
        "E": (210, 150, 255),
        "W": (248, 240, 255),
    },
}

# 光束弹配色（热 / 冷 / 酸三套）
BOLT_PALETTES = {
    "hot":  {"O": (60, 16, 20), "S": (255, 120, 60), "E": (255, 200, 90), "W": (255, 248, 230)},
    "cool": {"O": (10, 30, 50), "S": (70, 190, 255), "E": (170, 235, 255), "W": (240, 252, 255)},
    "acid": {"O": (8, 34, 18), "S": (90, 220, 110), "E": (180, 255, 160), "W": (245, 255, 235)},
    "violet": {"O": (26, 8, 36), "S": (190, 110, 255), "E": (240, 190, 255), "W": (250, 242, 255)},
}
