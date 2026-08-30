# -*- coding: utf-8 -*-
"""《钢铁对决 MECH DUEL》入口：主循环、场景（菜单/选人/对战/按键设置/结算）、
回合流程、KO 高光回放、训练模式与自测。

运行：
    python main.py            # 正常启动
    python main.py --demo     # AI 演示模式
    python main.py --selftest # 无窗口逻辑自测（回归验证；含 AI vs AI 平衡回归，
                              #  可用环境变量 MECHDUEL_BALANCE_N 调整局数，默认 100）
"""

import collections
import os
import random
import sys

import pygame

from settings import (INTERNAL_W, INTERNAL_H, WINDOW_W, WINDOW_H, FPS, TITLE,
                      P1_KEYS, P2_KEYS, DEFAULT_P1_KEYS, DEFAULT_P2_KEYS,
                      load_keymap, save_keymap, MECH_ORDER, ROUND_TIME,
                      ROUNDS_TO_WIN, KO_SLOW_FRAMES, HITSTOP_FRAMES,
                      MIN_SEPARATION, ARENA_LEFT, ARENA_RIGHT, GROUND_Y,
                      BLOCK_REDUCE, MELEE_WINDUP, THROW_HIT_T, THROW_RANGE,
                      AIR_MELEE_ACTIVE, AIR_MELEE_MULT, RANGED_DAMAGE,
                      RANGED_COST, ENERGY_MAX, REPLAY_FRAMES, REPLAY_HOLD,
                      SUPER_MAX, SUPER_GAIN_HIT, SUPER_GAIN_TAKE,
                      SUPER_GAIN_BLOCK, SUPER_FLASH_FRAMES, AZURE_SUPER_BOLT_DMG,
                      VERDANT_SUPER_BOLT_DMG, GARNET_SUPER_DMG,
                      GUARD_MAX, JUMP_SEP_Y)
from assets import (build_mech_frames, build_background, get_font,
                    SPRITE_W, SPRITE_H, ANCHOR_FX, PIX)
from mech import Mech
from effects import Fx
from ai import AIController
from sfx import Sfx
from ui import (HUD, banner, draw_menu, draw_victory, draw_select,
                draw_keyconfig)

MENU, SELECT, FIGHT, VICTORY, KEYCONFIG = (
    "menu", "select", "fight", "victory", "keyconfig")
INTRO, ACTIVE, SLOW, REPLAY, ROUND_END = (
    "intro", "active", "slow", "replay", "round_end")
AI_LEVELS = ("easy", "normal", "hard")     # 菜单 TAB 轮换顺序

INTRO_FRAMES = 150
ROUND_END_FRAMES = 100


class FakeKeys:
    """自测用：模拟 pygame.key.get_pressed() 的按位取值接口。"""

    def __init__(self, pressed):
        self.pressed = pressed

    def __getitem__(self, keycode):
        return self.pressed.get(keycode, False)


class InputMux:
    """键盘 + 手柄合并输入源（接口兼容 key.get_pressed() 的取下标用法）。"""

    def __init__(self, keys, pads):
        self.keys = keys
        self.pads = pads          # 每个手柄一个 {键码: bool}

    def __getitem__(self, keycode):
        if self.keys[keycode]:
            return True
        for pad in self.pads:
            if pad.get(keycode):
                return True
        return False


