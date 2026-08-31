# -*- coding: utf-8 -*-
"""《钢铁对决 MECH DUEL》内置像素素材系统。

素材方案（零外部资源）：
- 机体：手绘字符画，按「上身姿势部件 × 腿部部件」拼装成 40x30 画布，运行时 2x 放大。
  光剑不画进字符图，而是作为程序化光刃（角度/长度参数表）叠加渲染，
  叠加时只写入空像素格，因此剑刃会自然被身体遮挡（剑在身后时正确分层）。
- 双机甲差异：同一套骨架 + p1/p2 两套调色板。
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
# (帧名, 上身, 腿部, 光剑参数(origin_x, origin_y, 角度°, 长度) 或 None)
# 角度：-90 为正上，0 为正前（朝右），正值向下。

FRAMES = {
    "idle":  ("idle",  UPPER_IDLE,  LEGS_IDLE,  (27, 13, -90, 11)),
    "walk_a": ("walk_a", UPPER_IDLE, LEGS_WALK_A, (27, 13, -90, 11)),
    "walk_b": ("walk_b", UPPER_IDLE, LEGS_WALK_B, (27, 13, -90, 11)),
    "jump":  ("jump",  UPPER_IDLE,  LEGS_JUMP,  (27, 13, -80, 10)),
    "atk0":  ("atk0",  UPPER_ATK0,  LEGS_WALK_A, (23, 9, -145, 13)),
    "atk1":  ("atk1",  UPPER_ATK1,  LEGS_WALK_A, (25, 10, -8, 14)),
    "atk2":  ("atk2",  UPPER_IDLE,  LEGS_WALK_A, (26, 13, 35, 11)),
    # 重击变体专属动作帧（复用上身像素 + 光剑参数重组，无新画）：
    # thrust=水平直刺 rise=升斩 sweep=下段低扫 bash=无剑肩撞 toss=空手投掷
    "thrust": ("thrust", UPPER_ATK1, LEGS_WALK_A, (24, 10, 0, 15)),
    "rise":   ("rise",   UPPER_ATK1, LEGS_IDLE,   (25, 13, -72, 13)),
    "sweep":  ("sweep",  UPPER_ATK1, LEGS_WALK_B, (27, 13, 28, 13)),
    "bash":   ("bash",   UPPER_ATK1, LEGS_WALK_A, None),
    "toss":   ("toss",   UPPER_ATK0, LEGS_WALK_B, None),
    "shoot": ("shoot", UPPER_SHOOT0, LEGS_WALK_A, (26, 14, -60, 7)),
    "block": ("block", UPPER_BLOCK, LEGS_IDLE,  None),
    "hurt":  ("hurt",  UPPER_HURT,  LEGS_IDLE,  (25, 9, -115, 8)),
    "ko":    ("ko",    FRAME_KO,    None,       None),
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
    """把光刃画进画布空格（不覆盖已有像素 → 剑可被身体遮挡）。"""
    if not params:
        return
    import math
    ox, oy, ang, ln = params
    rad = math.radians(ang)
    dx, dy = math.cos(rad), math.sin(rad)
    main = palette["S"]
    for i in range(int(ln * PIX) + 1):
        t = i / PIX
        x = int(round(ox + dx * t))
        y = int(round(oy + dy * t))
        for px_, py_ in ((x, y), (x, y + 1)):
            if 0 <= px_ < FRAME_W and 0 <= py_ < FRAME_H and grid[py_][px_] == ".":
                grid[py_][px_] = "S"
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


def build_mech_frames():
    """返回 frames[pal][name][facing] -> Surface（facing: 1 右, -1 左）。"""
    global WHITE_PALETTE
    white = {k: (248, 248, 250) for k in MECH_PALETTES["p1"]}
    out = {}
    for pal_name, palette in MECH_PALETTES.items():
        per_pal = {}
        for name, (_tag, upper, legs, saber) in FRAMES.items():
            rows = list(upper) + (legs if legs else [])
            grid = _grid_from_rows(rows)
            _draw_saber(grid, saber, palette)
            right = _render_grid(grid, palette)
            left = pygame.transform.flip(right, True, False)
            wgrid = _grid_from_rows(rows)
            _draw_saber(wgrid, saber, white)
            wright = _render_grid(wgrid, white)
            wleft = pygame.transform.flip(wright, True, False)
            per_pal[name] = {1: right, -1: left, "flash1": wright, "flash-1": wleft}
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
