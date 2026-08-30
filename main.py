# -*- coding: utf-8 -*-
"""《钢铁对决 MECH DUEL》入口：主循环、场景（菜单/对战/结算）、回合流程、自测。

运行：
    python main.py            # 正常启动
    python main.py --selftest # 无窗口逻辑自测（回归验证）
"""

import sys

import pygame

from settings import (INTERNAL_W, INTERNAL_H, WINDOW_W, WINDOW_H, FPS, TITLE,
                      P1_KEYS, P2_KEYS, ROUND_TIME, ROUNDS_TO_WIN,
                      KO_SLOW_FRAMES, HITSTOP_FRAMES, MIN_SEPARATION,
                      ARENA_LEFT, ARENA_RIGHT, GROUND_Y, BLOCK_REDUCE,
                      MELEE_WINDUP, THROW_HIT_T, THROW_RANGE,
                      AIR_MELEE_ACTIVE, AIR_MELEE_MULT, RANGED_DAMAGE,
                      RANGED_COST, ENERGY_MAX,
                      SUPER_MAX, SUPER_GAIN_HIT, SUPER_GAIN_TAKE,
                      SUPER_GAIN_BLOCK, SUPER_FLASH_FRAMES,
                      GUARD_MAX, AZURE_SUPER_BOLT_DMG, JUMP_SEP_Y)
from assets import build_mech_frames, build_background, get_font
from mech import Mech
from effects import Fx
from ai import AIController
from sfx import Sfx
from ui import HUD, banner, draw_menu, draw_victory

MENU, FIGHT, VICTORY = "menu", "fight", "victory"
INTRO, ACTIVE, SLOW, ROUND_END = "intro", "active", "slow", "round_end"

INTRO_FRAMES = 150
ROUND_END_FRAMES = 100


class FakeKeys:
    """自测用：模拟 pygame.key.get_pressed() 的按位取值接口。"""

    def __init__(self, pressed):
        self.pressed = pressed

    def __getitem__(self, keycode):
        return self.pressed.get(keycode, False)