class PadMap:
    """手柄映射：第一个手柄 → P1，第二个 → P2。无需配置。
    十字键/左摇杆 移动+跳+防，按钮 0/1/2/3 = 斩/束/投/超，4=防御 5=跳。"""

    BTN = {"melee": 0, "ranged": 1, "throw": 2, "super": 3, "block": 4,
           "jump": 5}

    def __init__(self):
        self.joys = []
        try:
            pygame.joystick.init()
            for i in range(pygame.joystick.get_count()):
                self.joys.append(pygame.joystick.Joystick(i))
        except Exception:
            self.joys = []

    def poll(self, keymaps):
        """按玩家键位表把手柄状态翻译成 {键码: bool} 列表。"""
        outs = [{} for _ in keymaps]
        for pi, joy in enumerate(self.joys[:len(keymaps)]):
            km = keymaps[pi]
            out = outs[pi]
            try:
                ax = joy.get_axis(0) if joy.get_numaxes() > 0 else 0.0
                ay = joy.get_axis(1) if joy.get_numaxes() > 1 else 0.0
                hat = joy.get_hat(0) if joy.get_numhats() > 0 else (0, 0)

                def press(act):
                    code = km.get(act)
                    if code is not None:
                        out[code] = True

                if ax < -0.5 or hat[0] < 0:
                    press("left")
                if ax > 0.5 or hat[0] > 0:
                    press("right")
                if ay < -0.5 or hat[1] < 0:
                    press("jump")
                if ay > 0.5 or hat[1] > 0:
                    press("block")
                for act, idx in self.BTN.items():
                    if joy.get_numbuttons() > idx and joy.get_button(idx):
                        press(act)
            except Exception:
                pass
        return outs


class QuietFx(Fx):
    """无头平衡回归用：跳过纯视觉粒子，保留光束与判定相关状态。"""

    def dust(self, *a, **k):
        pass

    def sparks(self, *a, **k):
        pass

    def block_spark(self, *a, **k):
        pass

    def muzzle_flash(self, *a, **k):
        pass

    def damage_number(self, *a, **k):
        pass

    def slash(self, *a, **k):
        pass

    def ko_burst(self, *a, **k):
        pass

    def throw_impact(self, *a, **k):
        pass

    def flash(self, *a, **k):
        pass


def _seeded_rng(seed):
    return random.Random(seed) if seed is not None else random.Random()


