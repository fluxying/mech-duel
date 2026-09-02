# -*- coding: utf-8 -*-
"""《钢铁对决 MECH DUEL》内置像素素材系统。

素材方案（零外部资源）：
- 机体：手绘字符画，按「上身姿势部件 × 腿部部件」拼装成 40x30 画布，运行时 2x 放大。
  光剑不画进字符图，而是作为程序化光刃（角度/长度/形状参数表）叠加渲染，
  叠加时只写入空像素格，因此剑刃会自然被身体遮挡（剑在身后时正确分层）。
- 机甲差异：同一套基础骨架 + 每套调色板，再用 `PAL_PARTS`（剪影部件覆盖）与
  `PAL_SABER`（光刃形状/参数覆盖）做 per-palette 差异化——四台机甲站姿、
  行走、跳跃剪影与光刃形状各不相同（GARNET 重斧 / AZURE 刺剑 / VERDANT 软鞭 /
  VIOLET 电锯）。未覆盖的部件自动回退通用骨架。
- 受击闪白：用全白调色板再渲染一套剪影。
- 场景：夜空渐变 + 星空 + 月亮 + 两层废墟剪影 + 金属地面，全部程序绘制并预渲染。
- 直接运行本文件可输出 preview.png 素材总览图，用于美术校对。
"""

import random

import pygame

from settings import (INTERNAL_W, INTERNAL_H, GROUND_Y, MECH_PALETTES,
                      BOLT_PALETTES, COLORS)

FRAME_W, FRAME_H = 40, 30       # 字符画画布
PIX = 2                         # 渲染放大倍数（画面上的大像素颗粒）
SPRITE_W, SPRITE_H = FRAME_W * PIX, FRAME_H * PIX
ANCHOR_FX = 17.5                # 机体中心在画布中的 x（用于贴合逻辑坐标）

_BLANK_ROW = "." * FRAME_W


def row(*seg):
    """拼一行像素：整数 = 若干个透明点，字符串 = 原样字符。行宽必须等于 FRAME_W。"""
    parts = []
    for s in seg:
        parts.append("." * s if isinstance(s, int) else s)
    line = "".join(parts)
    assert len(line) == FRAME_W, f"像素行宽度 {len(line)} != {FRAME_W}: {line!r}"
    return line


# ================================================================ 上身部件
# 朝右。字符：O描边 A主装甲 B暗部 L亮部 J关节 C传感器 G武器深色 E能量 W白

UPPER_IDLE = [   # 待机：持剑手收于体侧（光剑由参数表叠加）
    row(40),
    row(18, "O", 21),
    row(18, "O", 21),
    row(13, "OOOOOOOOO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OAACCCAAO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OOOOOOOOO", 18),
    row(8, "OOOOO", "OOOOOOOOO", "OOOOO", 13),
    row(8, "OBBBO", "OALLLLLAO", "OALLO", 13),
    row(8, "OBBBO", "OALLLLLAO", "OAAAO", 13),
    row(8, "OOOOO", "OAACCAAAO", "OOOOO", 13),
    row(9, "OJO", 1, "OAAAAAAAO", 1, "OJO", 14),
    row(8, "OGGGO", "OBBBBBBBO", 1, "OGG", 14),
    row(8, "OGGGO", "OBBBBBBBO", 2, "OGGG", 12),
    row(8, "OGGGO", "OOOOOOOOO", 5, "GG", 11),
]

UPPER_ATK0 = [   # 前摇：持剑手举过头顶（光剑向斜后方上举）
    row(40),
    row(18, "O", 21),
    row(18, "O", 21),
    row(13, "OOOOOOOOO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OAACCCAAO", 18),
    row(13, "OAAAAAAAO", 1, "JG", 15),
    row(13, "OOOOOOOOO", 1, "J", 16),
    row(8, "OOOOO", "OOOOOOOOO", "OOOOO", 13),
    row(8, "OBBBO", "OALLLLLAO", "OALLO", 13),
    row(8, "OBBBO", "OALLLLLAO", "OAAAO", 13),
    row(8, "OOOOO", "OAACCAAAO", "OOOOO", 13),
    row(9, "OJO", 1, "OAAAAAAAO", 1, "OJO", 14),
    row(8, "OGGGO", "OBBBBBBBO", 1, "OGG", 14),
    row(8, "OGGGO", "OBBBBBBBO", 2, "OGGG", 12),
    row(8, "OGGGO", "OOOOOOOOO", 5, "GG", 11),
]

UPPER_ATK1 = [   # 斩击：右臂水平刺出（光剑向前）
    row(40),
    row(18, "O", 21),
    row(18, "O", 21),
    row(13, "OOOOOOOOO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OAACCCAAO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OOOOOOOOO", 18),
    row(8, "OOOOO", "OOOOOOOOO", "OOOOO", 13),
    row(8, "OBBBO", "OALLLLLAO", "OALLO", 13),
    row(8, "OBBBO", "OALLLLLAO", "OAAAO", 13),
    row(8, "OOOOO", "OAACCAAAO", "OOOOO", 13),
    row(9, "OJO", 1, "OAAAAAAAO", 1, "OJO", 14),
    row(8, "OGGGO", "OBBBBBBBO", 1, "OOO", 14),
    row(8, "OGGGO", "OBBBBBBBO", 2, "OGGG", 12),
    row(8, "OGGGO", "OOOOOOOOO", 5, "GG", 11),
]
# 斩击臂：y10/y11 的前臂已由 "OJO" 画出
UPPER_ATK1[10] = row(8, "OBBBO", "OALLLLLAO", "OJO", 15)
UPPER_ATK1[11] = row(8, "OOOOO", "OAACCAAAO", "OJO", 15)

UPPER_SHOOT0 = [  # 射击：后臂机关炮抬平指向前方
    row(40),
    row(18, "O", 21),
    row(18, "O", 21),
    row(13, "OOOOOOOOO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OAACCCAAO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OOOOOOOOO", 18),
    row(8, "OOOOO", "OOOOOOOOO", "OOOOO", 13),
    row(8, "OBBBO", "OGGGGGGGGGGGGGGO", 11),
    row(8, "OBBBO", "OGGGGGGGGGGGGGEO", 11),
    row(8, "OOOOO", "OOOOOOOOOOOOOOOO", "OOOOO", 6),
    row(9, "OJO", 1, "OAACCAAAO", 1, "OJO", 14),
    row(8, "OGGGO", "OBBBBBBBO", 1, "OGG", 14),
    row(8, "OGGGO", "OBBBBBBBO", 2, "OGGG", 12),
    row(8, "OGGGO", "OOOOOOOOO", 5, "GG", 11),
]

UPPER_BLOCK = [  # 防御：双臂在体前交叠成盾
    row(40),
    row(18, "O", 21),
    row(18, "O", 21),
    row(13, "OOOOOOOOO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OAACCCAAO", 18),
    row(13, "OAAAAAAAO", 18),
    row(13, "OOOOOOOOO", 18),
    row(8, "OOOOO", "OOOOOOOOO", "OOOOOO", 12),
    row(8, "OBBBO", "OALLLLLAO", "OJGGGO", 12),
    row(8, "OBBBO", "OALLLLLAO", "OJGGGO", 12),
    row(8, "OOOOO", "OAAAAAAAO", "OJGGGO", 12),
    row(9, "OJO", 1, "OAAAAAAAO", "OJGGGO", 12),
    row(8, "OGGGO", "OBBBBBBBO", "OJGGGO", 12),
    row(8, "OGGGO", "OBBBBBBBO", "OJGGGO", 12),
    row(8, "OGGGO", "OOOOOOOOO", "OOOOOO", 12),
]

UPPER_HURT = [   # 受击：双臂上扬后仰
    row(40),
    row(18, "O", 21),
    row(18, "O", 21),
    row(13, "OOOOOOOOO", 18),
    row(8, "OJO", 2, "OAAAAAAAO", 2, "OJO", 13),
    row(8, "OJO", 2, "OAACCCAAO", 2, "OJO", 13),
    row(8, "OJO", 2, "OAAAAAAAO", 2, "OJO", 13),
    row(8, "OJO", 2, "OOOOOOOOO", 2, "OJO", 13),
    row(8, "OOOOO", "OOOOOOOOO", "OOOOO", 13),
    row(8, "OBBBO", "OALLLLLAO", "OALLO", 13),
    row(8, "OBBBO", "OALLLLLAO", "OAAAO", 13),
    row(8, "OOOOO", "OAACCAAAO", "OOOOO", 13),
    row(9, "OJO", 1, "OAAAAAAAO", 1, "OJO", 14),
    row(8, "OGGGO", "OBBBBBBBO", 1, "OGG", 14),
    row(8, "OGGGO", "OBBBBBBBO", 2, "OGGG", 12),
    row(8, "OGGGO", "OOOOOOOOO", 5, "GG", 11),
]

# ================================================================ 腿部部件

