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
# P1：A/D 移动  W 跳  S 防御  J 近战  K 远程  L 投技  I 超必杀（双击 A/D 冲刺/后撤）
import pygame as _pg

P1_KEYS = {
    "left":   _pg.K_a,
    "right":  _pg.K_d,
    "jump":   _pg.K_w,
    "block":  _pg.K_s,
    "melee":  _pg.K_j,
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
MECH_ORDER = ["garnet", "azure", "verdant"]

# ---------------------------------------------------------------- 机甲规格
# 三机甲共用像素骨架，配色与数值不同；每台各有专属超必杀与专属特性
MECH_SPECS = {
    "garnet": {
        "name": "GARNET",
        "cn_name": "红莲",
        "palette": "p1",
        "hp": 120,
        "walk_speed": 1.35,      # px / frame
        "jump_power": 6.0,       # 提高跳跃高度，保证能越过对手头顶（体高 56px）
        "air_jumps": 0,
        "melee_damage": 12,
        "melee_range": 40,       # 判定盒前端离中心的距离
        "knockback": 3.6,
        "bolt_color": "hot",     # 光束弹配色（红橙）
        "throw_damage": 18,      # 投技伤害（无视格挡）
        "super_name": "熔核冲击",  # 超必杀：向前冲撞，命中重创击飞
        "super_damage": 30,
    },
    "azure": {
        "name": "AZURE",
        "cn_name": "苍鳍",
        "palette": "p2",
        "hp": 100,
        "walk_speed": 1.7,
        "jump_power": 6.3,       # 提高跳跃高度，保证能越过对手头顶（体高 56px）
        "air_jumps": 0,
        "melee_damage": 9,
        "melee_range": 40,
        "knockback": 3.2,
        "bolt_color": "cool",    # 光束弹配色（青蓝）
        "throw_damage": 15,      # 投技伤害（无视格挡）
        "super_name": "苍蓝齐射",  # 超必杀：连发三道强化光束
        "super_damage": 7,       # 每发光束伤害（共 3 发）
    },
    "verdant": {
        "name": "VERDANT",
        "cn_name": "翠岚",
        "palette": "p3",
        "hp": 110,
        "walk_speed": 1.55,
        "jump_power": 6.6,       # 全场最高跳跃
        "air_jumps": 1,          # 专属机动：空中二段跳
        "melee_damage": 10,
        "melee_range": 40,
        "knockback": 3.4,
        "bolt_color": "acid",    # 光束弹配色（酸绿）
        "throw_damage": 16,
        "super_name": "翠暴轰炸",  # 超必杀：两发弧线榴弹砸向对手当前位置
        "super_damage": 12,      # 单发榴弹伤害（共 2 发）
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
# 超必杀：独立 SUPER 槽，命中/受击/格挡积攒，满 100 释放
SUPER_MAX = 100
SUPER_GAIN_HIT = 12             # 命中积攒
SUPER_GAIN_TAKE = 8             # 受击积攒
SUPER_GAIN_BLOCK = 4            # 格挡积攒
SUPER_TOTAL = 40                # 超必杀动作总帧数
SUPER_INVULN_FRAMES = 20        # 发动后无敌帧（含定格演出时间）
SUPER_FLASH_FRAMES = 26         # 发动瞬间全局定格（演出）
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

# ---------------------------------------------------------------- 阶段3：第三机甲专属超必杀 / AI 难度
VERDANT_SUPER_SHOTS = (12, 24)    # 两发榴弹发射帧
VERDANT_SUPER_BOLT_DMG = 12       # 单发榴弹伤害
VERDANT_SUPER_VY = -4.8           # 榴弹初速（向上）
VERDANT_SUPER_GRAV = 0.24         # 榴弹重力（弧线弹道）
# AI 难度三档：反应概率 / 决策间隔 / 失误率全部入表，架构不动
AI_DIFFICULTY = {
    "easy":   {"react_melee": 0.015, "react_bolt": 0.020, "grab_block": 0.015,
               "grab_near": 0.35, "dodge_throw": 0.015, "decide": (16, 30),
               "mistake": 0.30, "super_p": 0.20, "melee_p": 0.30, "block_p": 0.25},
    "normal": {"react_melee": 0.035, "react_bolt": 0.050, "grab_block": 0.060,
               "grab_near": 0.60, "dodge_throw": 0.060, "decide": (8, 16),
               "mistake": 0.10, "super_p": 0.45, "melee_p": 0.50, "block_p": 0.20},
    "hard":   {"react_melee": 0.075, "react_bolt": 0.100, "grab_block": 0.120,
               "grab_near": 0.75, "dodge_throw": 0.140, "decide": (5, 11),
               "mistake": 0.04, "super_p": 0.60, "melee_p": 0.65, "block_p": 0.10},
}

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
}

# 光束弹配色（热 / 冷 / 酸三套）
BOLT_PALETTES = {
    "hot":  {"O": (60, 16, 20), "S": (255, 120, 60), "E": (255, 200, 90), "W": (255, 248, 230)},
    "cool": {"O": (10, 30, 50), "S": (70, 190, 255), "E": (170, 235, 255), "W": (240, 252, 255)},
    "acid": {"O": (8, 34, 18), "S": (90, 220, 110), "E": (180, 255, 160), "W": (245, 255, 235)},
}