class Fight:
    """一场三局两胜对战：回合状态机 + 判定 + 特效编排。"""

    def __init__(self, mode, frames, bg, sfx, m1="garnet", m2="azure",
                 difficulty="normal", seed=None, quiet=False):
        self.mode = mode          # "2p" | "ai" | "cpu" | "demo" | "training"
        self.training = mode == "training"
        self.difficulty = difficulty
        self.frames = frames
        self.bg = bg
        self.sfx = sfx
        self.fx = QuietFx() if quiet else Fx()
        self.hud = HUD()
        self.p1 = Mech(m1, 140, 1, frames)
        self.p2 = Mech(m2, 340, -1, frames)
        self.ai1 = None
        self.ai2 = None
        if mode in ("ai", "demo"):
            self.ai2 = AIController(self.p2, self.p1, difficulty,
                                    _seeded_rng(seed))
        if mode in ("cpu", "demo"):
            self.ai1 = AIController(
                self.p1, self.p2, difficulty,
                _seeded_rng(None if seed is None else seed + 1))
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
        # KO 高光回放：ACTIVE 期间滚动快照
        self.replay = collections.deque(maxlen=REPLAY_FRAMES)
        self.replay_i = 0
        # 训练模式开关
        self.show_hitboxes = False
        self.dummy_block = False

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
        self.replay.clear()
        self.replay_i = 0

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
            if self.training and self.dummy_block:
                self.p2.input["block"] = True   # 训练假人：自动格挡
            self.p1.update(self.p2, self.fx, self.sfx)
            self.p2.update(self.p1, self.fx, self.sfx)
            self._super_cinematic()          # 超必杀发动定格演出
            self._spawn_slashes()
            self._separate()
            self._combat()
            if not self.training:
                self.timer -= 1
                self._capture_replay()       # KO 高光回放快照
            self.fx.update()
            if self.p1.hp <= 0 or self.p2.hp <= 0:
                self._on_ko()
            elif self.timer <= 0:
                self._on_timeup()
            return

        if self.phase == REPLAY:              # KO 高光回放（慢放）
            self.replay_i += 1
            if not self.replay or self.replay_i >= len(self.replay) * REPLAY_HOLD:
                self.phase = SLOW
                self.phase_t = 0
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
                if not self.training:
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
                res = dfn.take_damage(GARNET_SUPER_DMG, atk.facing,
                                      self.fx, self.sfx,
                                      heavy=True, unblockable=True, launch=True)
                self.fx.shake(8)
                if res == "ko":
                    self._on_ko()
                meter(atk, dfn, "hit")
        # 投技判定：THROW_HIT_T 帧抓取范围内地面目标，无视格挡（破防手段）
        # 先收集双方判定再统一结算：同帧对拼不因结算顺序偏袒先手方
        throws = []
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            if (atk.state == "throw" and atk.t == THROW_HIT_T
                    and not atk.throw_hit_done):
                atk.throw_hit_done = True
                if (dfn.grounded and dfn.state not in ("thrown", "hurt", "ko")
                        and not dfn.invuln
                        and abs(dfn.x - atk.x) <= THROW_RANGE):
                    throws.append((atk, dfn))
        for atk, dfn in throws:
            res = dfn.take_damage(atk.spec["throw_damage"], atk.facing,
                                  self.fx, self.sfx,
                                  heavy=True, unblockable=True, launch=True)
            if res == "hit":
                self.hitstop = HITSTOP_FRAMES + 3
            elif res == "ko":
                self._on_ko()
            meter(atk, dfn, "hit")
        # 近战判定（同帧对拼双方互换，先收集后结算）
        melees = []
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            hb = atk.melee_hitbox()
            if hb is None or atk.melee_did_hit:
                continue
            if hb.colliderect(dfn.body_rect()):
                dmg = atk.spec["melee_damage"]
                if atk.state == "air_melee":
                    dmg = max(1, round(dmg * AIR_MELEE_MULT))
                melees.append((atk, dfn, dmg))
        for atk, dfn, dmg in melees:
            if atk.melee_did_hit:    # 对拼同帧：允许阵亡方的最后一击落地（双 KO 平局）
                continue
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

    def _capture_replay(self):
        """滚动快照：机体姿态 + 弹幕位置，供 KO 高光回放。"""
        p1, p2 = self.p1, self.p2

        def pose(m):
            return (m.x, m.y, m.facing, m.current_frame_name(),
                    f"flash{m.facing}" if m.flash > 0 else m.facing)

        self.replay.append((pose(p1), pose(p2),
                            tuple((b.x, b.y, b.facing,
                                   b.owner.spec["bolt_color"], b.big)
                                  for b in self.fx.bolts)))

    def _on_ko(self):
        if self.phase != ACTIVE:
            return
        if self.training:            # 训练模式：不记比分，慢镜头后重置假人
            self.banner_text = "K.O."
            self.banner_sub = "假人重启中"
            self.sfx.play("ko")
            self.phase = SLOW
            self.phase_t = 0
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
        self.phase = REPLAY          # 先回放高光，再进慢镜头
        self.replay_i = 0

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
        if self.phase == REPLAY:
            self._render_replay(frame)
            return
        w = self.world
        w.blit(self.bg, (0, 0))
        # 倒地方优先画在底层
        order = (self.p2, self.p1)
        for m in sorted(order, key=lambda m: m.state == "ko", reverse=True):
            m.draw(w, self.t)
        self.fx.draw(w, get_font(10))
        if self.training and self.show_hitboxes:
            self._draw_hitboxes(w)

        ox, oy = self.fx.shake_offset()
        frame.fill((8, 8, 12))
        frame.blit(w, (ox, oy))

        self.hud.draw(frame, self.p1, self.p2, self.wins[0], self.wins[1],
                      self.timer, training=self.training)

        # 横幅
        if self.phase == INTRO:
            if self.training:
                banner(frame, "TRAINING",
                       sub="F1 判定框 · F2 假人格挡 · R 重置 · ESC 菜单")
            elif self.phase_t < INTRO_FRAMES - 45:
                banner(frame, f"ROUND {self.round_no}",
                       sub=f"{self.p1.spec['name']} vs {self.p2.spec['name']}")
            else:
                banner(frame, "FIGHT!", pulse=True)
        elif self.banner_text:
            banner(frame, self.banner_text, sub=self.banner_sub)
        if self.training:
            self._training_overlay(frame)

    def _draw_hitboxes(self, w):
        """训练模式判定框：红=近战 绿=超必杀 蓝=本体 黄=弹幕。"""
        for m in (self.p1, self.p2):
            r = m.melee_hitbox()
            if r:
                pygame.draw.rect(w, (255, 80, 80), r, 1)
            hb = m.super_hitbox()
            if hb:
                pygame.draw.rect(w, (110, 255, 130), hb, 1)
            pygame.draw.rect(w, (90, 160, 255), m.body_rect(), 1)
        for b in self.fx.bolts:
            pygame.draw.rect(w, (255, 230, 90), b.rect(), 1)

    def _training_overlay(self, frame):
        """训练模式帧数据：状态/帧数/资源/开关提示。"""
        p1, p2 = self.p1, self.p2
        fnt = get_font(8)

        def line(m):
            return (f"{m.spec['name']} {m.state:<10} t={m.t:<3} HP {m.hp:<3} "
                    f"EN {int(m.energy):<3} SG {int(m.super):<3} "
                    f"GU {int(m.guard):<3} CD {m.melee_cd}/{m.ranged_cd}")

        rows = [line(p1), line(p2),
                f"F1 判定框:{'开' if self.show_hitboxes else '关'}"
                f"  F2 假人格挡:{'开' if self.dummy_block else '关'}"
                f"  R 重置"]
        y = INTERNAL_H - 31
        for i, s in enumerate(rows):
            img = fnt.render(s, True, (195, 205, 220))
            frame.fill((10, 10, 18), (4, y + i * 10 - 1,
                                      img.get_width() + 4, 9))
            frame.blit(img, (6, y + i * 10))

    def _render_replay(self, frame):
        """KO 高光回放：黑边 + REPLAY 字样 + 慢放快照。"""
        w = self.world
        w.blit(self.bg, (0, 0))
        if self.replay:
            snap = self.replay[min(len(self.replay) - 1,
                                   self.replay_i // REPLAY_HOLD)]
            for (x, y, facing, name, fkey), pal in (
                    (snap[0], self.p1.palette), (snap[1], self.p2.palette)):
                img = self.frames[pal][name][fkey]
                ax = int(ANCHOR_FX * PIX)
                x_off = int(x) - ax if facing == 1 else int(x) - (SPRITE_W - ax)
                w.blit(img, (x_off, int(y) - SPRITE_H))
            for bx, by, bf, col, big in snap[2]:
                img = self.fx.bolt_sprites[col][(self.t // 3) % 2][bf]
                if big:
                    img = pygame.transform.scale(
                        img, (img.get_width() * 2, img.get_height() * 2))
                    w.blit(img, (int(bx) - img.get_width() // 2,
                                 int(by) - img.get_height() // 2))
                else:
                    w.blit(img, (int(bx) - 10, int(by) - 5))
        frame.fill((6, 6, 10))
        frame.blit(w, (0, 0))
        bar = 26
        frame.fill((0, 0, 0), (0, 0, INTERNAL_W, bar))
        frame.fill((0, 0, 0), (0, INTERNAL_H - bar, INTERNAL_W, bar))
        if (self.t // 12) % 2 == 0:
            fnt = get_font(13)
            img = fnt.render("● REPLAY", True, (255, 90, 90))
            frame.blit(img, (10, 6))


# ================================================================ 选人 / 按键设置

SEL_ACTS = ("left", "right", "jump", "block", "melee", "ranged", "throw",
            "super")


class SelectState:
    """选人界面状态机（mode = "2p" | "ai" | "training"）。

    handle(key) 返回 ("start", (m1, m2)) / ("back", None) / (None, None)；
    ai/training 模式下 P2（CPU/假人）由随机源抽取机体。
    """

    def __init__(self, mode, difficulty="normal", rng=None):
        self.mode = mode
        self.difficulty = difficulty
        self.cur = [0, 0]          # [P1 游标, P2 游标]（MECH_ORDER 下标）
        self.locked = [False, False]
        self.rng = rng if rng is not None else random

    def handle(self, key):
        if key == pygame.K_ESCAPE:
            return "back", None
        p2_active = self.mode == "2p"
        if not self.locked[0]:
            if key == P1_KEYS["left"]:
                self.cur[0] = (self.cur[0] - 1) % len(MECH_ORDER)
            elif key == P1_KEYS["right"]:
                self.cur[0] = (self.cur[0] + 1) % len(MECH_ORDER)
            elif key == P1_KEYS["melee"]:
                self.locked[0] = True
        if p2_active and not self.locked[1]:
            if key == P2_KEYS["left"]:
                self.cur[1] = (self.cur[1] - 1) % len(MECH_ORDER)
            elif key == P2_KEYS["right"]:
                self.cur[1] = (self.cur[1] + 1) % len(MECH_ORDER)
            elif key == P2_KEYS["melee"]:
                self.locked[1] = True
        if self.locked[0] and (self.locked[1] or not p2_active):
            m1 = MECH_ORDER[self.cur[0]]
            m2 = (MECH_ORDER[self.cur[1]] if p2_active
                  else self.rng.choice(MECH_ORDER))
            return "start", (m1, m2)
        return None, None


class KeyConfigState:
    """按键重映射界面状态：行游标 + 等待按键；同玩家键位冲突自动交换。

    handle(key) 返回 "back"（ESC）/ "changed"（发生改键或恢复默认）/ None。
    持久化由调用方在 "changed" 时 save_keymap()。
    """

    def __init__(self):
        self.idx = 0
        self.waiting = False

    def rows(self):
        out = []
        for who, km in (("P1", P1_KEYS), ("P2", P2_KEYS)):
            for act in SEL_ACTS:
                out.append((who, act, pygame.key.name(km[act])))
        return out

    def handle(self, key):
        if self.waiting:               # 等待绑定：任意键生效，ESC 取消
            self.waiting = False
            if key == pygame.K_ESCAPE:
                return None
            who, act, _ = self.rows()[self.idx]
            km = P1_KEYS if who == "P1" else P2_KEYS
            old = km[act]
            for other in SEL_ACTS:     # 该键已被同玩家其他动作占用 → 互换
                if other != act and km[other] == key:
                    km[other] = old
            km[act] = key
            return "changed"
        col, row = self.idx // len(SEL_ACTS), self.idx % len(SEL_ACTS)
        if key == pygame.K_UP:
            row = (row - 1) % len(SEL_ACTS)
        elif key == pygame.K_DOWN:
            row = (row + 1) % len(SEL_ACTS)
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            col = 1 - col
        elif key == pygame.K_RETURN:
            self.waiting = True
        elif key == pygame.K_r:
            P1_KEYS.update(DEFAULT_P1_KEYS)
            P2_KEYS.update(DEFAULT_P2_KEYS)
            return "changed"
        elif key == pygame.K_ESCAPE:
            return "back"
        self.idx = col * len(SEL_ACTS) + row
        return None


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

    load_keymap()                  # 启动读取重映射键位（keymap.json）
    frames = build_mech_frames()
    bg = build_background()
    sfx = Sfx()
    pads = PadMap()                # 手柄：1号→P1 2号→P2，即插即用无需配置
    scanlines = build_scanlines()

    demo = "--demo" in sys.argv            # 演示模式：AI 对 AI，直接开打
    difficulty = "normal"
    scene = FIGHT if demo else MENU
    fight = None                           # 菜单场景下尚无对战实例
    sel = None                             # 选人界面状态
    kc = None                              # 按键设置界面状态
    if demo:
        fight = Fight("demo", frames, bg, sfx, difficulty=difficulty)
    menu_t = 0
    victory_t = 0
    running = True
    # 冒烟钩子：MECHDUEL_SMOKE=N 帧后自动退出（配合 dummy 驱动无头自检）
    smoke = int(os.environ.get("MECHDUEL_SMOKE", "0") or 0)
    smoke_scene = os.environ.get("MECHDUEL_SMOKE_SCENE", "")
    if smoke and not demo:
        if smoke_scene == "select":
            sel = SelectState("ai", difficulty)
            scene = SELECT
        elif smoke_scene == "keyconfig":
            kc = KeyConfigState()
            scene = KEYCONFIG
        elif smoke_scene == "training":
            fight = Fight("training", frames, bg, sfx)
    frame_i = 0

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_m:           # 全局静音开关
                    sfx.toggle_mute()
                elif ev.key == pygame.K_ESCAPE:
                    if scene in (FIGHT, VICTORY):
                        scene, fight = MENU, None
                    elif scene == SELECT:
                        scene, sel = MENU, None
                    elif scene == KEYCONFIG:
                        scene, kc = MENU, None
                    else:
                        running = False
                elif scene == MENU:
                    if ev.key == pygame.K_1:
                        sel = SelectState("2p", difficulty)
                        scene = SELECT
                        sfx.play("menu")
                    elif ev.key == pygame.K_2:
                        sel = SelectState("ai", difficulty)
                        scene = SELECT
                        sfx.play("menu")
                    elif ev.key == pygame.K_3:
                        sel = SelectState("training", difficulty)
                        scene = SELECT
                        sfx.play("menu")
                    elif ev.key == pygame.K_4:
                        fight = Fight("demo", frames, bg, sfx,
                                      difficulty=difficulty)
                        scene = FIGHT
                        sfx.play("menu")
                    elif ev.key == pygame.K_5:
                        kc = KeyConfigState()
                        scene = KEYCONFIG
                        sfx.play("menu")
                    elif ev.key == pygame.K_TAB:   # AI 难度三档轮换
                        difficulty = AI_LEVELS[
                            (AI_LEVELS.index(difficulty) + 1) % len(AI_LEVELS)]
                        sfx.play("menu")
                elif scene == SELECT and sel is not None:
                    act, payload = sel.handle(ev.key)
                    if act == "back":
                        scene, sel = MENU, None
                    elif act == "start":
                        m1, m2 = payload
                        mode = ("2p" if sel.mode == "2p"
                                else "ai" if sel.mode == "ai" else "training")
                        fight = Fight(mode, frames, bg, sfx, m1=m1, m2=m2,
                                      difficulty=difficulty)
                        scene, sel = FIGHT, None
                        sfx.play("menu")
                elif scene == FIGHT and fight is not None:
                    if ev.key == pygame.K_r:
                        if fight.training:
                            fight.reset_round()    # 训练：仅重启假人
                        else:
                            fight.restart_match()
                        sfx.play("menu")
                    elif fight.training and ev.key == pygame.K_F1:
                        fight.show_hitboxes = not fight.show_hitboxes
                    elif fight.training and ev.key == pygame.K_F2:
                        fight.dummy_block = not fight.dummy_block
                elif scene == VICTORY and ev.key == pygame.K_r:
                    if fight:
                        fight.restart_match()
                        scene = FIGHT
                    sfx.play("menu")
                elif scene == KEYCONFIG and kc is not None:
                    res = kc.handle(ev.key)
                    if res == "back":
                        scene, kc = MENU, None
                    elif res == "changed":
                        save_keymap()

        frame = pygame.Surface((INTERNAL_W, INTERNAL_H))
        if scene == MENU:
            menu_t += 1
            draw_menu(frame, bg, frames, menu_t, difficulty)
        elif scene == SELECT and sel is not None:
            menu_t += 1
            draw_select(frame, bg, frames, sel, menu_t)
        elif scene == KEYCONFIG and kc is not None:
            menu_t += 1
            draw_keyconfig(frame, bg, kc.rows(), kc.idx, kc.waiting, menu_t)
        elif scene == FIGHT and fight is not None:
            inp = InputMux(pygame.key.get_pressed(),
                           pads.poll([P1_KEYS, P2_KEYS]))
            fight.step(inp)
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
        sfx.play_bgm("battle" if scene in (FIGHT, VICTORY) else "menu")
        clock.tick(FPS)
        frame_i += 1
        if smoke and frame_i >= smoke:
            running = False

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

    # 2) 强制 KO 流程：回放高光 → 慢镜头 → 下一局重置
    f2 = Fight("ai", frames, bg, sfx)
    f2.phase = ACTIVE
    f2.phase_t = INTRO_FRAMES
    res = f2.p2.take_damage(9999, 1, f2.fx, sfx, heavy=True)
    assert res == "ko" and f2.p2.state == "ko"
    f2.step(None)
    assert f2.wins[0] == 1
    assert f2.phase == REPLAY, f"KO 后未进入高光回放: {f2.phase}"
    for _ in range(10):
        f2.step(None)
        if f2.phase == SLOW:
            break
    assert f2.phase == SLOW, "回放后未进入慢镜头"
    for _ in range(KO_SLOW_FRAMES + ROUND_END_FRAMES + 10):
        f2.step(None)
    assert f2.round_no == 2 and f2.p2.hp == f2.p2.max_hp
    print("[2] KO → 回放 → 慢镜头 → 下一局重置: OK")

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
    assert f12.p2.hp <= f12.p2.max_hp - GARNET_SUPER_DMG, "冲撞未命中"
    assert f12.p2.state in ("thrown", "hurt")
    print("[12] GARNET 超必杀冲撞: OK")

    # 13) AZURE 超必杀「苍蓝齐射」：三连强化光束
    f13 = Fight("2p", frames, bg, sfx)
    f13.phase = ACTIVE
    f13.p1.x, f13.p2.x = 160, 320
    f13.p2.super = SUPER_MAX
    f13.step(FakeKeys({P2_KEYS["super"]: True}))
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

    # 17) 训练模式：无限时间 + 假人自动格挡 + KO 不记分并自动重启
    f17 = Fight("training", frames, bg, sfx)
    f17.phase = ACTIVE
    f17.dummy_block = True
    t0 = f17.timer
    for _ in range(90):
        f17.step(FakeKeys({}))
    assert f17.timer == t0, "训练模式计时不应减少"
    f17.p1.x, f17.p2.x = 200, 226
    f17.p1.melee_cd = 0
    keys = FakeKeys({pygame.K_j: True})
    for _ in range(30):
        f17.step(keys)
        if f17.p2.hp < f17.p2.max_hp:
            break
    chip = max(1, round(f17.p1.spec["melee_damage"] * BLOCK_REDUCE))
    assert f17.p2.hp == f17.p2.max_hp - chip, "训练假人格挡失效（应只吃 chip）"
    f17.p2.hp = 1
    f17.p1.melee_cd = 0
    for _ in range(400):
        f17.step(keys)
        if f17.p2.hp <= 0:
            break
    assert f17.p2.hp <= 0 and f17.wins == [0, 0], "训练模式 KO 不应记分"
    assert f17.phase in (SLOW, ROUND_END), "训练 KO 未进慢镜头"
    for _ in range(600):
        f17.step(keys)
        if f17.p2.hp == f17.p2.max_hp:
            break
    assert f17.p2.hp == f17.p2.max_hp, "训练假人未自动重启"
    print("[17] 训练模式（无限时/假人格挡/KO 重启）: OK")

    # 18) 选人状态机：游标移动 / 双人分别锁定 / AI 模式随机对手
    sel = SelectState("ai", rng=random.Random(5))
    sel.handle(pygame.K_d)
    sel.handle(pygame.K_d)
    assert sel.cur[0] == 2, "P1 游标未移动到第三台机甲"
    act, payload = sel.handle(P1_KEYS["melee"])
    assert act == "start" and payload[0] == MECH_ORDER[2], "P1 锁定失败"
    assert payload[1] in MECH_ORDER, "AI 随机体不在名单内"
    sel2 = SelectState("2p", rng=random.Random(5))
    sel2.handle(P1_KEYS["right"])          # P1 → 1
    sel2.handle(P2_KEYS["left"])           # P2 环绕 → 2
    act, payload = sel2.handle(P1_KEYS["melee"])
    assert act is None and sel2.locked[0] and not sel2.locked[1], \
        "P1 锁定后不应直接开局"
    act, payload = sel2.handle(P2_KEYS["melee"])
    assert act == "start" and payload == (MECH_ORDER[1], MECH_ORDER[2]), \
        "双人选人结果不符"
    print("[18] 选人状态机: OK")

    # 19) 按键重映射：绑定 / 冲突交换 / 持久化往返
    kc = KeyConfigState()
    assert len(kc.rows()) == 16, "键位行数应为 P1+P2 各 8 项"
    kc.idx = 4                              # P1 melee 行
    old_melee = P1_KEYS["melee"]
    assert kc.handle(pygame.K_RETURN) is None and kc.waiting
    assert kc.handle(pygame.K_o) == "changed"
    assert P1_KEYS["melee"] == pygame.K_o and not kc.waiting, "改键未生效"
    kc.idx = 5                              # P1 ranged 行
    old_ranged = P1_KEYS["ranged"]          # 冲突交换语义：两动作互换键位
    kc.handle(pygame.K_RETURN)
    assert kc.handle(pygame.K_o) == "changed"
    assert P1_KEYS["ranged"] == pygame.K_o, "ranged 改键未生效"
    assert P1_KEYS["melee"] == old_ranged, "冲突键未互换"
    tmp = "keymap_selftest.json"
    if os.path.exists(tmp):
        os.remove(tmp)
    save_keymap(tmp)
    P1_KEYS["ranged"] = pygame.K_q
    assert load_keymap(tmp) and P1_KEYS["ranged"] == pygame.K_o, \
        "键位持久化往返失败"
    os.remove(tmp)
    P1_KEYS.update(DEFAULT_P1_KEYS)         # 还原，避免污染其他用例
    P2_KEYS.update(DEFAULT_P2_KEYS)
    print("[19] 按键重映射 + 冲突交换 + 持久化: OK")

    # 20) 平衡回归：AI vs AI ×N 局（默认 100，可 MECHDUEL_BALANCE_N 调整），
    #     每对机体左右互换抵消机体强度差 → 度量纯先后手公平性
    N = int(os.environ.get("MECHDUEL_BALANCE_N", "100"))
    wins = [0, 0]
    draws = 0
    for i in range(N):
        pi = i % (len(MECH_ORDER) ** 2)
        m1, m2 = MECH_ORDER[pi // len(MECH_ORDER)], MECH_ORDER[pi % len(MECH_ORDER)]
        if i % 2:
            m1, m2 = m2, m1
        fb = Fight("cpu", frames, bg, sfx, m1=m1, m2=m2, quiet=True)
        fb.ai1 = AIController(fb.p1, fb.p2, "normal", random.Random(7000 + i * 2))
        fb.ai2 = AIController(fb.p2, fb.p1, "normal",
                              random.Random(7000 + i * 2 + 1))
        guard = ROUND_TIME * 60 * 12        # 双 KO 平局兜底：局数/帧数上限
        while fb.match_winner is None and fb.round_no < 9 and guard > 0:
            fb.step(None)
            guard -= 1
        if fb.match_winner is fb.p1:
            wins[0] += 1
        elif fb.match_winner is fb.p2:
            wins[1] += 1
        elif fb.wins[0] != fb.wins[1]:
            wins[0 if fb.wins[0] > fb.wins[1] else 1] += 1
        else:
            draws += 1
    decided = wins[0] + wins[1]
    assert decided == N, f"存在未决局（{N - decided} 局超时未分胜负）"
    r1 = wins[0] / decided
    print(f"[20] 平衡回归 {N} 局: P1 {wins[0]} : P2 {wins[1]}"
          + (f"（平 {draws}）" if draws else "")
          + f" → P1 胜率 {r1:.0%}")
    if not 0.45 <= r1 <= 0.55:
        print("    ⚠ 警告：P1 胜率超出 45%-55% 平衡带，请回调 settings.py 数值")

    print("SELFTEST PASS")
    pygame.quit()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run_window()