LEGS_IDLE = [    # 站立
    row(13, "OBBBBBBBO", 18),
    row(13, "OOOO", 1, "OOOO", 18),
    row(13, "OAAO", 1, "OAAO", 18),
    row(13, "OAAO", 1, "OAAO", 18),
    row(13, "OAAO", 1, "OAAO", 18),
    row(13, "OJJO", 1, "OJJO", 18),
    row(13, "OBBO", 1, "OBBO", 18),
    row(13, "OBBO", 1, "OBBO", 18),
    row(13, "OBBO", 1, "OBBO", 18),
    row(13, "OJJO", 1, "OJJO", 18),
    row(12, "OOOOOO", "OOOOOOOO", 14),
    row(12, "OAAAAO", "OAAAAAAO", 14),
    row(12, "OJJJJO", "OJJJJJJO", 14),
    row(12, "OOOOOO", "OOOOOOOO", 14),
]

LEGS_WALK_A = [  # 行走：迈步展开
    row(13, "OBBBBBBBO", 18),
    row(13, "OOOO", 1, "OOOO", 18),
    row(11, "OAAO", 5, "OAAO", 16),
    row(10, "OAAO", 6, "OAAO", 16),
    row(10, "OAAO", 6, "OAAO", 16),
    row(10, "OJJO", 6, "OJJO", 16),
    row(9, "OBBO", 8, "OBBO", 15),
    row(9, "OBBO", 8, "OBBO", 15),
    row(9, "OBBO", 8, "OBBO", 15),
    row(9, "OJJO", 8, "OJJO", 15),
    row(8, "OOOOOOO", 5, "OOOOOOOO", 12),
    row(8, "OAAAAAO", 5, "OAAAAAAAO", 11),
    row(8, "OJJJJJO", 5, "OJJJJJJJO", 11),
    row(8, "OOOOOOO", 5, "OOOOOOOOO", 11),
]

LEGS_WALK_B = [  # 行走：并步过渡（整体抬高 1px）
    row(13, "OBBBBBBBO", 18),
    row(13, "OOOO", 1, "OOOO", 18),
    row(13, "OAAO", 1, "OAAO", 18),
    row(13, "OAAO", 1, "OAAO", 18),
    row(13, "OAAO", 1, "OAAO", 18),
    row(13, "OJJO", 1, "OJJO", 18),
    row(13, "OBBO", 1, "OBBO", 18),
    row(13, "OBBO", 1, "OBBO", 18),
    row(13, "OJJO", 1, "OJJO", 18),
    row(12, "OOOOOO", "OOOOOOOO", 14),
    row(12, "OAAAAO", "OAAAAAAO", 14),
    row(12, "OJJJJO", "OJJJJJJO", 14),
    row(12, "OOOOOO", "OOOOOOOO", 14),
    row(40),
]

LEGS_JUMP = [    # 跳跃：屈膝收腿
    row(13, "OBBBBBBBO", 18),
    row(13, "OAAO", 1, "OAAO", 18),
    row(13, "OAAO", 1, "OAAO", 18),
    row(12, "OJJO", 2, "OJJO", 18),
    row(11, "OBBO", 2, "OBBO", 19),
    row(10, "OBBO", 3, "OBBO", 19),
    row(10, "OBBO", 3, "OBBO", 19),
    row(10, "OJJO", 3, "OJJO", 19),
    row(9, "OBBO", 4, "OBBO", 19),
    row(9, "OBBO", 4, "OBBO", 19),
    row(8, "OOOOOOOOOOOOOOOO", 16),
    row(8, "OAAAAAO", "OAAAAAAO", 17),
    row(8, "OJJJJJO", "OJJJJJJO", 17),
    row(8, "OOOOOOO", "OOOOOOOO", 17),
]

FRAME_KO = [     # 倒地（整机横躺，光剑掉在身边）
    row(40), row(40), row(40), row(40), row(40), row(40),
    row(40), row(40), row(40), row(40), row(40), row(40),
    row(40), row(40), row(40), row(40), row(40),
    row(15, "OJO", 22),
    row(15, "OJO", 22),
    row(15, "OJO", 22),
    row(15, "OJO", 22),
    row(15, "OJO", 22),
    row(4, "OOOOOOOOO", 2, "OOOOOOOOOOOO", 13),
    row(4, "OAACCCAAO", "OAAAAAAAAAAAO", 14),
    row(4, "OAAAAAAAO", "OALLLLLLLLLAO", "OBBBBBBBBO", 4),
    row(4, "OAAAAAAAO", "OAAAAAAAAAAAO", "OBBBBBBBBO", 4),
    row(4, "OAAAAAAAO", "OAAAAAAAAAAAO", "OBBBBBBBBO", 4),
    row(4, "OOOOOOOOO", "OOOOOOOOOOOOO", "OAAAAAAAO", 5),
    row(13, "OOOOOOOOOOOOO", "OOOOOOOOO", 5),
    row(24, "SSSSSSSSSS", 6),
]

# ================================================================ 帧组装表
# (帧名, 上身部件名, 腿部部件名, 光剑参数(origin_x, origin_y, 角度°, 长度[, style]) 或 None)
# 角度：-90 为正上，0 为正前（朝右），正值向下。
# 上身/腿部部件名查 BASE_PARTS；per-palette 覆盖查 PAL_PARTS（缺省回退通用骨架）。
# 光剑第 5 元（可选）= style：blade 直线（默认）/ axe 短粗重斧 /
#   lance 细长刺剑 / whip 弧线软鞭 / saw 锯齿电光。
# style 可被 PAL_SABER[pal][name] 覆盖（每台机甲可定制每个招式的光刃形状）。

FRAMES = {
    "idle":   ("idle",   "upper_idle",   "legs_idle",   (27, 13, -90, 11)),
    "walk_a": ("walk_a", "upper_idle",   "legs_walk_a", (27, 13, -90, 11)),
    "walk_b": ("walk_b", "upper_idle",   "legs_walk_b", (27, 13, -90, 11)),
    "jump":   ("jump",   "upper_idle",   "legs_jump",   (27, 13, -80, 10)),
    "atk0":   ("atk0",   "upper_atk0",   "legs_walk_a", (23, 9, -145, 13)),
    "atk1":   ("atk1",   "upper_atk1",   "legs_walk_a", (25, 10, -8, 14)),
    "atk2":   ("atk2",   "upper_idle",   "legs_walk_a", (26, 13, 35, 11)),
    # 重击变体专属动作帧（复用上身像素 + 光剑参数重组，无新画）：
    # thrust=水平直刺 rise=升斩 sweep=下段低扫 bash=无剑肩撞 toss=空手投掷
    "thrust": ("thrust", "upper_atk1",   "legs_walk_a", (24, 10, 0, 15, "lance")),
    "rise":   ("rise",   "upper_atk1",   "legs_idle",   (25, 13, -72, 13, "blade")),
    "sweep":  ("sweep",  "upper_atk1",   "legs_walk_b", (27, 13, 28, 13, "axe")),
    "bash":   ("bash",   "upper_atk1",   "legs_walk_a", None),
    "toss":   ("toss",   "upper_atk0",   "legs_walk_b", None),
    "shoot":  ("shoot",  "upper_shoot",  "legs_walk_a", (26, 14, -60, 7)),
    "block":  ("block",  "upper_block",  "legs_idle",   None),
    "hurt":   ("hurt",   "upper_hurt",   "legs_idle",   (25, 9, -115, 8)),
    "ko":     ("ko",     "frame_ko",     None,          None),
}

# 光束弹（10x5，两帧闪烁）
BOLT_MAP = [
    "...OOOO...",
    ".OOSSWWO..",
    "OSSSWWWWO.",
    ".OOSSWWO..",
    "...OOOO...",
]
BOLT_MAP_BRIGHT = [r.replace("S", "W") for r in BOLT_MAP]


# ================================================================ 渲染

def _grid_from_rows(rows):
    return [list(r) for r in rows]