class Fight:
    """一场三局两胜对战：回合状态机 + 判定 + 特效编排。"""

    def __init__(self, mode, frames, bg, sfx):
        self.mode = mode                      # "2p" | "ai"
        self.frames = frames
        self.bg = bg
        self.sfx = sfx
        self.fx = Fx()
        self.hud = HUD()
        self.p1 = Mech("garnet", 140, 1, frames)
        self.p2 = Mech("azure", 340, -1, frames)
        self.ai1 = None
        self.ai2 = AIController(self.p2, self.p1) if mode in ("ai", "demo") else None
        if mode == "demo":
            self.ai1 = AIController(self.p1, self.p2)
        self.wins = [0, 0]
        self.round_no = 1
        self.timer = ROUND_TIME * 60
        self.phase = INTRO
        self.phase_t = 0
        self.t = 0
        self.hitstop = 0
        self.match_winner = None      # Mech 或 None
        self.banner_text = None
        self.banner_sub = None
        self.world = pygame.Surface((INTERNAL_W, INTERNAL_H))

    # -------------------------------------------------- 回合管理
    def reset_round(self):
        self.p1.reset_round(140, 1)
        self.p2.reset_round(340, -1)
        self.fx.clear()
        self.timer = ROUND_TIME * 60
        self.phase = INTRO
        self.phase_t = 0
        self.banner_text = None
        self.banner_sub = None

    def restart_match(self):
        self.wins = [0, 0]
        self.round_no = 1
        self.match_winner = None
        self.hud.reset()
        self.reset_round()

    # -------------------------------------------------- 输入
    def _read_inputs(self, keys):
        for m, ai, keymap in ((self.p1, self.ai1, P1_KEYS),
                              (self.p2, self.ai2, None if self.ai2 else P2_KEYS)):
            if ai is not None:
                ai.update()
                continue
            if keys is None:
                for k in m.input:
                    m.input[k] = False
                continue
            for act, code in keymap.items():
                m.input[act] = bool(keys[code])
        if self.ai1:
            self.ai1.observe_bolts(self.fx.bolts)
        if self.ai2:
            self.ai2.observe_bolts(self.fx.bolts)

    def _clear_inputs(self):
        for m in (self.p1, self.p2):
            for k in m.input:
                m.input[k] = False

    # -------------------------------------------------- 每帧推进
    def step(self, keys):
        self.t += 1
        if self.hitstop > 0:                 # 命中顿帧：世界冻结但粒子继续
            self.hitstop -= 1
            self.fx.update(frozen=True)
            return

        self.phase_t += 1

        if self.phase == INTRO:
            self._clear_inputs()
            self.p1.update(self.p2, self.fx, self.sfx)
            self.p2.update(self.p1, self.fx, self.sfx)
            self.fx.update()
            if self.phase_t >= INTRO_FRAMES:
                self.phase = ACTIVE
                self.phase_t = 0
                self.sfx.play("fight")
            return

        if self.phase == ACTIVE:
            self._read_inputs(keys)
            self.p1.update(self.p2, self.fx, self.sfx)
            self.p2.update(self.p1, self.fx, self.sfx)
            self._super_cinematic()          # 超必杀发动定格演出
            self._spawn_slashes()
            self._separate()
            self._combat()
            self.timer -= 1
            self.fx.update()
            if self.p1.hp <= 0 or self.p2.hp <= 0:
                self._on_ko()
            elif self.timer <= 0:
                self._on_timeup()
            return

        if self.phase == SLOW:                # KO 慢镜头
            if self.phase_t % 3 == 0:
                self._clear_inputs()
                self.p1.update(self.p2, self.fx, self.sfx)
                self.p2.update(self.p1, self.fx, self.sfx)
            self.fx.update()
            if self.phase_t >= KO_SLOW_FRAMES:
                self.phase = ROUND_END
                self.phase_t = 0
            return

        if self.phase == ROUND_END:
            self.fx.update()
            if self.phase_t >= ROUND_END_FRAMES and not self.match_winner:
                self.round_no += 1
                self.reset_round()

    # -------------------------------------------------- 判定
    def _super_cinematic(self):
        """超必杀发动瞬间：全局定格 + 白闪 + 震屏 + 专属音效。"""
        for m in (self.p1, self.p2):
            if m.super_pending:
                m.super_pending = False
                self.hitstop = SUPER_FLASH_FRAMES
                self.fx.flash(150)
                self.fx.shake(6)
                self.sfx.play("super")

    def _spawn_slashes(self):
        from settings import MELEE_WINDUP
        for m in (self.p1, self.p2):
            if m.state == "melee" and m.t == MELEE_WINDUP:
                self.fx.slash(m)
            elif m.state == "air_melee" and m.t == AIR_MELEE_ACTIVE[0]:
                self.fx.slash(m)

    def _separate(self):
        a, b = self.p1, self.p2
        if a.state == "ko" or b.state == "ko":
            return
        if abs(a.y - b.y) > JUMP_SEP_Y:   # 高度差够大（跳到头顶以上）不再互推
            return
        dx = b.x - a.x
        if abs(dx) < MIN_SEPARATION:
            push = (MIN_SEPARATION - abs(dx)) / 2
            s = 1 if dx >= 0 else -1
            a.x = max(ARENA_LEFT, a.x - s * push)
            b.x = max(ARENA_LEFT, min(ARENA_RIGHT, b.x + s * push))

    def _combat(self):
        # 超必杀槽位结算（命中双方都积攒）
        def meter(atk, dfn, res):
            if res in ("hit", "break"):
                atk.super = min(SUPER_MAX, atk.super + SUPER_GAIN_HIT)
                dfn.super = min(SUPER_MAX, dfn.super + SUPER_GAIN_TAKE)
            elif res == "blocked":
                dfn.super = min(SUPER_MAX, dfn.super + SUPER_GAIN_BLOCK)

        # 超必杀判定：GARNET「熔核冲击」冲撞（AZURE 射击型走光束判定）
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            hb = atk.super_hitbox()
            if hb is None or atk.super_did_hit:
                continue
            if hb.colliderect(dfn.body_rect()):
                atk.super_did_hit = True
                res = dfn.take_damage(atk.spec["super_damage"], atk.facing,
                                      self.fx, self.sfx,
                                      heavy=True, unblockable=True, launch=True)
                self.fx.shake(8)
                if res == "ko":
                    self._on_ko()
                meter(atk, dfn, "hit")
        # 投技判定：THROW_HIT_T 帧抓取范围内地面目标，无视格挡（破防手段）
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            if (atk.state == "throw" and atk.t == THROW_HIT_T
                    and not atk.throw_hit_done):
                atk.throw_hit_done = True
                if (dfn.grounded and dfn.state not in ("thrown", "hurt", "ko")
                        and not dfn.invuln
                        and abs(dfn.x - atk.x) <= THROW_RANGE):
                    res = dfn.take_damage(atk.spec["throw_damage"], atk.facing,
                                          self.fx, self.sfx,
                                          heavy=True, unblockable=True, launch=True)
                    if res == "hit":
                        self.hitstop = HITSTOP_FRAMES + 3
                    elif res == "ko":
                        self._on_ko()
                    meter(atk, dfn, "hit")
        # 近战判定
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            hb = atk.melee_hitbox()
            if hb is None or atk.melee_did_hit:
                continue
            if hb.colliderect(dfn.body_rect()):
                dmg = atk.spec["melee_damage"]
                if atk.state == "air_melee":
                    dmg = max(1, round(dmg * AIR_MELEE_MULT))
                res = dfn.take_damage(dmg, atk.facing,
                                      self.fx, self.sfx, heavy=True)
                if res is None:            # 对方无敌帧：判定不消耗，攻击穿透
                    continue
                atk.melee_did_hit = True
                meter(atk, dfn, res)
                if res == "hit" or res == "break":
                    self.hitstop = HITSTOP_FRAMES
                elif res == "ko":
                    self._on_ko()
        # 光束判定
        for bolt in list(self.fx.bolts):
            target = self.p2 if bolt.owner is self.p1 else self.p1
            if bolt.dead or target.state == "ko":
                continue
            if bolt.rect().colliderect(target.body_rect()):
                direction = 1 if bolt.vx > 0 else -1
                res = target.take_damage(bolt.dmg, direction,
                                         self.fx, self.sfx, heavy=False)
                if res is None:            # 无敌帧：光束穿透不消失
                    continue
                bolt.dead = True
                meter(bolt.owner, target, res)
                if res == "ko":
                    self._on_ko()

    def _on_ko(self):
        if self.phase != ACTIVE:
            return
        if self.p1.hp <= 0 and self.p2.hp <= 0:      # 双 KO 平局
            self.banner_text = "DRAW"
            self.banner_sub = "双双倒地"
        else:
            winner = self.p1 if self.p1.hp > 0 else self.p2
            idx = 0 if winner is self.p1 else 1
            self.wins[idx] += 1
            self.banner_text = "K.O."
            self.banner_sub = f"{winner.spec['name']} 获得本局"
            if self.wins[idx] >= ROUNDS_TO_WIN:
                self.match_winner = winner
        self.sfx.play("ko")
        self.phase = SLOW
        self.phase_t = 0

    def _on_timeup(self):
        self.timer = 0
        if self.p1.hp == self.p2.hp:
            self.banner_text = "DRAW"
            self.banner_sub = "平局"
        else:
            winner = self.p1 if self.p1.hp > self.p2.hp else self.p2
            idx = 0 if winner is self.p1 else 1
            self.wins[idx] += 1
            self.banner_text = "TIME UP"
            self.banner_sub = f"{winner.spec['name']} 剩余血量更多"
            if self.wins[idx] >= ROUNDS_TO_WIN:
                self.match_winner = winner
        self.phase = ROUND_END
        self.phase_t = 0

    # -------------------------------------------------- 渲染
    def render(self, frame):
        w = self.world
        w.blit(self.bg, (0, 0))
        # 倒地方优先画在底层
        order = (self.p2, self.p1)
        for m in sorted(order, key=lambda m: m.state == "ko", reverse=True):
            m.draw(w, self.t)
        self.fx.draw(w, get_font(10))

        ox, oy = self.fx.shake_offset()
        frame.fill((8, 8, 12))
        frame.blit(w, (ox, oy))

        self.hud.draw(frame, self.p1, self.p2, self.wins[0], self.wins[1],
                      self.timer)

        # 横幅
        if self.phase == INTRO:
            if self.phase_t < INTRO_FRAMES - 45:
                banner(frame, f"ROUND {self.round_no}",
                       sub=f"{self.p1.spec['name']} vs {self.p2.spec['name']}")
            else:
                banner(frame, "FIGHT!", pulse=True)
        elif self.banner_text:
            banner(frame, self.banner_text, sub=self.banner_sub)


