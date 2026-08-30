# -*- coding: utf-8 -*-
"""界面：HUD（血条/能量条/计时器/回合星）、标题菜单、胜负结算、中央横幅。"""

import pygame

from settings import (INTERNAL_W, INTERNAL_H, COLORS, ROUND_TIME,
                      ROUNDS_TO_WIN, RANGED_COST, ENERGY_MAX,
                      GUARD_MAX, SUPER_MAX)
from assets import get_font, SPRITE_H

BAR_MARGIN = 14
BAR_W = 176
BAR_H = 11
ENERGY_H = 5
GUARD_H = 4
SUPER_H = 3


class HUD:
    def __init__(self):
        self.ghost = {}     # id(mech) -> 幽灵血条值（缓慢追落，打击感）

    def reset(self):
        self.ghost = {}

    def draw(self, surf, p1, p2, wins1, wins2, timer_frames, training=False):
        self._bar(surf, p1, left=True)
        self._bar(surf, p2, left=False)
        self._pips(surf, wins1, left=True)
        self._pips(surf, wins2, left=False)
        self._timer(surf, timer_frames, training)

    def _bar(self, surf, m, left):
        x0 = BAR_MARGIN if left else INTERNAL_W - BAR_MARGIN - BAR_W
        y0 = 10
        # 底框
        pygame.draw.rect(surf, COLORS["hud_bg"], (x0 - 2, y0 - 2, BAR_W + 4, BAR_H + 4))
        pygame.draw.rect(surf, COLORS["hud_frame"], (x0 - 2, y0 - 2, BAR_W + 4, BAR_H + 4), 1)

        ghost = self.ghost.setdefault(id(m), float(m.hp))
        ghost = max(m.hp, ghost - 0.55)
        self.ghost[id(m)] = ghost

        hp_w = int(BAR_W * m.hp / m.max_hp)
        gh_w = int(BAR_W * ghost / m.max_hp)
        hp_col = COLORS["hp_p1"] if left else COLORS["hp_p2"]
        # 幽灵（掉血余像）
        if left:
            surf.fill(COLORS["hp_ghost"], (x0 + hp_w, y0, gh_w - hp_w, BAR_H))
        else:
            gx = x0 + BAR_W - gh_w
            surf.fill(COLORS["hp_ghost"], (gx, y0, gh_w - hp_w, BAR_H))
        # 当前血量（从中央向外保留：P1 靠左锚点为左端？格斗游戏习惯从外侧锚定）
        if left:
            surf.fill(hp_col, (x0, y0, hp_w, BAR_H))
        else:
            surf.fill(hp_col, (x0 + BAR_W - hp_w, y0, hp_w, BAR_H))
        # 高光线
        surf.fill((255, 255, 255) if not left else (255, 200, 190),
                  (x0 if left else x0 + BAR_W - hp_w, y0, max(hp_w, 0), 2))

        # 能量条
        ey = y0 + BAR_H + 3
        pygame.draw.rect(surf, COLORS["hud_bg"], (x0 - 2, ey - 1, BAR_W + 4, ENERGY_H + 2))
        e_w = int(BAR_W * m.energy / ENERGY_MAX)
        e_col = COLORS["energy"] if m.energy >= RANGED_COST else COLORS["energy_low"]
        if m.energy >= ENERGY_MAX:            # 能量满：超必杀就绪闪烁提示
            blink = (pygame.time.get_ticks() // 260) % 2 == 0
            e_col = (255, 255, 240) if blink else (255, 214, 100)
        if left:
            surf.fill(e_col, (x0, ey, e_w, ENERGY_H))
        else:
            surf.fill(e_col, (x0 + BAR_W - e_w, ey, e_w, ENERGY_H))

        # 防御槽（耗尽 → GUARD BREAK）
        gy = ey + ENERGY_H + 2
        pygame.draw.rect(surf, COLORS["hud_bg"], (x0 - 2, gy - 1, BAR_W + 4, GUARD_H + 2))
        g_w = int(BAR_W * max(0, m.guard) / GUARD_MAX)
        g_col = ((230, 90, 70) if m.guard <= GUARD_MAX * 0.3
                 else (150, 150, 175))
        if left:
            surf.fill(g_col, (x0, gy, g_w, GUARD_H))
        else:
            surf.fill(g_col, (x0 + BAR_W - g_w, gy, g_w, GUARD_H))

        # 超必杀槽
        sy = gy + GUARD_H + 2
        pygame.draw.rect(surf, COLORS["hud_bg"], (x0 - 2, sy - 1, BAR_W + 4, SUPER_H + 2))
        s_w = int(BAR_W * m.super / SUPER_MAX)
        s_col = (255, 214, 100) if m.super >= SUPER_MAX else (200, 160, 90)
        if left:
            surf.fill(s_col, (x0, sy, s_w, SUPER_H))
        else:
            surf.fill(s_col, (x0 + BAR_W - s_w, sy, s_w, SUPER_H))

        # 名字
        name = f"{m.spec['name']}·{m.spec['cn_name']}"
        fnt = get_font(9)
        img = fnt.render(name, True, (230, 230, 240))
        if left:
            surf.blit(img, (x0, y0 - 11))
        else:
            surf.blit(img, (x0 + BAR_W - img.get_width(), y0 - 11))

    def _pips(self, surf, wins, left):
        y = 10 + BAR_H + 3 + ENERGY_H + 2 + GUARD_H + 2 + SUPER_H + 2 + 4
        for i in range(ROUNDS_TO_WIN):
            size = 5
            if left:
                cx = BAR_MARGIN + 6 + i * (size + 5)
            else:
                cx = INTERNAL_W - BAR_MARGIN - 6 - i * (size + 5)
            col = COLORS["timer"] if i < wins else (60, 58, 76)
            pts = [(cx, y - 3), (cx + 3, y), (cx, y + 3), (cx - 3, y)]
            pygame.draw.polygon(surf, col, pts)

    def _timer(self, surf, timer_frames, training=False):
        if training:
            fnt = get_font(14)
            txt = "∞"
            img = fnt.render(txt, True, COLORS["timer"])
            shadow = fnt.render(txt, True, (20, 16, 28))
            cx = INTERNAL_W // 2
            surf.blit(shadow, (cx - img.get_width() // 2 + 2, 7 + 2))
            surf.blit(img, (cx - img.get_width() // 2, 7))
            fnt2 = get_font(8)
            sub = fnt2.render("TRAINING", True, (200, 200, 220))
            surf.blit(sub, (cx - sub.get_width() // 2, 26))
            return
        secs = max(0, -(-timer_frames // 60))   # 向上取整
        fnt = get_font(17)
        txt = f"{secs:02d}"
        img = fnt.render(txt, True, COLORS["timer"])
        shadow = fnt.render(txt, True, (20, 16, 28))
        cx = INTERNAL_W // 2
        surf.blit(shadow, (cx - img.get_width() // 2 + 2, 7 + 2))
        surf.blit(img, (cx - img.get_width() // 2, 7))
        fnt2 = get_font(8)
        sub = fnt2.render("TIME", True, (200, 200, 220))
        surf.blit(sub, (cx - sub.get_width() // 2, 28))


def banner(surf, text, sub=None, pulse=False):
    fnt = get_font(26)
    img = fnt.render(text, True, COLORS["banner"])
    shadow = fnt.render(text, True, COLORS["banner_sh"])
    cx, cy = INTERNAL_W // 2, INTERNAL_H // 2 - 24
    if pulse:                       # 呼吸缩放（FIGHT! 提示）
        ph = (pygame.time.get_ticks() // 9) % 8
        k = 1.0 + 0.06 * (ph / 8.0 if ph < 4 else (8 - ph) / 8.0)
        img = pygame.transform.scale(
            img, (int(img.get_width() * k), int(img.get_height() * k)))
        shadow = pygame.transform.scale(
            shadow, (int(shadow.get_width() * k), int(shadow.get_height() * k)))
    surf.blit(shadow, (cx - img.get_width() // 2 + 3, cy - img.get_height() // 2 + 3))
    surf.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))
    if sub:
        fnt2 = get_font(12)
        img2 = fnt2.render(sub, True, (235, 220, 190))
        surf.blit(img2, (cx - img2.get_width() // 2, cy + 22))


DIFF_CN = {"easy": "简单", "normal": "普通", "hard": "困难"}


def draw_menu(surf, bg, frames, t, difficulty="normal"):
    surf.blit(bg, (0, 0))
    # 三机甲登场姿势（贴两侧与底部，避免与说明文字重叠）
    idle_p1 = frames["p1"]["idle"][1]
    idle_p2 = frames["p2"]["idle"][-1]
    idle_p3 = frames["p3"]["idle"][-1]
    bob = 2 if (t // 22) % 2 else 0
    surf.blit(idle_p1, (10, 236 - SPRITE_H + bob))
    surf.blit(idle_p2, (480 - 10 - idle_p2.get_width(), 236 - SPRITE_H + bob))
    surf.blit(idle_p3, (66, 236 - SPRITE_H + 4 - bob))

    fnt_big = get_font(34)
    title = fnt_big.render("MECH DUEL", True, (245, 240, 225))
    sh = fnt_big.render("MECH DUEL", True, (25, 14, 34))
    cx = INTERNAL_W // 2
    surf.blit(sh, (cx - title.get_width() // 2 + 3, 34 + 3))
    surf.blit(title, (cx - title.get_width() // 2, 34))
    fnt_cn = get_font(15)
    sub = fnt_cn.render("钢 铁 对 决", True, (250, 200, 120))
    surf.blit(sub, (cx - sub.get_width() // 2, 70))

    fnt_opt = get_font(12)
    rows = [
        ("[1] 双人对抗    2P  VS  2P", (230, 230, 240)),
        (f"[2] 挑战 AI     VS  CPU    难度:{DIFF_CN[difficulty]}",
         (230, 230, 240)),
        ("[3] 训练模式    FREE TRAINING", (230, 230, 240)),
        ("[4] AI 演示     CPU  VS  CPU", (230, 230, 240)),
        ("[5] 按键设置    KEY CONFIG", (230, 230, 240)),
    ]
    y0 = 100
    for i, (txt, col) in enumerate(rows):
        img = fnt_opt.render(txt, True, col)
        surf.blit(img, (cx - img.get_width() // 2, y0 + i * 16))
    blink = (t // 30) % 2 == 0
    if blink:
        hint = fnt_opt.render("按 1-5 选择 · TAB 切换 AI 难度 · M 静音",
                              True, (255, 214, 100))
        surf.blit(hint, (cx - hint.get_width() // 2, y0 + 5 * 16 + 4))

    fnt_help = get_font(9)
    h1 = fnt_help.render(
        "P1  A/D 移动  W 跳  S 防  J 斩  K 束  L 投  I 超杀(槽满)  双击方向 冲刺/后撤",
        True, (215, 160, 150))
    h2 = fnt_help.render(
        "P2  ←/→ 移动  ↑ 跳  ↓ 防  小键盘1 斩 2 束 3 投 4 超杀(可在[5]改键)",
        True, (150, 180, 230))
    surf.blit(h1, (cx - h1.get_width() // 2, 212))
    surf.blit(h2, (cx - h2.get_width() // 2, 226))
    h4 = fnt_help.render("空中可斩击 · 投技无视防御 · 落地按跳/防 受身 · 训练: F1 判定框 F2 假人格挡",
                         True, (170, 220, 255))
    surf.blit(h4, (cx - h4.get_width() // 2, 240))
    h3 = fnt_help.render("三局两胜 · 每局 60 秒 · R 重开  ESC 菜单",
                         True, (170, 170, 190))
    surf.blit(h3, (cx - h3.get_width() // 2, 254))


def draw_select(surf, bg, frames, sel, t):
    """选人界面：P1 A/D+J，P2 ←/→+小键盘1（AI/训练模式 CPU 随机）。"""
    from settings import MECH_ORDER, MECH_SPECS
    surf.blit(bg, (0, 0))
    cx = INTERNAL_W // 2
    fnt_big = get_font(20)
    title = fnt_big.render("SELECT YOUR MECH 选择机体", True, (245, 240, 225))
    surf.blit(title, (cx - title.get_width() // 2, 26))
    if sel.mode == "ai":
        fnt_d = get_font(10)
        d = fnt_d.render(f"AI 难度: {DIFF_CN[sel.difficulty]}（菜单 TAB 切换）",
                         True, (255, 214, 100))
        surf.blit(d, (cx - d.get_width() // 2, 52))

    centers = [110, 240, 370]
    card = pygame.Rect(0, 0, 96, 118)
    fnt_nm = get_font(11)
    fnt_cn = get_font(9)
    for i, key in enumerate(MECH_ORDER):
        spec = MECH_SPECS[key]
        img = frames[spec["palette"]]["idle"][1]
        card.centerx = centers[i]
        card.top = 78
        cursor = sel.cur
        sel_col = (232, 76, 61)
        if cursor[0] == i:
            pygame.draw.rect(surf, sel_col, card, 1)
            pygame.draw.rect(surf, sel_col, card.inflate(4, 4), 1)
        p2_active = sel.mode == "2p"
        p2_col = (66, 134, 234)
        if p2_active and cursor[1] == i:
            pygame.draw.rect(surf, p2_col, card.inflate(-4, -4), 1)
        if (sel.locked[0] and cursor[0] == i) or (p2_active and sel.locked[1]
                                                  and cursor[1] == i):
            pygame.draw.rect(surf, (255, 214, 100), card.inflate(8, 8), 1)
        surf.blit(img, (centers[i] - img.get_width() // 2, card.top + 12))
        nm = fnt_nm.render(f"{spec['name']}·{spec['cn_name']}", True,
                           (240, 240, 245))
        surf.blit(nm, (centers[i] - nm.get_width() // 2, card.bottom - 22))
        tag = fnt_cn.render(spec["super_name"], True, (200, 190, 210))
        surf.blit(tag, (centers[i] - tag.get_width() // 2, card.bottom - 8))
        # P1 游标（上方红▲）
        if cursor[0] == i and (t // 14) % 2 == 0:
            px = centers[i]
            pygame.draw.polygon(surf, sel_col,
                                [(px, card.top - 12), (px - 6, card.top - 21),
                                 (px + 6, card.top - 21)])
            lab = fnt_cn.render("P1", True, sel_col)
            surf.blit(lab, (px - lab.get_width() // 2, card.top - 34))
        # P2 游标（下方蓝▼）
        if p2_active and cursor[1] == i and (t // 14) % 2 == 0:
            px = centers[i]
            pygame.draw.polygon(surf, p2_col,
                                [(px, card.bottom + 26), (px - 6, card.bottom + 35),
                                 (px + 6, card.bottom + 35)])
            lab = fnt_cn.render("P2", True, p2_col)
            surf.blit(lab, (px - lab.get_width() // 2, card.bottom + 38))

    fnt_h = get_font(10)
    if sel.mode == "2p":
        hint = "P1: A/D 选择 J 确认      P2: ←/→ 选择 小键盘1 确认      ESC 返回"
    elif sel.mode == "ai":
        hint = "P1: A/D 选择 J 确认      P2 由 CPU 随机体随机      ESC 返回"
    else:
        hint = "P1: A/D 选择 J 确认      假人随机使用机体      ESC 返回"
    img = fnt_h.render(hint, True, (235, 220, 190))
    surf.blit(img, (cx - img.get_width() // 2, 236))


# 按键设置界面用
ACT_CN = {"left": "左移", "right": "右移", "jump": "跳跃", "block": "防御",
          "melee": "斩击", "ranged": "光束", "throw": "投技", "super": "超必杀"}


def draw_keyconfig(surf, bg, rows, idx, waiting, t):
    """按键重映射界面：rows = [(玩家, 动作, 键名)]。"""
    surf.blit(bg, (0, 0))
    cx = INTERNAL_W // 2
    fnt_big = get_font(18)
    title = fnt_big.render("KEY CONFIG 按键设置", True, (245, 240, 225))
    surf.blit(title, (cx - title.get_width() // 2, 22))

    fnt = get_font(10)
    col_x = (60, 260)
    row_h = 17
    for i, (player, act, keyname) in enumerate(rows):
        col = 0 if player == "P1" else 1
        row_in_col = i % (len(rows) // 2)
        x = col_x[col]
        y = 56 + row_in_col * row_h
        selected = i == idx
        if selected:
            pygame.draw.rect(surf, (50, 44, 66), (x - 6, y - 3, 190, row_h))
            pygame.draw.rect(surf, (255, 214, 100), (x - 6, y - 3, 190, row_h), 1)
        tag = fnt.render(f"{player} {ACT_CN[act]}", True, (220, 220, 235))
        surf.blit(tag, (x, y))
        kv = fnt.render(keyname, True,
                        (255, 214, 100) if selected else (150, 190, 240))
        surf.blit(kv, (x + 120, y))

    blink = (t // 24) % 2 == 0
    fnt_h = get_font(10)
    if waiting:
        if blink:
            msg = fnt_h.render("…按任意键绑定（ESC 取消）", True, (255, 120, 90))
            surf.blit(msg, (cx - msg.get_width() // 2, 220))
    else:
        msg = fnt_h.render("↑/↓ 选择  回车 改键  R 恢复默认  ESC 返回",
                           True, (235, 220, 190))
        surf.blit(msg, (cx - msg.get_width() // 2, 220))
    note = fnt_h.render("手柄无需设置：P1=第一个手柄 P2=第二个，十字键移动 ABXY=斩/束/投/超",
                        True, (160, 170, 190))
    surf.blit(note, (cx - note.get_width() // 2, 244))


def draw_victory(surf, bg, winner_spec, wins1, wins2):
    surf.blit(bg, (0, 0))
    fnt = get_font(24)
    text = f"{winner_spec['name']} {winner_spec['cn_name']} WINS!"
    img = fnt.render(text, True, (250, 230, 150))
    sh = fnt.render(text, True, (25, 14, 34))
    cx = INTERNAL_W // 2
    surf.blit(sh, (cx - img.get_width() // 2 + 3, 92 + 3))
    surf.blit(img, (cx - img.get_width() // 2, 92))
    fnt2 = get_font(12)
    score = fnt2.render(f"{wins1} - {wins2}", True, (235, 235, 245))
    surf.blit(score, (cx - score.get_width() // 2, 126))
    blink = (pygame.time.get_ticks() // 400) % 2 == 0
    if blink:
        fnt3 = get_font(11)
        tip = fnt3.render("R 再来一局    ESC 返回菜单", True, (230, 230, 240))
        surf.blit(tip, (cx - tip.get_width() // 2, 160))