def _draw_saber(grid, params, palette):
    """把光刃画进画布空格（不覆盖已有像素 → 剑可被身体遮挡）。
    style: blade 直线(2px 厚) / axe 短粗重斧(3px 厚, 刃端 2-3 宽) /
           lance 细长刺剑(单像素, 长 + 尖端亮) /
           whip 弧线软鞭(垂直二次下坠) / saw 锯齿电光(±2 锯齿偏移)。
    """
    if not params:
        return
    import math
    ox, oy, ang, ln = params[:4]
    style = params[4] if len(params) > 4 else "blade"
    rad = math.radians(ang)
    dx, dy = math.cos(rad), math.sin(rad)

    def put(px, py, ch):
        if 0 <= px < FRAME_W and 0 <= py < FRAME_H and grid[py][px] == ".":
            grid[py][px] = ch

    if style == "whip":
        n = int(ln * 3)
        for i in range(n + 1):
            t = i / 3.0
            x = int(round(ox + dx * t))
            cv = 0.18 * t * t
            y = int(round(oy + dy * t + cv))
            put(x, y, "S")
            put(x, y + 1, "S")
            if i % 3 == 0:
                put(x, y - 1, "W")
        tx = int(round(ox + dx * ln + 0.18 * ln * ln))
        ty = int(round(oy + dy * ln + 0.18 * ln * ln))
        put(tx, ty, "W")
        return
    if style == "lance":
        px_ = py_ = None
        for i in range(int(ln * 2) + 1):
            t = i / 2.0
            x = int(round(ox + dx * t))
            y = int(round(oy + dy * t))
            # 斜刃在 x、y 同时跳变处只有对角相接，补一格避免断成虚线
            if px_ is not None and px_ != x and py_ != y:
                put(px_, y, "S")
            put(x, y, "S")
            px_, py_ = x, y
        tx = int(round(ox + dx * ln))
        ty = int(round(oy + dy * ln))
        put(tx, ty, "W")
        put(tx + (1 if dx >= 0 else -1), ty, "W")
        return
    prev = None
    for i in range(int(ln * PIX) + 1):
        t = i / PIX
        x = int(round(ox + dx * t))
        y = int(round(oy + dy * t))
        if prev is not None and prev[0] != x and prev[1] != y:
            put(prev[0], y, "S")      # 斜刃对角补缝
        prev = (x, y)
        for px_, py_ in ((x, y), (x, y + 1)):
            if 0 <= px_ < FRAME_W and 0 <= py_ < FRAME_H and grid[py_][px_] == ".":
                grid[py_][px_] = "S"
        if style == "axe":
            if 0 <= y - 1 < FRAME_H and 0 <= x < FRAME_W and grid[y - 1][x] == ".":
                grid[y - 1][x] = "S"
        if style == "saw":
            # 锯齿须与主线(y, y+1)相接，否则会碎成孤立点：上齿 y+2 / 下齿 y-1
            off = 2 if i % 2 == 0 else -1
            yy = y + off
            if 0 <= yy < FRAME_H and 0 <= x < FRAME_W and grid[yy][x] == ".":
                grid[yy][x] = "S"
            if i % 3 == 0:
                if 0 <= yy < FRAME_H and 0 <= x < FRAME_W and grid[yy][x] == "S":
                    grid[yy][x] = "W"
    # 剑尖白热点
    tx = int(round(ox + dx * ln))
    ty = int(round(oy + dy * ln))
    for px_, py_ in ((tx, ty), (tx + 1, ty), (tx, ty + 1)):
        if 0 <= px_ < FRAME_W and 0 <= py_ < FRAME_H and grid[py_][px_] == ".":
            grid[py_][px_] = "W"


def _render_grid(grid, palette):
    gh, gw = len(grid), len(grid[0])
    surf = pygame.Surface((gw * PIX, gh * PIX), pygame.SRCALPHA)
    for gy in range(gh):
        for gx in range(gw):
            ch = grid[gy][gx]
            if ch == ".":
                continue
            color = palette.get(ch)
            if color is None:
                continue
            surf.fill(color, (gx * PIX, gy * PIX, PIX, PIX))
    return surf


WHITE_PALETTE = None  # 延迟构建：受击闪白


# ================================================================ 部件名 → 基础部件
# build_mech_frames 装配每帧时，先用 BASE_PARTS 取通用部件，再用 PAL_PARTS[pal]
# 覆盖（per-palette 剪影差异化）。未被覆盖的部件回退通用骨架。
BASE_PARTS = {
    "upper_idle":  UPPER_IDLE,
    "upper_atk0":  UPPER_ATK0,
    "upper_atk1":  UPPER_ATK1,
    "upper_shoot": UPPER_SHOOT0,
    "upper_block": UPPER_BLOCK,
    "upper_hurt":  UPPER_HURT,
    "legs_idle":   LEGS_IDLE,
    "legs_walk_a": LEGS_WALK_A,
    "legs_walk_b": LEGS_WALK_B,
    "legs_jump":   LEGS_JUMP,
    "frame_ko":    FRAME_KO,
}


# ================================================================ 角色剪影覆盖（批次 A：L0 剪影）
# 写法：PAL_PARTS[pal][part_name] -> 字符画（40 宽 × 部件行数）；
# 未列出的部件继承 BASE_PARTS。等同于「同骨架换皮」→ 「四台机甲剪影一眼可分」。
def _at(*items):
    """辅助：起始 x + 字符串 → 40 宽字符画。"""
    g = ["."] * FRAME_W
    for x, s in items:
        for i, ch in enumerate(s):
            if 0 <= x + i < FRAME_W:
                g[x + i] = ch
    return "".join(g)


def _variant_upper(base, rows):
    """批次 B 辅助：以某台 idle 上身为底，按 {行号: 该行字符画} 覆盖生成攻击姿态。
    头/躯干沿用 idle（保机体辨识），只重画肩臂——差异集中在发力部位。
    覆盖行必须仍与未覆盖行 4-连通（selftest [37] 会拦悬空碎块）。"""
    out = list(base)
    for y, s in rows.items():
        out[y] = s
    return out


def _legs_up(legs):
    """派生「并步过渡」腿：髋部横梁保持不动，膝踝上收 1 格（重心上提）。
    注意不能整体平移——髋部那道横梁是左右腿唯一的连接，去掉会让双腿各自脱开。
    """
    rows = list(legs)
    if len(rows) < 2:
        return rows
    return [rows[0]] + rows[2:] + [_at()]


# GARNET 红莲：重装 · 宽肩厚甲低重心 · 粗短天线
G_UPPER_IDLE = [
    _at(),
    _at((17, "OOO")),
    _at((17, "OEO")),
    _at((11, "O" * 13)),
    _at((11, "O" + "A" * 11 + "O")),
    _at((11, "OA" + "C" * 9 + "AO")),
    _at((11, "O" + "A" * 11 + "O")),
    _at((11, "O" * 13)),
    _at((5, "O" * 7), (12, "O" * 14), (26, "O" * 7)),
    _at((5, "OBBBBBO"), (12, "OA" + "L" * 10 + "AO"), (26, "OBBBBBO")),
    _at((5, "OBBBBBO"), (12, "OA" + "L" * 10 + "AO"), (26, "OBBBBBO")),
    _at((5, "OOBBBOO"), (12, "OAA" + "C" * 8 + "AAO"), (26, "OOBBBOO")),
    _at((7, "OJJJO"), (13, "O" + "A" * 11 + "O"), (26, "OJJJO")),
    _at((7, "OGGGO"), (13, "O" + "B" * 11 + "O"), (26, "OGGGO")),
    _at((7, "OGGGO"), (13, "O" + "B" * 11 + "O"), (26, "OGGGO")),
    _at((7, "OGGGO"), (13, "O" * 13), (26, "OGGGO")),
]
# GARNET 迈步（粗腿大跨步）
G_LEGS_WALK_A = [
    _at((12, "OBBBBBBBBBO")),
    _at((12, "OOOOO"), (20, "OOOOO")),
    _at((10, "OAAAO"), (21, "OAAAO")),
    _at((9, "OAAAO"), (22, "OAAAO")),
    _at((9, "OAAAO"), (22, "OAAAO")),
    _at((9, "OJJO"), (22, "OJJO")),
    _at((8, "OBBBO"), (23, "OBBBO")),
    _at((8, "OBBBO"), (23, "OBBBO")),
    _at((8, "OBBBO"), (23, "OBBBO")),
    _at((8, "OJJO"), (23, "OJJO")),
    _at((7, "OOOOOOO"), (23, "OOOOOOO")),
    _at((7, "OAAAAAO"), (23, "OAAAAAO")),
    _at((7, "OJJJJJO"), (23, "OJJJJJO")),
    _at((7, "OOOOOOO"), (23, "OOOOOOO")),
]
# GARNET 跳跃（粗腿屈膝收起）
G_LEGS_JUMP = [
    _at((12, "OBBBBBBBBBO")),
    _at((11, "OAAAO"), (21, "OAAAO")),
    _at((11, "OAAAO"), (21, "OAAAO")),
    _at((10, "OJJO"), (21, "OJJO")),
    _at((9, "OBBBO"), (21, "OBBBO")),
    _at((9, "OBBBO"), (22, "OBBBO")),
    _at((9, "OBBBO"), (22, "OBBBO")),
    _at((9, "OJJO"), (22, "OJJO")),
    _at((8, "OBBO"), (22, "OBBO")),
    _at((8, "OBBO"), (22, "OBBO")),
    _at((7, "OOOOOOO"), (22, "OOOOOOO")),
    _at((7, "OAAAAAO"), (22, "OAAAAAO")),
    _at((7, "OJJJJJO"), (22, "OJJJJJO")),
    _at(),
]

G_LEGS_IDLE = [
    _at((12, "OBBBBBBBBBO")),
    _at((12, "OOOOO"), (20, "OOOOO")),
    _at((12, "OAAAO"), (20, "OAAAO")),
    _at((12, "OAAAO"), (20, "OAAAO")),
    _at((12, "OAAAO"), (20, "OAAAO")),
    _at((12, "OJJO"), (20, "OJJO")),
    _at((11, "OBBBO"), (21, "OBBBO")),
    _at((11, "OBBBO"), (21, "OBBBO")),
    _at((11, "OBBBO"), (21, "OBBBO")),
    _at((11, "OJJO"), (21, "OJJO")),
    _at((10, "OOOOOOO"), (20, "OOOOOOO")),
    _at((10, "OAAAAAO"), (20, "OAAAAAO")),
    _at((10, "OJJJJJO"), (20, "OJJJJJO")),
    _at((10, "OOOOOOO"), (20, "OOOOOOO")),
]

