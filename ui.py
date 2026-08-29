# -*- coding: utf-8 -*-
"""界面：HUD（血条/能量条/计时器/回合星）、标题菜单、胜负结算、中央横幅。"""

import pygame

from settings import (INTERNAL_W, INTERNAL_H, COLORS, ROUND_TIME,
                      ROUNDS_TO_WIN, RANGED_COST, ENERGY_MAX)
from assets import get_font, SPRITE_H

BAR_MARGIN = 14
BAR_W = 176
BAR_H = 11
ENERGY_H = 5


class HUD:
    def __init__(self):
        self.ghost = {}     # id(mech) -> 幽灵血条值（缓慢追落，打击感）

    def reset(self):
        self.ghost = {}

    def draw(self, surf, p1, p2, wins1, wins2, timer_frames):
        self._bar(surf, p1, left=True)
        self._bar(surf, p2, left=False)
        self._pips(surf, wins1, left=True)
        self._pips(surf, wins2, left=False)
        self._timer(surf, timer_frames)

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
        if left:
            surf.fill(e_col, (x0, ey, e_w, ENERGY_H))
        else:
            surf.fill(e_col, (x0 + BAR_W - e_w, ey, e_w, ENERGY_H))

        # 名字
        name = f"{m.spec['name']}·{m.spec['cn_name']}"
        fnt = get_font(9)
        img = fnt.render(name, True, (230, 230, 240))
        if left:
            surf.blit(img, (x0, y0 - 11))
        else:
            surf.blit(img, (x0 + BAR_W - img.get_width(), y0 - 11))

    def _pips(self, surf, wins, left):
        y = 10 + BAR_H + 3 + ENERGY_H + 6
        for i in range(ROUNDS_TO_WIN):
            size = 5
            if left:
                cx = BAR_MARGIN + 6 + i * (size + 5)
            else:
                cx = INTERNAL_W - BAR_MARGIN - 6 - i * (size + 5)
            col = COLORS["timer"] if i < wins else (60, 58, 76)
            pts = [(cx, y - 3), (cx + 3, y), (cx, y + 3), (cx - 3, y)]
            pygame.draw.polygon(surf, col, pts)

    def _timer(self, surf, timer_frames):
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
    off = 0
    if pulse:
        import pygame.time
        off = 0
    surf.blit(shadow, (cx - img.get_width() // 2 + 3, cy - img.get_height() // 2 + 3))
    surf.blit(img, (cx - img.get_width() // 2, cy - img.get_height() // 2))
    if sub:
        fnt2 = get_font(12)
        img2 = fnt2.render(sub, True, (235, 220, 190))
        surf.blit(img2, (cx - img2.get_width() // 2, cy + 22))


def draw_menu(surf, bg, frames, t):
    surf.blit(bg, (0, 0))
    # 两机甲登场姿势（贴两侧，避免与说明文字重叠）
    idle_p1 = frames["p1"]["idle"][1]
    idle_p2 = frames["p2"]["idle"][-1]
    bob = 2 if (t // 22) % 2 else 0
    surf.blit(idle_p1, (36, 236 - SPRITE_H + bob))
    surf.blit(idle_p2, (480 - 36 - idle_p2.get_width(), 236 - SPRITE_H + bob))

    fnt_big = get_font(34)
    title = fnt_big.render("MECH DUEL", True, (245, 240, 225))
    sh = fnt_big.render("MECH DUEL", True, (25, 14, 34))
    cx = INTERNAL_W // 2
    surf.blit(sh, (cx - title.get_width() // 2 + 3, 38 + 3))
    surf.blit(title, (cx - title.get_width() // 2, 38))
    fnt_cn = get_font(15)
    sub = fnt_cn.render("钢 铁 对 决", True, (250, 200, 120))
    surf.blit(sub, (cx - sub.get_width() // 2, 74))

    blink = (t // 30) % 2 == 0
    fnt_opt = get_font(13)
    o1 = fnt_opt.render("[1] 双人对抗   2P  VS", True, (230, 230, 240))
    o2 = fnt_opt.render("[2] 挑战 AI    VS  CPU", True, (230, 230, 240))
    surf.blit(o1, (cx - o1.get_width() // 2, 118))
    surf.blit(o2, (cx - o2.get_width() // 2, 138))
    if blink:
        hint = fnt_opt.render("按 1 或 2 开始", True, (255, 214, 100))
        surf.blit(hint, (cx - hint.get_width() // 2, 166))

    fnt_help = get_font(9)
    h1 = fnt_help.render("P1  GARNET: A/D 移动  W 跳  S 防御  J 斩击  K 光束  L 投技", True, (215, 160, 150))
    h2 = fnt_help.render("P2  AZURE : ←/→ 移动  ↑ 跳  ↓ 防御  1 斩击  2 光束  3 投技", True, (150, 180, 230))
    surf.blit(h1, (cx - h1.get_width() // 2, 198))
    surf.blit(h2, (cx - h2.get_width() // 2, 212))
    h4 = fnt_help.render("双击方向 冲刺/后撤 · 空中可斩击 · 投技无视防御", True, (255, 214, 100))
    surf.blit(h4, (cx - h4.get_width() // 2, 226))
    h3 = fnt_help.render("三局两胜 · 每局 60 秒 · R 重开  ESC 菜单", True, (170, 170, 190))
    surf.blit(h3, (cx - h3.get_width() // 2, 240))


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