# ================================================================ 主程序

def build_scanlines():
    surf = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    for y in range(0, WINDOW_H, 3):
        surf.fill((0, 0, 0, 26), (0, y, WINDOW_W, 1))
    return surf


def run_window():
    pygame.mixer.pre_init(22050, -16, 1, 256)
    pygame.init()
    pygame.mixer.init(22050, -16, 1, 256)
    pygame.key.stop_text_input()   # 纯按键游戏：禁用 IME 文本合成，防止中文输入法吞键
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()

    frames = build_mech_frames()
    bg = build_background()
    sfx = Sfx()
    scanlines = build_scanlines()

    demo = "--demo" in sys.argv            # 演示模式：AI 对 AI，直接开打
    scene = FIGHT if demo else MENU
    fight = None                           # 菜单场景下尚无对战实例
    if demo:
        fight = Fight("demo", frames, bg, sfx)
    menu_t = 0
    victory_t = 0
    running = True

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    if scene != MENU:
                        scene = MENU
                        fight = None
                    else:
                        running = False
                elif scene == MENU and ev.key == pygame.K_1:
                    fight = Fight("2p", frames, bg, sfx)
                    scene = FIGHT
                    sfx.play("menu")
                elif scene == MENU and ev.key == pygame.K_2:
                    fight = Fight("ai", frames, bg, sfx)
                    scene = FIGHT
                    sfx.play("menu")
                elif scene in (FIGHT, VICTORY) and ev.key == pygame.K_r:
                    if fight:
                        fight.restart_match()
                        scene = FIGHT
                    sfx.play("menu")

        frame = pygame.Surface((INTERNAL_W, INTERNAL_H))
        if scene == MENU:
            menu_t += 1
            draw_menu(frame, bg, frames, menu_t)
        elif scene == FIGHT:
            fight.step(pygame.key.get_pressed())
            fight.render(frame)
            if fight.match_winner:
                scene = VICTORY
                victory_t = 0
                sfx.play("win")
        else:  # VICTORY
            victory_t += 1
            draw_victory(frame, bg, fight.match_winner.spec,
                         fight.wins[0], fight.wins[1])
            if demo and victory_t > FPS * 6:   # 演示模式自动再来一局
                fight.restart_match()
                scene = FIGHT

        scaled = pygame.transform.scale(frame, (WINDOW_W, WINDOW_H))
        screen.blit(scaled, (0, 0))
        screen.blit(scanlines, (0, 0))
        flash_a = fight.fx.flash_a if fight else 0
        if flash_a > 0:                       # 超必杀发动全屏白闪
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill((255, 250, 235, int(min(255, flash_a))))
            screen.blit(overlay, (0, 0))
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()