# AZURE 苍鳍：轻快 · 窄身流线长天线 · 背后推进器
A_UPPER_IDLE = [
    _at(),
    _at((18, "O")),
    _at((18, "O")),
    _at((14, "O" * 9)),
    _at((14, "O" + "A" * 7 + "O")),
    _at((14, "OA" + "C" * 5 + "AO")),
    _at((14, "O" + "A" * 7 + "O")),
    _at((14, "O" * 9)),
    _at((10, "O" * 5), (15, "O" * 9), (24, "O" * 5)),
    _at((10, "OBBBO"), (15, "OALLLLLAO"), (24, "OBBBO")),
    _at((10, "OBBBO"), (15, "OALLLLLAO"), (24, "OAAAO")),
    _at((10, "OOOOO"), (15, "OAACCAAAO"), (24, "OOOOO")),
    # 背部推进器：装甲(B)包住喷口(E)，经连接臂挂到手臂上，避免变成悬空碎块。
    # 注意手臂 OGGGO 占 9-13，推进器须止于 x<=8 才不会被盖掉喷口。
    _at((5, "OOOOOO"), (11, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OJO")),
    _at((4, "OBBEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (25, "OGG")),
    _at((4, "OBEEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (26, "OGGG")),
    _at((5, "OBBBOO"), (9, "OGGGO"), (15, "O" * 9), (28, "GG")),
]
# AZURE 迈步（细腿大跨步）
A_LEGS_WALK_A = [
    _at((15, "OBBBBBBO")),
    _at((15, "OOOO"), (20, "OOOO")),
    _at((13, "OAAO"), (22, "OAAO")),
    _at((12, "OAAO"), (23, "OAAO")),
    _at((11, "OAAO"), (23, "OAAO")),
    _at((11, "OJJO"), (24, "OJJO")),
    _at((11, "OBBO"), (24, "OBBO")),
    _at((12, "OBBO"), (24, "OBBO")),
    _at((12, "OJJO"), (24, "OJJO")),
    _at((12, "OBBO"), (24, "OBBO")),
    _at((11, "OOOOO"), (23, "OOOOOO")),
    _at((11, "OAAAAO"), (23, "OAAAAAO")),
    _at((11, "OJJJJO"), (23, "OJJJJJO")),
    _at((11, "OOOOOO"), (23, "OOOOOOO")),
]
# AZURE 跳跃（细腿收拢）
A_LEGS_JUMP = [
    _at((15, "OBBBBBBO")),
    _at((15, "OAAO"), (20, "OAAO")),
    _at((15, "OAAO"), (20, "OAAO")),
    _at((15, "OJJO"), (20, "OJJO")),
    _at((14, "OBBO"), (20, "OBBO")),
    _at((14, "OBBO"), (21, "OBBO")),
    _at((14, "OBBO"), (21, "OBBO")),
    _at((14, "OJJO"), (21, "OJJO")),
    _at((14, "OBBO"), (21, "OBBO")),
    _at((14, "OBBO"), (21, "OBBO")),
    _at((13, "OOOOO"), (20, "OOOOO")),
    _at((13, "OAAAAO"), (20, "OAAAAAO")),
    _at((13, "OJJJJO"), (20, "OJJJJJO")),
    _at(),
]

# AZURE 站立：细长错步（前腿向右斜伸，两脚分开且水平错位）
A_LEGS_IDLE = [
    _at((15, "OBBBBBBO")),
    _at((15, "OOO"), (20, "OOO")),
    _at((15, "OAAO"), (20, "OAAO")),
    _at((15, "OAAO"), (21, "OAAO")),
    _at((15, "OAAO"), (21, "OAAO")),
    _at((15, "OJJO"), (22, "OJJO")),
    _at((15, "OBBO"), (22, "OBBO")),
    _at((15, "OBBO"), (22, "OBBO")),
    _at((15, "OBBO"), (23, "OBBO")),
    _at((15, "OJJO"), (23, "OJJO")),
    _at((14, "OOOOO"), (22, "OOOOOO")),
    _at((14, "OAAAAO"), (22, "OAAAAAO")),
    _at((14, "OJJJJO"), (22, "OJJJJJO")),
    _at((14, "OOOOOO"), (22, "OOOOOOO")),
]

# VERDANT 翠岚：机动 · 修长 · 藤蔓双天线 · 长臂
V_UPPER_IDLE = [
    # 双天线改为自头顶左右缘垂直长出（斜线只有对角相接，放大后会看成浮空断点）
    _at((15, "O")),
    _at((15, "O"), (23, "O")),
    _at((15, "O"), (23, "O")),
    _at((15, "O" * 9)),
    _at((15, "O" + "A" * 7 + "O")),
    _at((15, "OA" + "C" * 5 + "AO")),
    _at((15, "O" + "A" * 7 + "O")),
    _at((15, "O" * 9)),
    _at((9, "O" * 6), (15, "O" * 9), (24, "O" * 6)),
    _at((9, "OBBBBO"), (15, "OALLLLLAO"), (24, "OBBBBO")),
    _at((9, "OBBBBO"), (15, "OALLLLLAO"), (24, "OBBBBO")),
    _at((9, "OOBBOO"), (15, "OAACCAAAO"), (24, "OOBBOO")),
    _at((10, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OJO")),
    _at((10, "OGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGO")),
    _at((10, "OGGO"), (15, "OBBBBBBBO"), (26, "OGGO")),
    _at((10, "OGGO"), (15, "O" * 9), (26, "OGGO")),
]
# VERDANT 迈步（长腿跨步）
V_LEGS_WALK_A = [
    _at((15, "OBBBBBBO")),
    _at((15, "OOOO"), (20, "OOOO")),
    _at((13, "OAAO"), (22, "OAAO")),
    _at((12, "OAAO"), (23, "OAAO")),
    _at((12, "OAAO"), (23, "OAAO")),
    _at((12, "OJJO"), (23, "OJJO")),
    _at((12, "OBBO"), (23, "OBBO")),
    _at((12, "OBBO"), (23, "OBBO")),
    _at((12, "OJJO"), (23, "OJJO")),
    _at((12, "OBBO"), (23, "OBBO")),
    _at((11, "OOOOO"), (22, "OOOOOO")),
    _at((11, "OAAAAO"), (22, "OAAAAAO")),
    _at((11, "OJJJJO"), (22, "OJJJJJO")),
    _at((11, "OOOOOO"), (22, "OOOOOOO")),
]
# VERDANT 跳跃（长腿折叠）
V_LEGS_JUMP = [
    _at((15, "OBBBBBBO")),
    _at((15, "OAAO"), (20, "OAAO")),
    _at((15, "OAAO"), (20, "OAAO")),
    _at((15, "OJJO"), (20, "OJJO")),
    _at((14, "OBBO"), (20, "OBBO")),
    _at((14, "OBBO"), (20, "OBBO")),
    _at((14, "OBBO"), (20, "OBBO")),
    _at((14, "OJJO"), (20, "OJJO")),
    _at((14, "OBBO"), (20, "OBBO")),
    _at((14, "OBBO"), (20, "OBBO")),
    _at((13, "OOOOO"), (20, "OOOOOO")),
    _at((13, "OAAAAO"), (20, "OAAAAAO")),
    _at((13, "OJJJJO"), (20, "OJJJJJO")),
    _at(),
]

# VERDANT 站立：修长并拢（大腿更长），两脚细窄分开
V_LEGS_IDLE = [
    _at((15, "OBBBBBBO")),
    _at((15, "OOO"), (20, "OOO")),
    _at((15, "OAAO"), (20, "OAAO")),
    _at((15, "OAAO"), (20, "OAAO")),
    _at((15, "OAAO"), (20, "OAAO")),
    _at((15, "OJJO"), (20, "OJJO")),
    _at((15, "OBBO"), (20, "OBBO")),
    _at((15, "OBBO"), (20, "OBBO")),
    _at((15, "OBBO"), (20, "OBBO")),
    _at((15, "OJJO"), (20, "OJJO")),
    _at((13, "OOOOO"), (21, "OOOOO")),
    _at((13, "OAAAAO"), (21, "OAAAAO")),
    _at((13, "OJJJJO"), (21, "OJJJJO")),
    _at((13, "OOOOOO"), (21, "OOOOOOO")),
]

# VIOLET 紫电：电击 · 锐角肩甲尖刺冠 · 脚下电弧
P_UPPER_IDLE = [
    # 尖刺冠同样改为垂直竖立（中间一刺最高），保证与头顶 4-连通
    _at((17, "O")),
    _at((15, "O"), (17, "O"), (20, "O")),
    _at((15, "O"), (17, "O"), (20, "O")),
    _at((13, "O" * 11)),
    _at((13, "O" + "A" * 9 + "O")),
    _at((13, "OA" + "C" * 7 + "AO")),
    _at((13, "O" + "A" * 9 + "O")),
    _at((13, "O" * 11)),
    # 肩甲：内缘紧贴躯干(12/23)，左右镜像对称，锐角朝外；不得悬空
    _at((8, "OOOO"), (12, "O" * 12), (24, "OOOO")),
    _at((7, "OBBOO"), (12, "OA" + "L" * 8 + "AO"), (24, "OOBBO")),
    _at((6, "OBBBBO"), (12, "OA" + "L" * 8 + "AO"), (24, "OBBBBO")),
    _at((7, "OOBOO"), (12, "OAA" + "C" * 6 + "AAO"), (24, "OOOBO")),
    _at((10, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OJO")),
    _at((10, "OGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGO")),
    _at((10, "OGGO"), (15, "OBBBBBBBO"), (25, "OGGO")),
    _at((10, "OGGO"), (15, "O" * 9), (26, "OGGO")),
]
# VIOLET 迈步
P_LEGS_WALK_A = [
    _at((13, "OBBBBBBBO")),
    _at((13, "OOOO"), (18, "OOOO")),
    _at((11, "OAAO"), (20, "OAAO")),
    _at((10, "OAAO"), (21, "OAAO")),
    _at((10, "OAAO"), (21, "OAAO")),
    _at((10, "OJJO"), (21, "OJJO")),
    _at((10, "OBBO"), (22, "OBBO")),
    _at((10, "OBBO"), (22, "OBBO")),
    _at((10, "OBBO"), (22, "OBBO")),
    _at((10, "OJJO"), (22, "OJJO")),
    _at((9, "OOOOOO"), (22, "OOOOOOO")),
    _at((9, "OAAAAO"), (21, "OAAAAAO")),
    _at((9, "OJJJJO"), (21, "OJJJJJO")),
    _at((9, "OOOOOO"), (21, "OOOOOOO")),
]
# VIOLET 跳跃（收腿 + 电弧外溢）
P_LEGS_JUMP = [
    _at((13, "OBBBBBBBO")),
    _at((13, "OAAO"), (18, "OAAO")),
    _at((13, "OAAO"), (18, "OAAO")),
    _at((13, "OJJO"), (18, "OJJO")),
    _at((12, "OBBO"), (19, "OBBO")),
    _at((12, "OBBO"), (19, "OBBO")),
    _at((12, "OBBO"), (19, "OBBO")),
    _at((12, "OJJO"), (19, "OJJO")),
    _at((11, "OBBO"), (19, "OBBO")),
    _at((11, "OBBO"), (19, "OBBO")),
    _at((10, "OOOOOO"), (19, "OOOOOOO")),
    _at((10, "OAAAAO"), (19, "OAAAAAO")),
    _at((10, "OJJJJO"), (19, "OJJJJJO")),
    _at((9, "E"), (10, "OOOOOO"), (19, "OOOOOOO"), (26, "E")),
]

P_LEGS_IDLE = [
    _at((13, "OBBBBBBBO")),
    _at((13, "OOOO"), (18, "OOOO")),
    _at((13, "OAAO"), (18, "OAAO")),
    _at((13, "OAAO"), (18, "OAAO")),
    _at((13, "OAAO"), (18, "OAAO")),
    _at((13, "OJJO"), (18, "OJJO")),
    _at((12, "OBBO"), (18, "OBBO")),
    _at((12, "OBBO"), (18, "OBBO")),
    _at((12, "OBBO"), (18, "OBBO")),
    _at((12, "OJJO"), (18, "OJJO")),
    _at((11, "OOOOOO"), (18, "OOOOOOO")),
    _at((11, "OAAAAO"), (18, "OAAAAAO")),
    _at((11, "OJJJJO"), (18, "OJJJJJO")),
    # 脚下放电电弧：紧贴脚掌外缘(12/24)，不得悬空
    _at((11, "E"), (12, "OOOOOO"), (18, "OOOOOOO"), (25, "E")),
]

# ================================================================ 攻击上身差异化（批次 B）
# 原则：头/躯干沿用各台 idle（保机体辨识），只重画肩臂——发力部位才是差异所在。
# 光刃起点一律落在臂端相邻格（4-连通），各台 PAL_SABER 同步调整。
# 画布右缘 x=39，臂伸得越长刃就得越短（reach 上限一致），差异化靠「臂型 × 刃型」比例。

# ---- GARNET 红莲：力斧型。肩甲前顶发力，粗臂短刃下劈 ----
G_UPPER_ATK0 = _variant_upper(G_UPPER_IDLE, {
    # 蓄力：斧扛肩后，臂向右下后拉（逐行右移 = 斜臂）
    12: _at((7, "OJJJO"), (13, "O" + "A" * 11 + "O"), (26, "OGGGO")),
    13: _at((7, "OGGGO"), (13, "O" + "B" * 11 + "O"), (27, "OGGGO")),
    14: _at((7, "OGGGO"), (13, "O" + "B" * 11 + "O"), (28, "OGGGO")),
    15: _at((7, "OGGGO"), (13, "O" * 13), (29, "OOOOO")),
})
G_UPPER_ATK1 = _variant_upper(G_UPPER_IDLE, {
    # 横扫：右肩甲加宽前顶（26-33），粗臂水平前伸
    9:  _at((5, "OBBBBBO"), (12, "OA" + "L" * 10 + "AO"), (26, "OBBBBBBO")),
    10: _at((5, "OBBBBBO"), (12, "OA" + "L" * 10 + "AO"), (26, "OBBBBBBO")),
    12: _at((7, "OJJJO"), (13, "O" + "A" * 11 + "O"), (26, "OBBGGO")),
    13: _at((7, "OGGGO"), (13, "O" + "B" * 11 + "O"), (26, "OBBGGO")),
    14: _at((7, "OGGGO"), (13, "O" + "B" * 11 + "O"), (26, "OBBGGO")),
    15: _at((7, "OGGGO"), (13, "O" * 13), (26, "OOOOO")),
})
G_UPPER_SHOOT = _variant_upper(G_UPPER_IDLE, {
    # 肩炮：右肩甲直接化为粗炮管（重装风格——武器长在肩上）
    8:  _at((5, "O" * 7), (12, "O" * 14), (26, "O" * 9)),
    9:  _at((5, "OBBBBBO"), (12, "OA" + "L" * 10 + "AO"), (26, "OGGGGGGGGO")),
    10: _at((5, "OBBBBBO"), (12, "OA" + "L" * 10 + "AO"), (26, "OGGGGGGGEO")),
    11: _at((5, "OOBBBOO"), (12, "OAA" + "C" * 8 + "AAO"), (26, "OOOOOOOOO")),
})
G_UPPER_BLOCK = _variant_upper(G_UPPER_IDLE, {
    # 重盾：双臂交叠成 5 行宽厚盾，中央能量核
    10: _at((5, "OBBBBBO"), (12, "OA" + "L" * 10 + "AO"), (25, "OGGGGGGO")),
    11: _at((5, "OOBBBOO"), (12, "OAA" + "C" * 8 + "AAO"), (24, "OGGGGGGGO")),
    12: _at((7, "OJJJO"), (13, "O" + "A" * 11 + "O"), (24, "OGEEGGGGO")),
    13: _at((7, "OGGGO"), (13, "O" + "B" * 11 + "O"), (24, "OGGGGGGGO")),
    14: _at((7, "OGGGO"), (13, "O" + "B" * 11 + "O"), (25, "OGGGGGGO")),
    15: _at((7, "OGGGO"), (13, "O" * 13), (26, "OOOOOOO")),
})
G_UPPER_HURT = [
    # 后仰：头部/上躯干左移 2 格，右臂前上扬（重心被击退感）
    _at(),
    _at((15, "OOO")),
    _at((15, "OEO")),
    _at((9, "O" * 13)),
    _at((9, "O" + "A" * 11 + "O")),
    _at((9, "OA" + "C" * 9 + "AO"), (25, "OJO")),
    _at((9, "O" + "A" * 11 + "O"), (25, "OJO")),
    _at((9, "O" * 13), (25, "OJO")),
    _at((5, "O" * 7), (11, "O" * 14), (26, "O" * 7)),
    _at((5, "OBBBBBO"), (11, "OA" + "L" * 10 + "AO"), (26, "OBBBBBO")),
    _at((5, "OBBBBBO"), (11, "OA" + "L" * 10 + "AO"), (26, "OBBBBBO")),
    _at((5, "OOBBBOO"), (11, "OAA" + "C" * 8 + "AAO"), (26, "OOBBBOO")),
    _at((7, "OJJJO"), (12, "O" + "A" * 11 + "O"), (26, "OGGGO")),
    _at((7, "OGGGO"), (12, "O" + "B" * 11 + "O"), (26, "OGGGO")),
    _at((7, "OGGGO"), (12, "O" + "B" * 11 + "O"), (26, "OGGGO")),
    _at((7, "OGGGO"), (13, "O" * 13), (26, "OGGGO")),
]

# ---- AZURE 苍鳍：刺剑型。细臂长剑，窄盾侧身 ----
A_UPPER_ATK0 = _variant_upper(A_UPPER_IDLE, {
    # 起手式：细臂前抬，剑指前上（中段式）
    12: _at((5, "OOOOOO"), (11, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OGGGGO")),
    13: _at((4, "OBBEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGGGO")),
    14: _at((4, "OBEEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (25, "OGGGO")),
    15: _at((5, "OBBBOO"), (9, "OGGGO"), (15, "O" * 9), (26, "OOOOO")),
})
A_UPPER_ATK1 = _variant_upper(A_UPPER_IDLE, {
    # 突刺：细臂半伸（留出长刃空间），全身直线
    12: _at((5, "OOOOOO"), (11, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OGGGGO")),
    13: _at((4, "OBBEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGGGO")),
    14: _at((4, "OBEEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (25, "OGGGO")),
    15: _at((5, "OBBBOO"), (9, "OGGGO"), (15, "O" * 9), (26, "OOOOO")),
})
A_UPPER_SHOOT = _variant_upper(A_UPPER_IDLE, {
    # 臂炮：细长单管，与肩线齐平（射手风格——武器扛在臂上）
    8:  _at((10, "O" * 5), (15, "O" * 9), (24, "O" * 10)),
    9:  _at((10, "OBBBO"), (15, "OALLLLLAO"), (24, "OGGGGGGGGGO")),
    10: _at((10, "OBBBO"), (15, "OALLLLLAO"), (24, "OGGGGGGGGEO")),
    11: _at((10, "OOOOO"), (15, "OAACCAAAO"), (24, "OOOOOOOOOO")),
})
A_UPPER_BLOCK = _variant_upper(A_UPPER_IDLE, {
    # 窄盾：单臂竖条小盾（侧身受击面小 = 机动防御风格）
    10: _at((10, "OBBBO"), (15, "OALLLLLAO"), (26, "OGGGO")),
    11: _at((10, "OOOOO"), (15, "OAACCAAAO"), (26, "OGGGO")),
    12: _at((5, "OOOOOO"), (11, "OJO"), (15, "O" + "A" * 7 + "O"), (26, "OGEEO")),
    13: _at((4, "OBBEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (26, "OGGGO")),
    14: _at((4, "OBEEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (26, "OGGGO")),
    15: _at((5, "OBBBOO"), (9, "OGGGO"), (15, "O" * 9), (26, "OOOOO")),
})
A_UPPER_HURT = [
    # 后仰：窄身稳（头仅移 1 格向左），天线后倒（垂直竖立，斜线会断），
    # 腰腹(行12-15)保持 idle 原位 x15——对齐腿髋 x15-23，上身后仰靠头/胸错位表达
    _at(),
    _at((16, "O")),
    _at((16, "O")),
    _at((13, "O" * 9)),
    _at((13, "O" + "A" * 7 + "O")),
    _at((13, "OA" + "C" * 5 + "AO"), (23, "OJO")),
    _at((13, "O" + "A" * 7 + "O"), (23, "OJO")),
    _at((13, "O" * 9), (23, "OJO")),
    _at((10, "O" * 5), (15, "O" * 9), (24, "O" * 5)),
    _at((10, "OBBBO"), (15, "OALLLLLAO"), (24, "OBBBO")),
    _at((10, "OBBBO"), (15, "OALLLLLAO"), (24, "OAAAO")),
    _at((10, "OOOOO"), (15, "OAACCAAAO"), (24, "OOOOO")),
    _at((5, "OOOOOO"), (11, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OGGO")),
    _at((4, "OBBEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGO")),
    _at((4, "OBEEEO"), (9, "OGGGO"), (15, "O" + "B" * 7 + "O"), (25, "OGG")),
    _at((5, "OBBBOO"), (9, "OGGGO"), (15, "O" * 9), (25, "OG")),
]

# ---- VERDANT 翠岚：藤鞭型。臂最长，鞭走弧线 ----
V_UPPER_ATK0 = _variant_upper(V_UPPER_IDLE, {
    # 上扬：手臂高举过头（藤蔓舒展）
    5: _at((15, "OA" + "C" * 5 + "AO"), (26, "OJO")),
    6: _at((15, "O" + "A" * 7 + "O"), (26, "OJO")),
    7: _at((15, "O" * 9), (26, "OJO")),
})
V_UPPER_ATK1 = _variant_upper(V_UPPER_IDLE, {
    # 前甩：长臂伸到最远（24-32，全场最长臂）
    12: _at((10, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OGGGGGGGO")),
    13: _at((10, "OGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGGGGGGO")),
    14: _at((10, "OGGO"), (15, "OBBBBBBBO"), (25, "OGGGGGGO")),
    15: _at((10, "OGGO"), (15, "O" * 9), (26, "OOOOOO")),
})
V_UPPER_SHOOT = _variant_upper(V_UPPER_IDLE, {
    # 藤炮：臂化炮管，管身藤蔓缠绕（A 纹理）
    8:  _at((9, "O" * 6), (15, "O" * 9), (24, "O" * 9)),
    9:  _at((9, "OBBBBO"), (15, "OALLLLLAO"), (24, "OGGAGGAGO")),
    10: _at((9, "OBBBBO"), (15, "OALLLLLAO"), (24, "OGGAGGAEO")),
    11: _at((9, "OOBBOO"), (15, "OAACCAAAO"), (24, "OOOOOOOOO")),
})
V_UPPER_BLOCK = _variant_upper(V_UPPER_IDLE, {
    # 藤环盾：环形（外圈装甲、中空能量感）
    10: _at((9, "OBBBBO"), (15, "OALLLLLAO"), (25, "OOOOOOO")),
    11: _at((9, "OOBBOO"), (15, "OAACCAAAO"), (24, "OGOAAOGO")),
    12: _at((10, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OGOCCOGO")),
    13: _at((10, "OGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGOAAOGO")),
    14: _at((10, "OGGO"), (15, "OBBBBBBBO"), (25, "OOOOOOO")),
    15: _at((10, "OGGO"), (15, "O" * 9), (26, "OOOOO")),
})
V_UPPER_HURT = [
    # 后仰：双天线整齐后倒（藤蔓受创）
    _at((14, "O")),
    _at((14, "O"), (22, "O")),
    _at((14, "O"), (22, "O")),
    _at((14, "O" * 9)),
    _at((14, "O" + "A" * 7 + "O")),
    _at((14, "OA" + "C" * 5 + "AO"), (23, "OJO")),
    _at((14, "O" + "A" * 7 + "O"), (23, "OJO")),
    _at((14, "O" * 9), (23, "OJO")),
    _at((9, "O" * 6), (15, "O" * 9), (24, "O" * 6)),
    _at((9, "OBBBBO"), (15, "OALLLLLAO"), (24, "OBBBBO")),
    _at((9, "OBBBBO"), (15, "OALLLLLAO"), (24, "OBBBBO")),
    _at((9, "OOBBOO"), (15, "OAACCAAAO"), (24, "OOBBOO")),
    _at((10, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OGGO")),
    _at((10, "OGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGO")),
    _at((10, "OGGO"), (15, "OBBBBBBBO"), (25, "OGGO")),
    _at((10, "OGGO"), (15, "O" * 9), (25, "OGO")),
]

# ---- VIOLET 紫电：电锯型。臂带电弧，锯齿突刺 ----
P_UPPER_ATK0 = _variant_upper(P_UPPER_IDLE, {
    # 举锯：单臂上举过肩
    6: _at((13, "O" + "A" * 9 + "O"), (25, "OJO")),
    7: _at((13, "O" * 11), (25, "OJO")),
})
P_UPPER_ATK1 = _variant_upper(P_UPPER_IDLE, {
    # 突刺：臂前伸，臂身电弧迸发
    12: _at((10, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OGGGGO")),
    13: _at((10, "OGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGGEO")),
    14: _at((10, "OGGO"), (15, "OBBBBBBBO"), (25, "OGGGO")),
    15: _at((10, "OGGO"), (15, "O" * 9), (26, "OOOOO")),
})
P_UPPER_SHOOT = _variant_upper(P_UPPER_IDLE, {
    # 电光发射器：短粗炮口双 E 极
    8:  _at((8, "OOOO"), (12, "O" * 12), (24, "OOOOOOO")),
    9:  _at((7, "OBBOO"), (12, "OA" + "L" * 8 + "AO"), (24, "OGGGGGGO")),
    10: _at((6, "OBBBBO"), (12, "OA" + "L" * 8 + "AO"), (24, "OGGGEEEO")),
    11: _at((7, "OOBOO"), (12, "OAA" + "C" * 6 + "AAO"), (24, "OOOOOOO")),
})
P_UPPER_BLOCK = _variant_upper(P_UPPER_IDLE, {
    # 电磁盾：E 纹交错的能量壁
    10: _at((6, "OBBBBO"), (12, "OA" + "L" * 8 + "AO"), (25, "OEOOOEO")),
    11: _at((7, "OOBOO"), (12, "OAA" + "C" * 6 + "AAO"), (24, "OEOEOEO")),
    12: _at((10, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OGGGGGGO")),
    13: _at((10, "OGGO"), (15, "O" + "B" * 7 + "O"), (24, "OEOEOEO")),
    14: _at((10, "OGGO"), (15, "OBBBBBBBO"), (25, "OEOOOEO")),
    15: _at((10, "OGGO"), (15, "O" * 9), (26, "OOOOOO")),
})
P_UPPER_HURT = [
    # 后仰：尖刺冠后倒，电弧沿臂侧迸散（每个 E 都与机体相邻，不悬空）
    _at((16, "O")),
    _at((14, "O"), (16, "O"), (19, "O")),
    _at((14, "O"), (16, "O"), (19, "O")),
    _at((12, "O" * 11)),
    _at((12, "O" + "A" * 9 + "O")),
    _at((12, "OA" + "C" * 7 + "AO"), (22, "OJO"), (25, "E")),
    _at((12, "O" + "A" * 9 + "O"), (22, "OJO"), (25, "E")),
    _at((12, "O" * 11), (22, "OJO"), (25, "E")),
    _at((8, "OOOO"), (12, "O" * 12), (23, "E"), (24, "OOOO")),
    _at((7, "OBBOO"), (12, "OA" + "L" * 8 + "AO"), (24, "OOBBO")),
    _at((6, "OBBBBO"), (12, "OA" + "L" * 8 + "AO"), (24, "OBBBBO")),
    _at((7, "OOBOO"), (12, "OAA" + "C" * 6 + "AAO"), (24, "OOOBO")),
    _at((10, "OJO"), (15, "O" + "A" * 7 + "O"), (24, "OJO")),
    _at((10, "OGGO"), (15, "O" + "B" * 7 + "O"), (24, "OGGO")),
    _at((10, "OGGO"), (15, "OBBBBBBBO"), (25, "OGGO")),
    _at((10, "OGGO"), (15, "O" * 9), (26, "OGGO")),
]


PAL_PARTS = {
    "p1": {"upper_idle": G_UPPER_IDLE, "upper_atk0": G_UPPER_ATK0,
           "upper_atk1": G_UPPER_ATK1, "upper_shoot": G_UPPER_SHOOT,
           "upper_block": G_UPPER_BLOCK, "upper_hurt": G_UPPER_HURT,
           "legs_idle": G_LEGS_IDLE,
           "legs_walk_a": G_LEGS_WALK_A, "legs_walk_b": _legs_up(G_LEGS_IDLE),
           "legs_jump": G_LEGS_JUMP},
    "p2": {"upper_idle": A_UPPER_IDLE, "upper_atk0": A_UPPER_ATK0,
           "upper_atk1": A_UPPER_ATK1, "upper_shoot": A_UPPER_SHOOT,
           "upper_block": A_UPPER_BLOCK, "upper_hurt": A_UPPER_HURT,
           "legs_idle": A_LEGS_IDLE,
           "legs_walk_a": A_LEGS_WALK_A, "legs_walk_b": _legs_up(A_LEGS_IDLE),
           "legs_jump": A_LEGS_JUMP},
    "p3": {"upper_idle": V_UPPER_IDLE, "upper_atk0": V_UPPER_ATK0,
           "upper_atk1": V_UPPER_ATK1, "upper_shoot": V_UPPER_SHOOT,
           "upper_block": V_UPPER_BLOCK, "upper_hurt": V_UPPER_HURT,
           "legs_idle": V_LEGS_IDLE,
           "legs_walk_a": V_LEGS_WALK_A, "legs_walk_b": _legs_up(V_LEGS_IDLE),
           "legs_jump": V_LEGS_JUMP},
    "p4": {"upper_idle": P_UPPER_IDLE, "upper_atk0": P_UPPER_ATK0,
           "upper_atk1": P_UPPER_ATK1, "upper_shoot": P_UPPER_SHOOT,
           "upper_block": P_UPPER_BLOCK, "upper_hurt": P_UPPER_HURT,
           "legs_idle": P_LEGS_IDLE,
           "legs_walk_a": P_LEGS_WALK_A, "legs_walk_b": _legs_up(P_LEGS_IDLE),
           "legs_jump": P_LEGS_JUMP},
}


# ================================================================ 光刃覆盖（批次 A：L1 光刃）
# 每台机甲的 atk1/atk0/shoot/thrust/rise/sweep 等帧，可定制专属光刃 style 与位置。
# 未列出的帧继承 FRAMES 通用参数。
# 待机/移动帧的持刃姿态：刃柄须紧贴肩甲外缘（右缘+1、且 y 落在肩甲所在行），
# 这样既「扛在肩上」与机体 4-连通，又不会被肩甲分层遮掉刃身。
# 各台肩甲右缘：GARNET 32 / AZURE 28 / VERDANT 29 / VIOLET 29。
PAL_SABER = {
    # GARNET：粗臂短斧（reach 分配偏臂），肩顶发力下劈
    "p1": {
        "idle":   (33, 10, -80, 8, "axe"),
        "walk_a": (33, 10, -80, 8, "axe"),
        "walk_b": (33, 10, -80, 8, "axe"),
        "jump":   (33, 10, -88, 8, "axe"),
        "atk0":   (33, 14, -62, 11, "axe"),
        "atk1":   (32, 13, 18, 8, "axe"),
        "atk2":   (31, 13, 35, 8, "axe"),
        "shoot":  None,
        "thrust": (32, 13, 0, 8, "axe"),
        "rise":   (32, 12, -75, 9, "axe"),
        "sweep":  (32, 13, 25, 8, "axe"),
        "hurt":   (28, 8, 65, 9, "axe"),
    },
    # AZURE：细臂长剑（reach 分配偏刃），直线突刺
    "p2": {
        "idle":   (29, 10, -88, 9, "lance"),
        "walk_a": (29, 10, -88, 9, "lance"),
        "walk_b": (29, 10, -88, 9, "lance"),
        "jump":   (29, 10, -80, 9, "lance"),
        "atk0":   (30, 12, -38, 9, "lance"),
        "atk1":   (30, 12, -3, 9, "lance"),
        "atk2":   (29, 13, 30, 9, "lance"),
        "shoot":  None,
        "thrust": (30, 12, 0, 9, "lance"),
        "rise":   (29, 11, -70, 8, "lance"),
        "sweep":  (30, 13, 22, 8, "lance"),
        "hurt":   (26, 8, 70, 10, "lance"),
    },
    # VERDANT：最长臂 + 短鞭（鞭走弧线，前甩下垂）
    "p3": {
        "idle":   (30, 11, 60, 7, "whip"),
        "walk_a": (30, 11, 60, 7, "whip"),
        "walk_b": (30, 11, 60, 7, "whip"),
        "jump":   (30, 11, 40, 7, "whip"),
        "atk0":   (28, 4, -55, 9, "whip"),
        "atk1":   (32, 13, 35, 7, "whip"),
        "atk2":   (30, 13, 40, 8, "whip"),
        "shoot":  None,
        "thrust": (32, 12, 8, 7, "whip"),
        "rise":   (32, 12, -55, 8, "whip"),
        "sweep":  (32, 14, 30, 7, "whip"),
        "hurt":   (26, 8, 75, 8, "whip"),
    },
    # VIOLET：中臂电锯，臂身电弧
    "p4": {
        "idle":   (30, 10, -88, 9, "saw"),
        "walk_a": (30, 10, -88, 9, "saw"),
        "walk_b": (30, 10, -88, 9, "saw"),
        "jump":   (30, 10, -80, 9, "saw"),
        "atk0":   (27, 6, -30, 10, "saw"),
        "atk1":   (30, 12, -10, 9, "saw"),
        "atk2":   (28, 13, 35, 8, "saw"),
        "shoot":  None,
        "thrust": (30, 12, -3, 9, "saw"),
        "rise":   (30, 11, -65, 8, "saw"),
        "sweep":  (30, 13, 25, 8, "saw"),
        "hurt":   (25, 8, 80, 8, "saw"),
    },
}


def build_mech_frames():
    """返回 frames[pal][name][facing] -> Surface（facing: 1 右, -1 左）。
    装配：通用部件 + PAL_PARTS 覆盖 + FRAMES 光剑参数 + PAL_SABER 覆盖。
    """
    global WHITE_PALETTE
    white = {k: (248, 248, 250) for k in MECH_PALETTES["p1"]}
    out = {}
    for pal_name, palette in MECH_PALETTES.items():
        per_pal = {}
        pal_overrides = PAL_PARTS.get(pal_name, {})
        pal_sabers = PAL_SABER.get(pal_name, {})
        for name, (_tag, upper_key, leg_key, saber) in FRAMES.items():
            upper = pal_overrides.get(upper_key, BASE_PARTS[upper_key])
            legs = (pal_overrides.get(leg_key, BASE_PARTS[leg_key])
                    if leg_key else None)
            saber_used = pal_sabers.get(name, saber)
            rows = list(upper) + (list(legs) if legs else [])
            grid = _grid_from_rows(rows)
            _draw_saber(grid, saber_used, palette)
            right = _render_grid(grid, palette)
            left = pygame.transform.flip(right, True, False)
            wgrid = _grid_from_rows(rows)
            _draw_saber(wgrid, saber_used, white)
            wright = _render_grid(wgrid, white)
            wleft = pygame.transform.flip(wright, True, False)
            per_pal[name] = {1: right, -1: left,
                              "flash1": wright, "flash-1": wleft}
        out[pal_name] = per_pal
    WHITE_PALETTE = white
    return out


def build_bolts():
    """返回 bolts[color][bright(0/1)][facing] -> Surface。"""
    out = {}
    for cname, pal in BOLT_PALETTES.items():
        per = []
        for mapping in (BOLT_MAP, BOLT_MAP_BRIGHT):
            grid = _grid_from_rows(mapping)
            base = _render_grid(grid, pal)
            flipped = pygame.transform.flip(base, True, False)
            per.append({1: base, -1: flipped})
        out[cname] = per
    return out


# ================================================================ 场景预渲染

def _lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


# 场地主题（阶段7）：夜战 / 熔炉黎明——同名键对应 settings.STAGES
THEMES = {
    "night": {
        "sky_top": (14, 12, 38), "sky_bot": (72, 38, 70),
        "stars": 90,
        "star_cols": [(180, 180, 210), (120, 120, 160), (230, 230, 240)],
        "far": (36, 26, 56), "near": (22, 16, 38),
        "win_far": (150, 120, 80), "win_near": (120, 90, 70),
        "ground": (52, 50, 68), "ground_dark": (38, 36, 52),
        "ground_hi": (86, 84, 104), "rivet": (70, 68, 88),
        "hazard": (66, 62, 84),
    },
    "dawn": {
        "sky_top": (40, 18, 44), "sky_bot": (235, 130, 62),
        "stars": 14,
        "star_cols": [(255, 210, 160), (255, 180, 130)],
        "far": (70, 34, 50), "near": (40, 20, 32),
        "win_far": (255, 190, 110), "win_near": (255, 160, 90),
        "ground": (78, 56, 54), "ground_dark": (56, 40, 40),
        "ground_hi": (128, 96, 84), "rivet": (104, 78, 70),
        "hazard": (122, 84, 52),
    },
}


def build_background(seed=7, theme="night"):
    """预渲染 480x270 战场背景：天空、天体、双层废墟、金属地面（按主题换装）。"""
    th = THEMES.get(theme, THEMES["night"])
    rng = random.Random(seed)
    bg = pygame.Surface((INTERNAL_W, INTERNAL_H))

    # --- 天空（量化成色带，复古感）---
    bands = 9
    for i in range(bands):
        t = i / (bands - 1)
        color = _lerp(th["sky_top"], th["sky_bot"], t)
        y0 = int(i * GROUND_Y / bands)
        y1 = int((i + 1) * GROUND_Y / bands)
        bg.fill(color, (0, y0, INTERNAL_W, y1 - y0))

    # --- 星空 ---
    for _ in range(th["stars"]):
        x, y = rng.randrange(INTERNAL_W), rng.randrange(int(GROUND_Y * 0.72))
        c = rng.choice(th["star_cols"])
        bg.set_at((x, y), c)

    # --- 天体：夜=缺角月亮；黎明=带光晕的朝阳 ---
    if theme == "dawn":
        mx, my, r = 92, 58, 20
        bg.fill(_lerp(th["sky_bot"], (255, 220, 150), 0.35),
                (mx - r - 10, my - r - 10, (r + 10) * 2, (r + 10) * 2))
        pygame.draw.circle(bg, (255, 226, 160), (mx, my), r + 5)
        pygame.draw.circle(bg, (255, 206, 110), (mx, my), r)
        pygame.draw.circle(bg, (255, 240, 200), (mx - 5, my - 6), 4)
        pygame.draw.line(bg, (70, 30, 46), (mx - r - 14, my + 4),
                         (mx + r + 14, my + 2), 2)   # 地平线云带
    else:
        mx, my, r = 396, 44, 17
        pygame.draw.circle(bg, (232, 228, 205), (mx, my), r)
        pygame.draw.circle(bg, (206, 200, 178), (mx - 4, my + 3), 4)
        pygame.draw.circle(bg, (206, 200, 178), (mx + 6, my - 5), 3)
        pygame.draw.circle(bg, (206, 200, 178), (mx + 2, my + 7), 2)
        pygame.draw.circle(bg, th["sky_top"], (mx + 11, my - 9), 4)  # 缺角

    # --- 远景废墟剪影 ---
    far = th["far"]
    x = -6
    while x < INTERNAL_W:
        w = rng.randrange(18, 42)
        h = rng.randrange(26, 66)
        top = GROUND_Y - 34 - h
        bg.fill(far, (x, top, w, h + 34))
        # 破损楼顶豁口
        notch = rng.randrange(3, max(4, w - 4))
        bg.fill((0, 0, 0, 0) if False else _lerp(far, (14, 12, 38), 0.55),
                (x + notch, top, min(6, w - notch), 8))
        # 零星亮窗
        for _ in range(rng.randrange(0, 4)):
            wx = x + rng.randrange(2, max(3, w - 2))
            wy = top + rng.randrange(4, max(5, h - 2))
            bg.set_at((wx, wy), th["win_far"])
        x += w + rng.randrange(2, 10)

    # --- 近景废墟剪影（更深、更高细节）---
    near = th["near"]
    x = -10
    while x < INTERNAL_W:
        w = rng.randrange(24, 56)
        h = rng.randrange(12, 40)
        top = GROUND_Y - 12 - h
        bg.fill(near, (x, top, w, h + 12))
        if rng.random() < 0.5:      # 天线
            ax = x + w // 2
            pygame.draw.line(bg, near, (ax, top), (ax, top - rng.randrange(6, 16)), 1)
        for _ in range(rng.randrange(0, 3)):
            wx = x + rng.randrange(2, max(3, w - 2))
            wy = top + rng.randrange(3, max(4, h - 2))
            bg.set_at((wx, wy), th["win_near"])
        x += w + rng.randrange(6, 18)

    # --- 金属地面 ---
    base = th["ground"]
    dark = th["ground_dark"]
    bg.fill(base, (0, GROUND_Y, INTERNAL_W, INTERNAL_H - GROUND_Y))
    bg.fill(th["ground_hi"], (0, GROUND_Y, INTERNAL_W, 2))    # 顶缘高光
    bg.fill(dark, (0, GROUND_Y + 22, INTERNAL_W, INTERNAL_H - GROUND_Y - 22))
    for gx in range(0, INTERNAL_W, 32):                        # 面板缝
        pygame.draw.line(bg, dark, (gx, GROUND_Y + 2), (gx, GROUND_Y + 20), 1)
        for ry in (GROUND_Y + 6, GROUND_Y + 14):
            bg.set_at((gx + 4, ry), th["rivet"])
    for gx in range(0, INTERNAL_W, 48):                        # 警示斜纹
        for i in range(8):
            bg.set_at((gx + i, GROUND_Y + 24 + i % 3), th["hazard"])
    return bg


# ================================================================ 字体

_FONT_CACHE = {}


def get_font(size, bold=True):
    """优先 CJK 字体（菜单中文），退回默认字体。"""
    key = (size, bold)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = pygame.font.SysFont(
                "microsoftyahei,msyh,simhei,consolas,arial", size, bold=bold)
        except Exception:
            _FONT_CACHE[key] = pygame.font.Font(None, size)
    return _FONT_CACHE[key]


# ================================================================ 素材总览（美术校对）

if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((1, 1))
    frames = build_mech_frames()
    bolts = build_bolts()

    names = list(FRAMES.keys())
    pal_names = list(MECH_PALETTES.keys())
    cell_w, cell_h = SPRITE_W + 8, SPRITE_H + 18
    sheet = pygame.Surface((cell_w * len(names), cell_h * len(pal_names) + 30))
    sheet.fill((34, 32, 44))
    for pi, pal in enumerate(pal_names):
        for ni, name in enumerate(names):
            x, y = ni * cell_w + 4, pi * cell_h + 20
            sheet.blit(frames[pal][name][1], (x, y))
        label = get_font(12).render(
            f"{pal}: " + " ".join(names), True, (240, 240, 240))
        sheet.blit(label, (4, pi * cell_h + 2))
    # 光束弹
    by = len(pal_names) * cell_h + 4
    sheet.blit(get_font(12).render("bolts:", True, (240, 240, 240)), (4, by))
    for ci, cname in enumerate(bolts):
        for b in (0, 1):
            sheet.blit(bolts[cname][b][1], (60 + ci * 60 + b * 24, by))
    pygame.image.save(sheet, "preview.png")
    print("preview.png saved:", sheet.get_size())
