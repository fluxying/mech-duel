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
# P1：A/D 移动  W 跳  S 防御  J 近战  K 远程
import pygame as _pg

P1_KEYS = {
    "left":   _pg.K_a,
    "right":  _pg.K_d,
    "jump":   _pg.K_w,
    "block":  _pg.K_s,
    "melee":  _pg.K_j,
    "ranged": _pg.K_k,
}
P2_KEYS = {
    "left":   _pg.K_LEFT,
    "right":  _pg.K_RIGHT,
    "jump":   _pg.K_UP,
    "block":  _pg.K_DOWN,
    "melee":  _pg.K_1,
    "ranged": _pg.K_2,
}

# ---------------------------------------------------------------- 机甲规格
# 两机甲共用像素骨架，仅配色与数值不同：重装型 vs 轻型
MECH_SPECS = {
    "garnet": {
        "name": "GARNET",
        "cn_name": "红莲",
        "palette": "p1",
        "hp": 120,
        "walk_speed": 1.35,      # px / frame
        "jump_power": 5.3,
        "melee_damage": 12,
        "melee_range": 40,       # 判定盒前端离中心的距离
        "knockback": 3.6,
        "bolt_color": "hot",     # 光束弹配色（红橙）
    },
    "azure": {
        "name": "AZURE",
        "cn_name": "苍鳍",
        "palette": "p2",
        "hp": 100,
        "walk_speed": 1.7,
        "jump_power": 5.6,
        "melee_damage": 9,
        "melee_range": 40,
        "knockback": 3.2,
        "bolt_color": "cool",    # 光束弹配色（青蓝）
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
}

# 光束弹配色（热 / 冷两套）
BOLT_PALETTES = {
    "hot":  {"O": (60, 16, 20), "S": (255, 120, 60), "E": (255, 200, 90), "W": (255, 248, 230)},
    "cool": {"O": (10, 30, 50), "S": (70, 190, 255), "E": (170, 235, 255), "W": (240, 252, 255)},
}