# ================================================================ 自测

def selftest():
    import os
    import random
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame.init()
    pygame.display.set_mode((1, 1))

    frames = build_mech_frames()
    bg = build_background()
    sfx = Sfx()

    # 1) AI vs AI 完整对局模拟：跑满 3 局时长
    f = Fight("ai", frames, bg, sfx)
    f.ai1 = AIController(f.p1, f.p2)
    bolts_seen = False
    for i in range(ROUND_TIME * 60 * 3 + 2000):
        f.step(None)
        if f.fx.bolts:
            bolts_seen = True
        if f.match_winner:
            break
        assert f.p1.x == max(ARENA_LEFT, min(ARENA_RIGHT, f.p1.x))
    assert f.match_winner is not None, "AI 对局未在限时内决出胜负"
    assert f.match_winner in (f.p1, f.p2)
    assert any(w >= ROUNDS_TO_WIN for w in f.wins)
    print(f"[1] AI 对局完成: {f.wins}, 胜者 {f.match_winner.spec['name']}, "
          f"光束出现={bolts_seen}")

    # 2) 强制 KO 流程
    f2 = Fight("ai", frames, bg, sfx)
    f2.phase = ACTIVE
    f2.phase_t = INTRO_FRAMES
    res = f2.p2.take_damage(9999, 1, f2.fx, sfx, heavy=True)
    assert res == "ko" and f2.p2.state == "ko"
    f2.step(None)
    assert f2.phase == SLOW and f2.wins[0] == 1
    for _ in range(KO_SLOW_FRAMES + ROUND_END_FRAMES + 10):
        f2.step(None)
    assert f2.round_no == 2 and f2.p2.hp == f2.p2.max_hp
    print("[2] KO → 慢镜头 → 下一局重置: OK")

    # 3) 2P 键盘输入驱动移动/攻击
    f3 = Fight("2p", frames, bg, sfx)
    f3.phase = ACTIVE
    x0 = f3.p1.x
    keys = FakeKeys({pygame.K_d: True})
    for _ in range(30):
        f3.step(keys)
    assert f3.p1.x > x0, "P1 未向右移动"
    keys = FakeKeys({pygame.K_j: True})
    f3.p1.melee_cd = 0
    for _ in range(10):
        f3.step(keys)
    assert f3.p1.state == "melee", "P1 未进入斩击状态"
    # 远程：能量足够时应生成光束
    keys = FakeKeys({pygame.K_k: True})
    f3.p1.ranged_cd = 0
    f3.p1.energy = 100
    f3.p1.state = "idle"
    saw_bolt = False
    for _ in range(40):
        f3.step(keys)
        if f3.fx.bolts:
            saw_bolt = True
            break
    assert saw_bolt, "P1 未发射光束"
    print("[3] 2P 输入: 移动/近战/远程 OK")

    # 4) 格挡减伤
    f4 = Fight("2p", frames, bg, sfx)
    f4.p2.state = "block"
    hp0 = f4.p2.hp
    f4.p2.take_damage(10, 1, f4.fx, sfx)
    assert f4.p2.hp == hp0 - max(1, round(10 * 0.2)), "格挡减伤数值不符"
    print("[4] 格挡减伤: OK")

    # 5) 计时到点判定
    f5 = Fight("2p", frames, bg, sfx)
    f5.phase = ACTIVE
    f5.timer = 1
    f5.p1.hp = 30
    f5.p2.hp = 80
    f5.step(None)
    assert f5.phase == "round_end" and f5.wins[1] == 1
    print("[5] 超时判负: OK")

    # 6) 投技：无视格挡 + 浮空落地硬直
    f6 = Fight("2p", frames, bg, sfx)
    f6.phase = ACTIVE
    f6.p1.x, f6.p2.x = 200, 232
    f6.p2.state = "block"
    hp0 = f6.p2.hp
    keys = FakeKeys({pygame.K_l: True, pygame.K_DOWN: True})  # P1投技 / P2格挡
    for _ in range(THROW_HIT_T + 2):
        f6.step(keys)
    assert f6.p2.hp == hp0 - f6.p1.spec["throw_damage"], "投技未无视格挡"
    assert f6.p2.state == "thrown", f"被投后状态异常: {f6.p2.state}"
    for _ in range(150):                      # 浮空 → 落地硬直 → 恢复
        f6.step(keys)
        if f6.p2.state == "idle":
            break
    assert f6.p2.state == "idle", "被投后未恢复正常"
    print("[6] 投技破防 + 浮空落地硬直: OK")

    # 7) 格挡削血（chip）：格挡仍掉血，但远低于裸吃
    f7 = Fight("2p", frames, bg, sfx)
    f7.p2.state = "block"
    hp0 = f7.p2.hp
    res = f7.p2.take_damage(RANGED_DAMAGE, 1, f7.fx, sfx)
    chip = max(1, round(RANGED_DAMAGE * BLOCK_REDUCE))
    assert res == "blocked" and f7.p2.hp == hp0 - chip, "格挡削血数值不符"
    print("[7] 格挡削血 chip: OK")

    # 8) 空中下劈：空中按近战进入 air_melee 并命中地面目标
    f8 = Fight("2p", frames, bg, sfx)
    f8.phase = ACTIVE
    f8.p1.x, f8.p2.x = 200, 220
    f8.p1.y = GROUND_Y - 40
    f8.p1.vy = 0
    f8.p1.state = "jump"
    keys = FakeKeys({pygame.K_j: True})
    f8.step(keys)
    assert f8.p1.state == "air_melee", f"未进入空中攻击: {f8.p1.state}"
    for _ in range(10):
        f8.step(keys)
        if f8.p2.hp < f8.p2.max_hp:
            break
    dmg = max(1, round(f8.p1.spec["melee_damage"] * AIR_MELEE_MULT))
    assert f8.p2.hp == f8.p2.max_hp - dmg, "空中下劈未造成预期伤害"
    print("[8] 空中下劈: OK")

    # 9) 后撤步无敌帧 + 双击方向触发冲刺/后撤
    f9 = Fight("2p", frames, bg, sfx)
    f9.p1.state = "backstep"
    f9.p1.t = 6
    hp0 = f9.p1.hp
    assert f9.p1.invuln, "后撤步无敌窗口判定失败"
    assert f9.p1.take_damage(10, 1, f9.fx, sfx) is None, "无敌帧未免疫伤害"
    assert f9.p1.hp == hp0
    f9b = Fight("2p", frames, bg, sfx)
    f9b.phase = ACTIVE
    f9b.p1.x, f9b.p2.x = 200, 260
    for ks in ({pygame.K_a: True}, {pygame.K_a: True}, {}, {}, {pygame.K_a: True}):
        f9b.step(FakeKeys(ks))
    assert f9b.p1.state == "backstep", f"双击后方未触发后撤步: {f9b.p1.state}"
    f9c = Fight("2p", frames, bg, sfx)
    f9c.phase = ACTIVE
    f9c.p1.x, f9c.p2.x = 200, 260
    for ks in ({pygame.K_d: True}, {pygame.K_d: True}, {}, {}, {pygame.K_d: True}):
        f9c.step(FakeKeys(ks))
    assert f9c.p1.state == "dash", f"双击前方未触发前冲: {f9c.p1.state}"
    assert f9c.p1.x > 200, "前冲未产生位移"
    print("[9] 后撤步无敌 + 双击冲刺/后撤: OK")

    # 10) 命中取消：斩击命中后摇可取消接光束（连段核心）
    f10 = Fight("2p", frames, bg, sfx)
    f10.phase = ACTIVE
    f10.p1.x, f10.p2.x = 200, 232
    f10.p1.state = "melee"
    f10.p1.t = MELEE_WINDUP + 1
    f10.p1.melee_did_hit = False
    f10.step(FakeKeys({pygame.K_j: True}))
    assert f10.p2.hp < f10.p2.max_hp, "斩击未命中"
    assert f10.p1.melee_did_hit
    for _ in range(12):                    # 命中顿帧结束后按 K 取消
        f10.step(FakeKeys({pygame.K_k: True}))
        if f10.p1.state == "shoot":
            break
    assert f10.p1.state == "shoot", f"命中取消失败: {f10.p1.state}"
    print("[10] 命中取消连段: OK")

    # 11) 受身：浮空受击落地后按住防 → 快速起身 + 起身无敌
    f11 = Fight("2p", frames, bg, sfx)
    f11.phase = ACTIVE
    f11.p1.state = "hurt"
    f11.p1.t = 3
    f11.p1._air_hurt = True
    f11.p1.y = GROUND_Y - 1
    f11.p1.vy = 0.2
    f11.p1._stun_extra = 0
    keys = FakeKeys({pygame.K_s: True})
    for _ in range(8):
        f11.step(keys)
        if f11.p1.state == "idle":
            break
    assert f11.p1.state == "idle", f"受身未生效: {f11.p1.state}"
    assert f11.p1.wake_invuln > 0 and f11.p1.invuln, "受身起身无敌缺失"
    print("[11] 受身起身 + 无敌: OK")

    # 12) GARNET 超必杀「熔核冲击」：冲撞命中击飞
    f12 = Fight("2p", frames, bg, sfx)
    f12.phase = ACTIVE
    f12.p1.x, f12.p2.x = 200, 280
    f12.p1.super = SUPER_MAX
    f12.step(FakeKeys({pygame.K_i: True}))
    assert f12.p1.state == "super", f"未进入超必杀: {f12.p1.state}"
    assert f12.hitstop == SUPER_FLASH_FRAMES, "发动定格演出缺失"
    assert f12.p1.invuln and f12.p1.super == 0
    for _ in range(150):
        f12.step(FakeKeys({}))
        if f12.p2.hp < f12.p2.max_hp:
            break
    assert f12.p2.hp <= f12.p2.max_hp - f12.p1.spec["super_damage"], "冲撞未命中"
    assert f12.p2.state in ("thrown", "hurt")
    print("[12] GARNET 超必杀冲撞: OK")

    # 13) AZURE 超必杀「苍蓝齐射」：三连强化光束
    f13 = Fight("2p", frames, bg, sfx)
    f13.phase = ACTIVE
    f13.p1.x, f13.p2.x = 160, 320
    f13.p2.super = SUPER_MAX
    f13.step(FakeKeys({pygame.K_4: True}))
    assert f13.p2.state == "super", f"未进入超必杀: {f13.p2.state}"
    for _ in range(90):
        f13.step(FakeKeys({}))
        if f13.fx.bolts:
            break
    assert f13.fx.bolts, "苍蓝齐射未发射"
    assert f13.fx.bolts[0].dmg == AZURE_SUPER_BOLT_DMG and f13.fx.bolts[0].big
    for _ in range(90):
        f13.step(FakeKeys({}))
        if f13.p1.hp < f13.p1.max_hp:
            break
    assert f13.p1.hp <= f13.p1.max_hp - AZURE_SUPER_BOLT_DMG, "强化光束未命中"
    print("[13] AZURE 超必杀齐射: OK")

    # 14) 破防槽：连续格挡耗尽防御槽 → GUARD BREAK
    f14 = Fight("2p", frames, bg, sfx)
    f14.p2.state = "block"
    f14.p2.guard = GUARD_MAX
    for _ in range(9):
        assert f14.p2.take_damage(RANGED_DAMAGE, 1, f14.fx, sfx) == "blocked"
    assert f14.p2.guard > 0, "防御槽过早耗尽"
    res = f14.p2.take_damage(RANGED_DAMAGE, 1, f14.fx, sfx)
    assert res == "break", f"未破防: {res}"
    assert f14.p2.state == "guard_break" and f14.p2.guard == 0
    print("[14] GUARD BREAK 破防: OK")

    # 15) 跳跃可越过对手：贴脸起跳横移，落地位置应越过对手头顶到另一侧
    f15 = Fight("2p", frames, bg, sfx)
    f15.phase = ACTIVE
    f15.p1.x, f15.p2.x = 200, 226           # 贴脸（间隔 26 = 最小推挤距离）
    x0 = f15.p1.x
    # 若跳起后成功越过，p1 会落到对手另一侧，即与初始位置分居对手两侧
    keys = FakeKeys({pygame.K_w: True, pygame.K_d: True})   # 跳 + 右
    landed = False
    for _ in range(240):
        f15.step(keys)
        if f15.p1.grounded:
            landed = True
            break
    assert landed, "跳跃未落地"
    assert (f15.p1.x - f15.p2.x) * (x0 - f15.p2.x) < 0, \
        f"跳跃未能越过对手（p1 起点 {x0:.0f} 落地 {f15.p1.x:.0f} 对手 {f15.p2.x:.0f}）"
    print("[15] 跳跃越过对手: OK")

    # 16) 空中射击：跳跃中按 K 可发射、保留水平动量、斜下弹道命中地面目标
    f16 = Fight("2p", frames, bg, sfx)
    f16.phase = ACTIVE
    f16.p1.x, f16.p2.x = 200, 300           # 中距离（贴脸时弹来不及下坠属正常）
    f16.p1.y = GROUND_Y - 40
    f16.p1.vy = 0
    f16.p1.vx = 2.0
    f16.p1.state = "jump"
    keys = FakeKeys({pygame.K_k: True})
    f16.step(keys)
    assert f16.p1.state == "shoot", f"空中射击未触发: {f16.p1.state}"
    for _ in range(3):
        f16.step(keys)
    assert f16.p1.vx > 1.5, f"空中射击丢失水平动量: vx={f16.p1.vx:.2f}"
    spent = False
    for _ in range(60):
        f16.step(keys)
        if f16.p1.energy < ENERGY_MAX:
            spent = True
        if f16.p2.hp < f16.p2.max_hp:
            break
    assert spent, "空中射击未消耗能量发射"
    assert f16.p2.hp < f16.p2.max_hp, "空中射击未命中地面目标"
    # 弹道应为斜向下（高度越高下坠越快）
    fx16 = Fx()
    m16 = Mech("garnet", 200, 1, frames)
    m16.y = GROUND_Y - 60
    fx16.spawn_bolt(m16, 221, m16.y - 38)
    b = fx16.bolts[0]
    y0 = b.y
    for _ in range(12):
        b.update(fx16)
    assert b.y > y0, f"空中射击弹道未斜向下（y 增量 {b.y - y0:.1f}）"
    assert b.vy > 0
    print("[16] 空中射击（斜向下弹道）: OK")

    print("SELFTEST PASS")
    pygame.quit()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run_window()
