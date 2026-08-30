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
                      AI_LEVELS, MECH_SPECS,
                      P1_KEYS, P2_KEYS, DEFAULT_P1_KEYS, DEFAULT_P2_KEYS,
                      load_keymap, save_keymap, MECH_ORDER, ROUND_TIME,
                      ROUNDS_TO_WIN, KO_SLOW_FRAMES, HITSTOP_FRAMES,
                      MIN_SEPARATION, ARENA_LEFT, ARENA_RIGHT, GROUND_Y,
                      BLOCK_REDUCE, MELEE_WINDUP, MELEE_ACTIVE, THROW_HIT_T,
                      THROW_RANGE,
                      AIR_MELEE_ACTIVE, AIR_MELEE_MULT, RANGED_DAMAGE,
                      RANGED_COST, ENERGY_MAX, REPLAY_FRAMES, REPLAY_HOLD,
                      SUPER_MAX, SUPER_GAIN_HIT, SUPER_GAIN_TAKE,
                      SUPER_GAIN_BLOCK, SUPER_FLASH_FRAMES, AZURE_SUPER_BOLT_DMG,
                      VERDANT_SUPER_BOLT_DMG, GARNET_SUPER_DMG,
                      GUARD_MAX, JUMP_SEP_Y,
                      THROW_TECH_LAG, THROW_TECH_PUSH, BLOCK_STUN,
                      PUNISH_MULT, COMBO_RESET_FRAMES, COMBO_SCALE_MIN,
                      DRIVE_MAX, DRIVE_HIT_GAIN, DRIVE_PARRY_GAIN,
                      PARRY_STAGGER, DIM_DMG, WALL_SPLASH_STUN, SUPER_COST,
                      DIM_GUARD_MULT, STAGE_ORDER, STAGES, STATS_FILE,
                      PARRY_HITSTOP)
from assets import (build_mech_frames, build_background, get_font,
                    SPRITE_W, SPRITE_H, ANCHOR_FX, PIX)
from mech import Mech, IDLE
from effects import Fx
from ai import AIController
from scene_flow import (InputMux, PadMap, SelectState, KeyConfigState,
                        demo_pair, load_stats, save_stats)
from sfx import Sfx
from ui import (HUD, banner, draw_menu, draw_victory, draw_select,
                draw_keyconfig)

MENU, SELECT, FIGHT, VICTORY, KEYCONFIG = (
    "menu", "select", "fight", "victory", "keyconfig")
INTRO, ACTIVE, SLOW, REPLAY, ROUND_END = (
    "intro", "active", "slow", "replay", "round_end")

INTRO_FRAMES = 150
ROUND_END_FRAMES = 100


class FakeKeys:
    """自测用：模拟 pygame.key.get_pressed() 的按位取值接口。"""

    def __init__(self, pressed):
        self.pressed = pressed

    def __getitem__(self, keycode):
        return self.pressed.get(keycode, False)


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

    def callout(self, *a, **k):
        pass

    def slash(self, *a, **k):
        pass

    def ko_burst(self, *a, **k):
        pass

    def throw_impact(self, *a, **k):
        pass

    def flash(self, *a, **k):
        pass


def arcade_next(arcade, player_won):
    """街机模式流程推进。返回 ("next", kwargs) / ("clear", None) / ("fail", None)。

    arcade = {"m1": 玩家机体, "stage": 当前序号, "opps": [(机体, 难度) ×3]}
    """
    if not player_won:
        return "fail", None
    arcade["stage"] += 1
    if arcade["stage"] >= len(arcade["opps"]):
        return "clear", None
    m2, diff = arcade["opps"][arcade["stage"]]
    return "next", {"m2": m2, "difficulty": diff, "stage": arcade["stage"]}


def _seeded_rng(seed):
    return random.Random(seed) if seed is not None else random.Random()


class Fight:
    """一场三局两胜对战：回合状态机 + 判定 + 特效编排。"""

    def __init__(self, mode, frames, bg, sfx, m1="garnet", m2="azure",
                 difficulty="normal", seed=None, quiet=False, pads=None,
                 record_script=False, scripted=None, intro_sub=None):
        self.mode = mode          # "2p" | "ai" | "cpu" | "demo" | "training"
        self.training = mode == "training"
        self.difficulty = difficulty
        self.intro_sub = intro_sub     # 开局横幅副标题（街机关卡标签等）
        self.pads = pads             # 手柄震动（run_window 注入，可为 None）
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
        # 对局录像（输入序列，虚拟输入同构：AI 与真人同一记录路径）
        self.script = [] if record_script else None
        self.scripted = scripted   # 回放模式：逐帧注入录像输入
        self.script_i = 0
        self.playback_done = False
        # 训练模式开关
        self.show_hitboxes = False
        self.dummy_block = False
        # 训练输入历史（最近 30 帧双方输入位图）
        self.input_log = (collections.deque(maxlen=30),
                          collections.deque(maxlen=30))

    def _rumble(self, mag, ms):
        """手柄震动钩子：mag 0~1，ms 毫秒。"""
        if self.pads is not None:
            self.pads.rumble(min(1.0, mag * 0.35), min(1.0, mag), ms)

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
        self.input_log[0].clear()
        self.input_log[1].clear()

    def restart_match(self):
        self.wins = [0, 0]
        self.round_no = 1
        self.match_winner = None
        self.hud.reset()
        if self.script is not None:
            self.script.clear()    # 重开后旧录像失效
        self.script_i = 0
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
        if self.scripted is not None:       # 回放：注入录像输入
            if self.script_i < len(self.scripted):
                a, b = self.scripted[self.script_i]
                for k in self.p1.input:
                    self.p1.input[k] = k in a
                for k in self.p2.input:
                    self.p2.input[k] = k in b
            else:
                self.playback_done = True
            self.script_i += 1
            return
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
            if self.script is not None:         # 录制本帧双方输入
                self.script.append((
                    frozenset(k for k, v in self.p1.input.items() if v),
                    frozenset(k for k, v in self.p2.input.items() if v)))
            self.p1.update(self.p2, self.fx, self.sfx)
            self.p2.update(self.p1, self.fx, self.sfx)
            if self.training:                # 输入历史记录
                self.input_log[0].append(
                    frozenset(k for k, v in self.p1.input.items() if v))
                self.input_log[1].append(
                    frozenset(k for k, v in self.p2.input.items() if v))
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
                lvl = m.super_pending
                m.super_pending = False
                self.hitstop = SUPER_FLASH_FRAMES + 7 * (lvl - 1)
                self.fx.flash(150)
                self.fx.shake(6)
                self._rumble(0.6, 200)
                self.fx.callout(INTERNAL_W / 2, 96,
                                m.spec["super_levels"][lvl]["name"],
                                (255, 214, 100))
                self.sfx.play("super")

    def _spawn_slashes(self):
        from settings import MELEE_WINDUP
        for m in (self.p1, self.p2):
            if m.state == "melee" and m.t == MELEE_WINDUP:
                self.fx.slash(m)
            elif m.state == "air_melee" and m.t == AIR_MELEE_ACTIVE[0]:
                self.fx.slash(m)
            elif (m.state in ("heavy", "special", "air_heavy")
                    and m.move is not None
                    and m.t == m.move["windup"]):
                key = m.move_key or ""
                scale, cool = 1.0, False
                if "fwd" in key or key == "od":
                    scale = 1.35          # 前重/OD：大弧光
                elif "back" in key:
                    scale, cool = 1.05, True   # 后重：青色横扫
                elif key == "air_heavy":
                    scale = 1.15
                self.fx.slash(m, scale=scale, cool=cool)

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
            if res in ("hit", "break", "armor"):
                atk.super = min(SUPER_MAX, atk.super + SUPER_GAIN_HIT)
                dfn.super = min(SUPER_MAX, dfn.super + SUPER_GAIN_TAKE)
                atk.drive = min(DRIVE_MAX, atk.drive + DRIVE_HIT_GAIN)
            elif res == "blocked":
                dfn.super = min(SUPER_MAX, dfn.super + SUPER_GAIN_BLOCK)

        # 超必杀判定：GARNET 系冲撞（等级由 super_level 决定；AZURE/VERDANT 射击型走光束判定）
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            hb = atk.super_hitbox()
            if hb is None or atk.super_did_hit:
                continue
            if hb.colliderect(dfn.body_rect()):
                atk.super_did_hit = True
                lv = atk.spec["super_levels"][atk.super_level]
                res = dfn.take_damage(lv["dmg"], atk.facing,
                                      self.fx, self.sfx,
                                      heavy=True, unblockable=True, launch=True)
                self.fx.shake(8 if atk.super_level < 3 else 10)
                if res == "ko":
                    self._on_ko()
                meter(atk, dfn, "hit")
        # Drive 冲击判定：命中大伤击飞；贴墙目标触发墙崩（眩晕 40 帧）
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            hb = atk.dim_hitbox()
            if hb is None or atk.move_did_hit:
                continue
            if hb.colliderect(dfn.body_rect()):
                atk.move_did_hit = True
                res = dfn.take_damage(DIM_DMG, atk.facing, self.fx, self.sfx,
                                      heavy=True, launch=True,
                                      guard_mult=DIM_GUARD_MULT)
                if res is None:
                    continue
                self.hitstop = HITSTOP_FRAMES + 2
                self._rumble(0.6, 160)
                meter(atk, dfn, res)
                if (res in ("hit", "break", "armor") and dfn.grounded
                        and (dfn.x <= ARENA_LEFT + 30
                             or dfn.x >= ARENA_RIGHT - 30)):
                    dfn.gb_stun = WALL_SPLASH_STUN
                    dfn.state = "guard_break"
                    dfn.t = 0
                    dfn.vy = 0
                    dfn._stun_extra = 0
                    self.fx.callout(dfn.x, dfn.y - 76, "WALL BREAK",
                                    (255, 120, 90))
                    self.fx.shake(8)
                    self._rumble(0.8, 220)
                if res == "ko":
                    self._on_ko()
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
            if len(throws) == 2 or dfn.tech_window > 0:
                # 拆投：同帧双投自动双拆；或防守方在判定窗内按投 → 无伤，
                # 双方后退，投方附加硬直（-6 帧不利，拆投是投择的答案）
                dirn = 1 if dfn.x >= atk.x else -1
                atk.x = max(ARENA_LEFT, atk.x - dirn * THROW_TECH_PUSH)
                dfn.x = max(ARENA_LEFT, min(ARENA_RIGHT,
                                            dfn.x + dirn * THROW_TECH_PUSH))
                atk.tech_stun = THROW_TECH_LAG
                self.fx.callout((atk.x + dfn.x) / 2, GROUND_Y - 66, "TECH",
                                (120, 230, 255))
                self.sfx.play("block")
                continue
            res = dfn.take_damage(atk.spec["throw_damage"], atk.facing,
                                  self.fx, self.sfx,
                                  heavy=True, unblockable=True, launch=True)
            if res == "hit":
                self.hitstop = HITSTOP_FRAMES + 3
                self._rumble(0.4, 120)
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
                                  self.fx, self.sfx, heavy=True,
                                  punish=dfn.punishable)
            if res is None:            # 对方无敌帧：判定不消耗，攻击穿透
                continue
            atk.melee_did_hit = True
            if res == "parried":           # 被完美格挡：时停 + 攻击中断 + 踉跄
                self.hitstop = PARRY_HITSTOP
                self.fx.flash(70)
                self.fx.shake(4)
                atk.stagger = PARRY_STAGGER
                atk._enter(IDLE)
                continue
            if res == "blocked":
                atk.melee_blocked = True   # 被防 → 解锁被防取消
            meter(atk, dfn, res)
            if res == "hit" or res == "break":
                self.hitstop = HITSTOP_FRAMES
                self._rumble(0.35 if res == "hit" else 0.6,
                             90 if res == "hit" else 160)
            elif res == "ko":
                self._on_ko()
        # 重击/特殊技判定（MOVE_DEFS 数据驱动：重击/前重/后重/突进技/空中重）
        moves = []
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            hb = atk.move_hitbox()
            if hb is None or atk.move_did_hit:
                continue
            if hb.colliderect(dfn.body_rect()):
                moves.append((atk, dfn))
        for atk, dfn in moves:
            if atk.move_did_hit:
                continue
            d = atk.move
            res = dfn.take_damage(d["dmg"], atk.facing, self.fx, self.sfx,
                                  heavy=True, launch=d.get("launch", False),
                                  punish=dfn.punishable,
                                  guard_mult=d.get("guard_mult", 1.0))
            if res is None:            # 无敌帧：判定不消耗
                continue
            atk.move_did_hit = True
            if res == "parried":           # 被完美格挡：时停 + 攻击中断 + 踉跄
                self.hitstop = PARRY_HITSTOP
                self.fx.flash(70)
                self.fx.shake(4)
                atk.stagger = PARRY_STAGGER
                atk._enter(IDLE)
                continue
            meter(atk, dfn, res)
            if d.get("pull") and res in ("hit", "break"):
                dfn.x = max(ARENA_LEFT, min(ARENA_RIGHT,
                                            atk.x + atk.facing * d["pull"]))
            if res in ("hit", "break", "armor"):
                self.hitstop = HITSTOP_FRAMES
                self._rumble(0.35, 90)
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
                                         self.fx, self.sfx, heavy=False,
                                         punish=target.punishable)
                if res is None:            # 无敌帧：光束穿透不消失
                    continue
                bolt.dead = True
                if res == "parried":       # 被完美格挡：时停 + 弹体被弹开
                    self.hitstop = PARRY_HITSTOP
                    self.fx.flash(70)
                    self.fx.shake(4)
                    bolt.owner.stagger = PARRY_STAGGER
                    bolt.owner._enter(IDLE)
                    continue
                meter(bolt.owner, target, res)
                if res == "hit" or res == "break":
                    self._rumble(0.2 if res == "hit" else 0.6,
                                 70 if res == "hit" else 160)
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
        self._rumble(1.0, 320)
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
                       sub=self.intro_sub or
                       f"{self.p1.spec['name']} vs {self.p2.spec['name']}")
            else:
                banner(frame, "FIGHT!", pulse=True)
        elif self.banner_text:
            banner(frame, self.banner_text, sub=self.banner_sub)
        if self.training:
            self._training_overlay(frame)
        if self.scripted is not None:      # 整局回放标识
            img = get_font(10).render("▶ 对局回放", True, (120, 230, 255))
            frame.blit(img, (10, 28))

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
        # 输入历史位图：上=P1 下=P2，亮点=按键（金=攻击系 蓝=移动系）
        acts = ("left", "right", "jump", "block", "melee", "heavy",
                "ranged", "throw", "super")
        for pi, log in enumerate(self.input_log):
            base_y = INTERNAL_H - 31 - 14 + pi * 5
            for fi, acts_f in enumerate(log):
                x = 6 + fi * 3
                for ai, act in enumerate(acts):
                    if act in acts_f:
                        col = ((255, 214, 100) if ai >= 4
                               else (120, 180, 255))
                        frame.fill(col, (x, base_y + ai, 2, 1))
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
    stats = load_stats()           # 战绩存档
    frames = build_mech_frames()
    stage_i = 0
    bg = build_background(theme=STAGE_ORDER[stage_i])
    sfx = Sfx()
    pads = PadMap()                # 手柄：1号→P1 2号→P2，即插即用无需配置
    scanlines = build_scanlines()

    demo = "--demo" in sys.argv            # 演示模式：AI 对 AI，直接开打
    difficulty = "normal"
    battle_i = 0                           # 战斗曲 A/B 按局轮换
    scene = FIGHT if demo else MENU
    fight = None                           # 菜单场景下尚无对战实例
    sel = None                             # 选人界面状态
    kc = None                              # 按键设置界面状态
    if demo:
        battle_i += 1
        fight = Fight("demo", frames, bg, sfx, difficulty=difficulty,
                      pads=pads, record_script=True)
    victory_fight = None                   # 回放前的结算局引用
    arcade = None                          # 街机模式状态（None=非街机）
    arcade_result = None                   # ("clear"/"fail", 通过层数)
    menu_t = 0
    victory_t = 0
    demo_i = 0                             # 演示轮换计数（demo_pair）
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
            fight = Fight("training", frames, bg, sfx, pads=pads,
                      record_script=True)
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
                        arcade, arcade_result = None, None
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
                        battle_i += 1
                        fight = Fight("demo", frames, bg, sfx,
                                      difficulty=difficulty, pads=pads,
                                      record_script=True)
                        scene = FIGHT
                        sfx.play("menu")
                    elif ev.key == pygame.K_5:
                        kc = KeyConfigState()
                        scene = KEYCONFIG
                        sfx.play("menu")
                    elif ev.key == pygame.K_6:
                        sel = SelectState("arcade", difficulty)
                        scene = SELECT
                        sfx.play("menu")
                    elif ev.key == pygame.K_TAB:   # AI 难度三档轮换
                        difficulty = AI_LEVELS[
                            (AI_LEVELS.index(difficulty) + 1) % len(AI_LEVELS)]
                        sfx.play("menu")
                    elif ev.key == pygame.K_e:     # 场地轮换
                        stage_i = (stage_i + 1) % len(STAGE_ORDER)
                        bg = build_background(theme=STAGE_ORDER[stage_i])
                        sfx.play("menu")
                elif scene == SELECT and sel is not None:
                    act, payload = sel.handle(ev.key)
                    if act == "back":
                        scene, sel = MENU, None
                    elif act == "start":
                        m1, m2 = payload
                        if sel.mode == "arcade":
                            import random as _rnd
                            arcade = {
                                "m1": m1, "stage": 0,
                                "opps": [(MECH_ORDER[_rnd.randrange(
                                    len(MECH_ORDER))], AI_LEVELS[i])
                                    for i in range(3)],
                            }
                            m2, diff = arcade["opps"][0]
                            mode, intro_sub = "ai", (
                                f"街机挑战 1/3 · "
                                f"{MECH_SPECS[m2]['cn_name']}")
                        else:
                            arcade = None
                            mode = ("2p" if sel.mode == "2p"
                                    else "ai" if sel.mode == "ai"
                                    else "training")
                            intro_sub = None
                        battle_i += 1
                        fight = Fight(mode, frames, bg, sfx, m1=m1, m2=m2,
                                      difficulty=diff if sel.mode == "arcade"
                                      else difficulty, pads=pads,
                                      record_script=True,
                                      intro_sub=intro_sub)
                        scene, sel = FIGHT, None
                        sfx.play("menu")
                elif scene == FIGHT and fight is not None:
                    if ev.key == pygame.K_r and not fight.scripted:
                        if arcade is not None:  # 街机：重开当前层
                            fight.reset_round()
                        else:
                            battle_i += 1       # 重开一局换曲
                            if fight.training:
                                fight.reset_round()    # 训练：仅重启假人
                            else:
                                fight.restart_match()
                        sfx.play("menu")
                    elif fight.training and ev.key == pygame.K_F1:
                        fight.show_hitboxes = not fight.show_hitboxes
                    elif fight.training and ev.key == pygame.K_F2:
                        fight.dummy_block = not fight.dummy_block
                elif scene == VICTORY and ev.key == pygame.K_v:
                    if fight is not None and fight.script and not demo:
                        victory_fight = fight           # 整局回放
                        fight = Fight("2p", frames, bg, sfx,
                                      m1=fight.p1.spec_key,
                                      m2=fight.p2.spec_key,
                                      scripted=fight.script, pads=pads)
                        scene = FIGHT
                        sfx.play("menu")
                elif scene == VICTORY and ev.key == pygame.K_r:
                    if arcade is not None:          # 街机：整链重开
                        arcade["stage"] = 0
                        m2, diff = arcade["opps"][0]
                        sub = f"街机挑战 1/3 · {MECH_SPECS[m2]['cn_name']}"
                        battle_i += 1
                        fight = Fight("ai", frames, bg, sfx, m1=arcade["m1"],
                                      m2=m2, difficulty=diff, pads=pads,
                                      record_script=True, intro_sub=sub)
                        arcade_result = None
                        scene = FIGHT
                    elif fight:
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
            draw_menu(frame, bg, frames, menu_t, difficulty,
                      STAGES[STAGE_ORDER[stage_i]]["name"], stats)
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
            if fight.playback_done and fight.phase == ROUND_END:
                fight, scene = victory_fight, VICTORY   # 回放结束回结算页
                victory_t = 0
            elif fight.match_winner:
                if (not demo and fight.mode != "training"
                        and not fight.scripted):        # 回放不重复记战绩
                    stats["matches"] += 1
                    wname = fight.match_winner.spec_key
                    stats["wins"][wname] = stats["wins"].get(wname, 0) + 1
                    for p in (fight.p1, fight.p2):
                        stats["picks"][p.spec_key] = stats["picks"].get(p.spec_key, 0) + 1
                    save_stats(stats)
                if arcade is not None:                  # 街机流程推进
                    act, kw = arcade_next(arcade, fight.match_winner is fight.p1)
                    if act == "next":
                        battle_i += 1
                        sub = (f"街机挑战 {kw['stage'] + 1}/3 · "
                               f"{MECH_SPECS[kw['m2']]['cn_name']}")
                        fight = Fight("ai", frames, bg, sfx, m1=arcade["m1"],
                                      m2=kw["m2"], difficulty=kw["difficulty"],
                                      pads=pads, record_script=True,
                                      intro_sub=sub)
                        sfx.play("fight")
                    else:
                        arcade_result = ("clear" if act == "clear" else "fail",
                                         arcade["stage"])
                        scene = VICTORY
                        victory_t = 0
                        sfx.play("win")
                        if act == "clear" and not fight.scripted:
                            stats["arcade_clears"] = stats.get("arcade_clears", 0) + 1
                            save_stats(stats)
                else:
                    scene = VICTORY
                    victory_t = 0
                    sfx.play("win")
        else:  # VICTORY
            victory_t += 1
            draw_victory(frame, bg, fight.match_winner.spec,
                         fight.wins[0], fight.wins[1],
                         has_replay=bool(fight.script) and not demo,
                         arcade_result=arcade_result[0] if arcade_result else None,
                         arcade_stage=arcade_result[1] if arcade_result else 0)
            if demo and victory_t > FPS * 6:   # 演示模式：轮换机体与难度再来一局
                demo_i += 1
                battle_i += 1
                m1, m2, diff = demo_pair(demo_i)
                fight = Fight("demo", frames, bg, sfx, m1=m1, m2=m2,
                              difficulty=diff, pads=pads)
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
        sfx.play_bgm(("battle2" if battle_i % 2 else "battle")
                     if scene in (FIGHT, VICTORY) else "menu")
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
    assert f12.p1.invuln and f12.p1.super == SUPER_MAX - SUPER_COST,         "Lv1 应消耗 1 层槽位"
    assert f12.p1.super_level == 1
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
    sel2.handle(P2_KEYS["left"])           # P2 环绕 → 3（四机体）
    act, payload = sel2.handle(P1_KEYS["melee"])
    assert act is None and sel2.locked[0] and not sel2.locked[1], \
        "P1 锁定后不应直接开局"
    act, payload = sel2.handle(P2_KEYS["melee"])
    assert act == "start" and payload == (MECH_ORDER[1], MECH_ORDER[3]), \
        "双人选人结果不符"
    print("[18] 选人状态机: OK")

    # 19) 按键重映射：绑定 / 冲突交换 / 持久化往返
    kc = KeyConfigState()
    assert len(kc.rows()) == 18, "键位行数应为 P1+P2 各 9 项（含重击）"
    kc.idx = 4                              # P1 melee 行
    old_melee = P1_KEYS["melee"]
    assert kc.handle(pygame.K_RETURN) is None and kc.waiting
    assert kc.handle(pygame.K_o) == "changed"
    assert P1_KEYS["melee"] == pygame.K_o and not kc.waiting, "改键未生效"
    kc.idx = 6                              # P1 ranged 行（heavy 插入后）
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

    # 21) 连段伤害衰减 + 连段计数 + 重置（[22] 预留给 5B 拖尾修正）
    f21 = Fight("2p", frames, bg, sfx)
    f21.phase = ACTIVE
    v = f21.p2
    hp0 = v.hp
    deltas = []
    for _ in range(4):
        hp_before = v.hp
        assert v.take_damage(10, 1, f21.fx, sfx) == "hit"
        deltas.append(hp_before - v.hp)
    assert deltas[0] == 10 and deltas[-1] < deltas[0], f"衰减未生效: {deltas}"
    assert deltas == sorted(deltas, reverse=True), f"衰减非单调递减: {deltas}"
    assert v.combo_count == 4, "连段计数错误"
    for _ in range(2):                     # 衰减下限 40%
        hp_before = v.hp
        v.take_damage(10, 1, f21.fx, sfx)
        deltas.append(hp_before - v.hp)
    assert deltas[-2] == deltas[-1] == max(1, round(10 * COMBO_SCALE_MIN)), \
        f"衰减下限不符: {deltas}"
    v.state = "block"                      # 被防重置连段
    assert v.take_damage(10, 1, f21.fx, sfx) == "blocked"
    assert v.combo_count == 0, "被防未重置连段"
    v.state = "idle"                       # 超时重置：命中 1 段后静置 31 帧
    v.take_damage(10, 1, f21.fx, sfx)
    assert v.combo_count == 1
    for _ in range(COMBO_RESET_FRAMES + 1):
        v.update(f21.p1, f21.fx, sfx)
    assert v.combo_count == 0, "超时未重置连段"
    print("[21] 连段衰减 + 计数 + 重置: OK")

    # 22) acid 弹拖尾颜色 + 演示轮换 + 手柄震动静默
    from settings import BOLT_PALETTES
    fx22 = Fx()
    m22 = Mech("verdant", 200, 1, frames)
    fx22.spawn_bolt(m22, 221, GROUND_Y - 38)
    for _ in range(3):
        fx22.bolts[0].update(fx22)
    assert any(p.color == BOLT_PALETTES["acid"]["S"] for p in fx22.particles), \
        "acid 拖尾颜色未修正"
    assert len(set(demo_pair(i) for i in range(9))) == 9, "演示轮换组合重复"
    assert demo_pair(0)[0] != demo_pair(0)[1], "首局演示不应镜像"
    pads = PadMap()
    pads.rumble(0.5, 1.0, 100)             # 无手柄环境应静默不抛错
    print("[22] acid 拖尾 + 演示轮换 + 手柄震动: OK")

    # 23) 受防硬直 + 惩罚反击
    f23 = Fight("2p", frames, bg, sfx)
    f23.phase = ACTIVE
    f23.p2.state = "block"
    assert f23.p2.take_damage(10, 1, f23.fx, sfx) == "blocked"
    assert f23.p2.block_stun == BLOCK_STUN, "受防硬直未置位"
    keys = FakeKeys({})
    for _ in range(BLOCK_STUN):
        f23.step(keys)
        assert f23.p2.state == "block", "受防硬直期间不应能行动"
    f23.step(keys)
    assert f23.p2.state != "block", "硬直结束未恢复行动"
    f23b = Fight("2p", frames, bg, sfx)    # 命中出招后摇 → ×1.2 + 强制击倒
    f23b.phase = ACTIVE
    f23b.p1.x, f23b.p2.x = 200, 226
    f23b.p1.state = "melee"
    f23b.p1.t = MELEE_WINDUP
    f23b.p1.melee_did_hit = False
    f23b.p2.state = "melee"
    f23b.p2.t = MELEE_WINDUP + MELEE_ACTIVE + 1
    hp0 = f23b.p2.hp
    f23b.step(FakeKeys({}))
    assert hp0 - f23b.p2.hp == max(1, round(
        f23b.p1.spec["melee_damage"] * PUNISH_MULT)), \
        f"惩罚反击倍率不符: {hp0 - f23b.p2.hp}"
    assert f23b.p2.state == "thrown", f"惩罚反击未强制击倒: {f23b.p2.state}"
    f23c = Fight("2p", frames, bg, sfx)    # 对照：判定相中命中 → 无惩罚加成
    f23c.phase = ACTIVE
    f23c.p1.x, f23c.p2.x = 200, 226
    f23c.p1.state = "melee"
    f23c.p1.t = MELEE_WINDUP
    f23c.p1.melee_did_hit = False
    f23c.p2.state = "melee"
    f23c.p2.t = MELEE_WINDUP + 1
    hp0 = f23c.p2.hp
    f23c.step(FakeKeys({}))
    assert hp0 - f23c.p2.hp == f23c.p1.spec["melee_damage"],         "非惩罚命中不应有加成"
    assert f23c.p2.state == "hurt", "非惩罚命中不应击倒"
    print("[23] 受防硬直 + 惩罚反击: OK")

    # 24) 投拆：判定窗内点投 → 无伤 + 投方附加硬直；同帧双投自动双拆
    f24 = Fight("2p", frames, bg, sfx)
    f24.phase = ACTIVE
    f24.p1.x, f24.p2.x = 200, 226
    for i in range(THROW_HIT_T + 2):
        k = {pygame.K_l: True, pygame.K_DOWN: True}  # P1 投 / P2 防
        if i == THROW_HIT_T - 2:
            k[pygame.K_KP3] = True                   # P2 抓取前 2 帧点投
        f24.step(FakeKeys(k))
    assert f24.p2.hp == f24.p2.max_hp, "拆投后不应掉血"
    assert f24.p1.tech_stun == THROW_TECH_LAG, "拆投未附加投方硬直"
    assert f24.p2.state == "block", "拆投后防守方状态异常"
    f24b = Fight("2p", frames, bg, sfx)
    f24b.phase = ACTIVE
    f24b.p1.x, f24b.p2.x = 200, 226
    f24b.p1.state = "throw"
    f24b.p1.t = THROW_HIT_T - 1
    f24b.p2.state = "throw"
    f24b.p2.t = THROW_HIT_T - 1
    f24b.step(FakeKeys({}))
    assert f24b.p1.hp == f24b.p1.max_hp and f24b.p2.hp == f24b.p2.max_hp, \
        "双投自动拆未生效"
    assert f24b.p1.tech_stun == THROW_TECH_LAG == f24b.p2.tech_stun
    print("[24] 投拆 + 双投自动拆: OK")

    # 25) MOVE_DEFS 出招表完整性（数据驱动校验）
    from settings import MOVE_DEFS
    need = ("heavy", "fwd_heavy", "back_heavy", "air_heavy", "dash_light",
            "fwd_bolt", "od")
    for mk in MECH_ORDER:
        d = MOVE_DEFS[mk]
        for k in need:
            assert k in d and d[k] is not None, f"{mk} 出招表缺 {k}"
            mv = d[k]
            assert mv["windup"] > 0 and mv["active"] > 0 and mv["recover"] >= 0
            assert mv["dmg"] > 0, f"{mk}.{k} 伤害非法"
    assert MOVE_DEFS["verdant"]["back_bolt"]["bolt"].get("mine"), \
        "VERDANT 缺种子地雷"
    assert not MOVE_DEFS["garnet"]["back_bolt"], "GARNET 不应有后向特殊弹"
    assert MOVE_DEFS["garnet"]["fwd_bolt"]["bolt"]["dist"] == 90
    print("[25] MOVE_DEFS 出招表完整性: OK")

    # 26) Modern 特殊技 ×3 机甲（冲刺技/方向弹/地雷/拉近/霸体）
    f26 = Fight("2p", frames, bg, sfx)
    f26.phase = ACTIVE
    f26.p1.x, f26.p2.x = 180, 300
    for ks in ({pygame.K_d: True}, {pygame.K_d: True}, {}, {},
               {pygame.K_d: True}):
        f26.step(FakeKeys(ks))
    assert f26.p1.state == "dash", "双击前未进入冲刺"
    for _ in range(3):                     # 冲刺取消门槛 t>=4，先空走再按
        f26.step(FakeKeys({}))
    for _ in range(3):
        f26.step(FakeKeys({pygame.K_j: True}))
        if f26.p1.state == "special":
            break
    assert f26.p1.state == "special" and f26.p1.move_key == "dash_light", \
        f"冲刺轻未接装甲冲撞: {f26.p1.state}/{f26.p1.move_key}"
    # 霸体：判定相内吃一段伤害不中断
    f26.p2.x = 210
    f26.p2.state = "melee"
    f26.p2.t = MELEE_WINDUP
    f26.p2.melee_did_hit = False
    hp0 = f26.p1.hp
    f26.step(FakeKeys({}))
    assert f26.p1.state == "special", f"霸体未生效: {f26.p1.state}"
    assert hp0 - f26.p1.hp == max(1, f26.p2.spec["melee_damage"] // 2), \
        "霸体应吃半伤"
    # GARNET →+K 熔核喷发：弹体 + 射程 90
    f26b = Fight("2p", frames, bg, sfx)
    f26b.phase = ACTIVE
    f26b.p1.ranged_cd = 0
    for _ in range(14):
        f26b.step(FakeKeys({pygame.K_d: True, pygame.K_k: True}))
        if f26b.p1.state == "special":
            break
    assert f26b.p1.state == "special" and f26b.p1.move_key == "fwd_bolt"
    for _ in range(12):
        f26b.step(FakeKeys({}))
        if f26b.fx.bolts:
            break
    assert f26b.fx.bolts and f26b.fx.bolts[0].dmg == 10, "熔核喷发未出弹"
    b26 = f26b.fx.bolts[0]
    for _ in range(80):
        b26.update(f26b.fx)
        if b26.dead:
            break
    assert b26.dead and abs(b26.x - b26.spawn_x) < 100, "射程限制未生效"
    # VERDANT ←+K 种子地雷（静置延时）+ 冲刺拉近
    f26c = Fight("2p", frames, bg, sfx)
    f26c.phase = ACTIVE
    f26c.p1 = Mech("verdant", 240, -1, frames)
    f26c.p1.ranged_cd = 0
    for _ in range(16):
        f26c.step(FakeKeys({pygame.K_a: True, pygame.K_k: True}))
        if f26c.p1.state == "special":
            break
    assert f26c.p1.state == "special" and f26c.p1.move_key == "back_bolt", \
        f"VERDANT 后向布雷未触发: {f26c.p1.move_key}"
    for _ in range(20):
        f26c.step(FakeKeys({}))
        if f26c.fx.bolts:
            break
    assert f26c.fx.bolts and f26c.fx.bolts[0].vx == 0, "地雷应为静止弹"
    f26d = Fight("2p", frames, bg, sfx)
    f26d.phase = ACTIVE
    f26d.p1 = Mech("verdant", 160, 1, frames)
    f26d.p2.x = 196
    f26d.p1.state = "special"
    f26d.p1.move_key = "dash_light"
    f26d.p1.move = MOVE_DEFS["verdant"]["dash_light"]
    f26d.p1.t = MOVE_DEFS["verdant"]["dash_light"]["windup"]
    f26d.p1.melee_did_hit = False
    hp0 = f26d.p2.hp
    f26d.step(FakeKeys({}))
    assert f26d.p2.hp < hp0 and f26d.p2.x <= 160 + 34 + 6, \
        f"藤蔓勾拉未拉近: p2.x={f26d.p2.x}"
    print("[26] Modern 特殊技 ×3 机甲: OK")

    # 27) 取消阶梯：被防取消进特殊技 / 轻链 / 目标连段
    f27 = Fight("2p", frames, bg, sfx)
    f27.phase = ACTIVE
    f27.p1.x, f27.p2.x = 200, 226
    f27.p2.state = "block"
    for _ in range(14):
        f27.step(FakeKeys({pygame.K_j: True, pygame.K_DOWN: True}))
        if f27.p1.melee_blocked:
            break
    assert f27.p1.melee_blocked, "轻斩未被防"
    f27.p1.ranged_cd = 0
    for _ in range(6):
        f27.step(FakeKeys({pygame.K_d: True, pygame.K_k: True}))
        if f27.p1.state == "special":
            break
    assert f27.p1.state == "special" and f27.p1.move_key == "fwd_bolt", \
        f"被防取消失败: {f27.p1.state}"
    f27b = Fight("2p", frames, bg, sfx)    # 轻命中 → 轻链
    f27b.phase = ACTIVE
    f27b.p1.x, f27b.p2.x = 200, 226
    f27b.step(FakeKeys({pygame.K_j: True}))
    for _ in range(14):
        f27b.step(FakeKeys({}))
        if f27b.p1.melee_did_hit:
            break
    assert f27b.p1.melee_did_hit, "轻斩未命中"
    for _ in range(HITSTOP_FRAMES + 1):    # 排空命中顿帧再按键
        f27b.step(FakeKeys({}))
    for _ in range(4):
        f27b.step(FakeKeys({pygame.K_j: True}))   # 松开后再按 → 链
        if f27b.p1.chain_count == 1:
            break
    assert f27b.p1.chain_count == 1 and f27b.p1.state == "melee", "轻链未生效"
    for _ in range(20):                    # 等链击落地计入连段
        f27b.step(FakeKeys({}))
        if f27b.p2.combo_count == 2:
            break
    assert f27b.p2.combo_count == 2, "链段应计入连段"
    f27c = Fight("2p", frames, bg, sfx)    # 轻命中 → 目标连段（重）
    f27c.phase = ACTIVE
    f27c.p1.x, f27c.p2.x = 200, 226
    f27c.step(FakeKeys({pygame.K_j: True}))
    for _ in range(14):
        f27c.step(FakeKeys({}))
        if f27c.p1.melee_did_hit:
            break
    for _ in range(HITSTOP_FRAMES + 1):
        f27c.step(FakeKeys({}))
    for _ in range(4):
        f27c.step(FakeKeys({pygame.K_u: True}))
        if f27c.p1.state == "heavy":
            break
    assert f27c.p1.state == "heavy" and f27c.p1.move_key == "heavy", \
        f"目标连段未生效: {f27c.p1.state}"
    print("[27] 取消阶梯（被防取消/轻链/目标连段）: OK")

    # 28) 相位槽：完美格挡 / Drive 冲击（墙崩）/ 逆转反技 / OD / 绿冲
    from settings import (DRIVE_COST, DRIVE_REVERSAL_COST, PARRY_WINDOW,
                          PARRY_RUSH_WINDOW, DIM_CHARGE_MAX, DREV_DMG)
    f28 = Fight("2p", frames, bg, sfx)
    f28.phase = ACTIVE
    f28.p2.state = "block"
    f28.p2.parry_window = PARRY_WINDOW
    d0 = f28.p2.drive
    assert f28.p2.take_damage(12, 1, f28.fx, sfx, heavy=True) == "parried"
    assert f28.p2.hp == f28.p2.max_hp, "完美格挡不应掉血"
    assert f28.p2.drive == min(DRIVE_MAX, d0 + DRIVE_PARRY_GAIN),         "完美格挡未回复 Drive"
    assert f28.p2.parry_rush > 0, "完美格挡未开启绿冲窗口"
    # Drive 冲击：轻+重蓄力 → 出手命中贴墙对手 → 墙崩
    f28b = Fight("2p", frames, bg, sfx)
    f28b.phase = ACTIVE
    f28b.p1.x, f28b.p2.x = 75, 45          # p2 贴左墙
    keys = FakeKeys({pygame.K_j: True, pygame.K_u: True})
    f28b.step(keys)
    assert f28b.p1.state == "drive_impact", f"冲击未触发: {f28b.p1.state}"
    for _ in range(DIM_CHARGE_MAX + 10):
        f28b.step(keys)
        if f28b.p2.state == "guard_break":
            break
    assert f28b.p2.state == "guard_break", "冲击未命中贴墙目标"
    assert f28b.p2.gb_stun == WALL_SPLASH_STUN, "墙崩眩晕帧不符"
    # 逆转反技：防御中 前方向+重，耗 2 格 Drive
    f28c = Fight("2p", frames, bg, sfx)
    f28c.phase = ACTIVE
    f28c.p1.x, f28c.p2.x = 240, 226
    f28c.step(FakeKeys({pygame.K_DOWN: True}))       # p2 先进入防御
    keys = FakeKeys({pygame.K_DOWN: True, pygame.K_RIGHT: True,
                     pygame.K_KP5: True})
    f28c.step(keys)
    assert f28c.p2.state == "drive_reversal", f"逆转未触发: {f28c.p2.state}"
    assert f28c.p2.drive == DRIVE_MAX - DRIVE_REVERSAL_COST, "逆转消耗不符"
    for _ in range(16):
        f28c.step(keys)
        if f28c.p1.hp < f28c.p1.max_hp:
            break
    assert f28c.p1.hp <= f28c.p1.max_hp - DREV_DMG, "逆转反技未命中"
    # OD 强化技：前方向+轻+束同按，耗 1 格 Drive
    f28d = Fight("2p", frames, bg, sfx)
    f28d.phase = ACTIVE
    f28d.p1.x, f28d.p2.x = 180, 300
    keys = FakeKeys({pygame.K_d: True, pygame.K_j: True, pygame.K_k: True})
    f28d.step(keys)
    assert f28d.p1.state == "special" and f28d.p1.move_key == "od",         f"OD 未触发: {f28d.p1.state}/{f28d.p1.move_key}"
    assert f28d.p1.drive == DRIVE_MAX - DRIVE_COST, "OD 消耗不符"
    # 完美格挡后免费绿冲
    f28e = Fight("2p", frames, bg, sfx)
    f28e.phase = ACTIVE
    f28e.p1.x, f28e.p2.x = 200, 240
    f28e.p2.state = "block"
    f28e.p2.parry_window = PARRY_WINDOW
    f28e.p2.take_damage(12, 1, f28e.fx, sfx, heavy=True)
    for ks in ({pygame.K_LEFT: True}, {pygame.K_LEFT: True}, {},
               {}, {pygame.K_LEFT: True}):
        f28e.step(FakeKeys(ks))
    assert f28e.p2.state == "dash" and f28e.p2.dash_rush,         f"免费绿冲未触发: {f28e.p2.state}"
    assert f28e.p2.drive == DRIVE_MAX, "免费绿冲不应消耗 Drive"
    print("[28] 相位槽五件套: OK")

    # 29) 三层超必杀：Lv2 / Lv3 释放、消耗与演出
    f29 = Fight("2p", frames, bg, sfx)
    f29.phase = ACTIVE
    f29.p1.x, f29.p2.x = 200, 280
    f29.p1.super = 300
    f29.step(FakeKeys({pygame.K_d: True, pygame.K_i: True}))
    assert f29.p1.state == "super" and f29.p1.super_level == 2,         f"Lv2 未触发: {f29.p1.super_level}"
    assert f29.p1.super == 100, "Lv2 应消耗 2 层"
    for _ in range(150):
        f29.step(FakeKeys({}))
        if f29.p2.hp < f29.p2.max_hp:
            break
    assert f29.p2.hp <= f29.p2.max_hp - 34, "Lv2 地裂冲击未命中"
    f29b = Fight("2p", frames, bg, sfx)
    f29b.phase = ACTIVE
    f29b.p1.x, f29b.p2.x = 200, 232
    f29b.p1.super = 300
    f29b.step(FakeKeys({pygame.K_a: True, pygame.K_i: True}))
    assert f29b.p1.state == "super" and f29b.p1.super_level == 3,         f"Lv3 未触发: {f29b.p1.super_level}"
    assert f29b.p1.super == 0, "Lv3 应清空槽位"
    for _ in range(150):
        f29b.step(FakeKeys({}))
        if f29b.p2.hp < f29b.p2.max_hp:
            break
    assert f29b.p2.hp <= f29b.p2.max_hp - 50, "Lv3 熔核天崩未命中"
    f29c = Fight("2p", frames, bg, sfx)    # AZURE Lv3 苍穹风暴：12 连射
    f29c.phase = ACTIVE
    f29c.p1.x, f29c.p2.x = 140, 340
    f29c.p2.super = 300
    keys = FakeKeys({pygame.K_RIGHT: True, pygame.K_KP4: True})
    f29c.step(keys)
    assert f29c.p2.state == "super" and f29c.p2.super_level == 3,         f"AZURE Lv3 未触发: {f29c.p2.super_level}"
    shot_frames = 0
    for _ in range(120):
        f29c.step(FakeKeys({}))
        if f29c.fx.bolts:
            shot_frames += 1
            f29c.fx.bolts.clear()
    assert shot_frames >= 6, f"苍穹风暴连射数不足: {shot_frames}"
    print("[29] 三层超必杀: OK")

    # 30) 分对阵平衡矩阵：C(n,2)+n 格（无序对阵，含镜像），35%-65% 带外报警
    K = max(6, int(os.environ.get("MECHDUEL_MATRIX_K", "18")))
    cells = []
    for i1, a in enumerate(MECH_ORDER):
        for b in MECH_ORDER[i1:]:
            w = [0, 0]                       # a 视角：[a 胜, 对方胜]
            mirror = a == b
            for k in range(2 * K):
                if mirror:
                    m1, m2 = a, a
                else:
                    m1, m2 = (a, b) if k % 2 == 0 else (b, a)
                fb = Fight("cpu", frames, bg, sfx, m1=m1, m2=m2, quiet=True)
                fb.ai1 = AIController(fb.p1, fb.p2, "normal",
                                      random.Random(9000 + k))
                fb.ai2 = AIController(fb.p2, fb.p1, "normal",
                                      random.Random(9500 + k))
                g2 = ROUND_TIME * 60 * 12
                while fb.match_winner is None and fb.round_no < 9 and g2 > 0:
                    fb.step(None)
                    g2 -= 1
                if fb.match_winner is fb.p1:
                    win_mech, win_side = m1, 0
                elif fb.match_winner is fb.p2:
                    win_mech, win_side = m2, 1
                elif fb.wins[0] != fb.wins[1]:
                    i2 = 0 if fb.wins[0] > fb.wins[1] else 1
                    win_mech, win_side = (m1, m2)[i2], i2
                else:
                    win_mech, win_side = None, None   # 平局不计
                if win_side is None:
                    continue
                if mirror:
                    w[win_side] += 1         # 镜像：按先后手计
                elif win_mech == a:
                    w[0] += 1
                else:
                    w[1] += 1
            cells.append((a, b, w))
    print(f"[30] 分对阵平衡矩阵（每格 {2 * K} 局；a vs b=a 的胜率，"
          "镜像=a 在左/P1 侧胜率）:")
    for a, b, w in cells:
        decided = w[0] + w[1]
        rate = w[0] * 100 // decided if decided else 50
        tag = " 镜像" if a == b else ""
        print(f"    {a:>8} vs {b:<8}{tag}: {rate:>3}%  ({w[0]}-{w[1]})")
    alarms = []
    for a, b, w in cells:
        decided = w[0] + w[1]
        if a == b or not decided:
            continue
        rate = w[0] / decided                   # a 的视角
        if not 0.35 <= rate <= 0.65:
            alarms.append(f"{a} vs {b}: {rate:.0%}")
    if alarms:
        print("    ⚠ 警告：对阵失衡（超出 35%-65%）" + " / ".join(alarms))
    n_cells = len(MECH_ORDER) * (len(MECH_ORDER) + 1) // 2
    assert sum(w[0] + w[1] for _, _, w in cells) > 2 * K * n_cells * 9 // 10,         "矩阵存在大量未决局"
    print("[30] 分对阵平衡矩阵: OK")

    # 31) 完整对局录像：input 序列回放与原局状态逐点一致
    f31 = Fight("cpu", frames, bg, sfx, m1="garnet", m2="azure", seed=77,
                quiet=True, record_script=True)
    f31.ai1 = AIController(f31.p1, f31.p2, "normal", random.Random(501))
    f31.ai2 = AIController(f31.p2, f31.p1, "normal", random.Random(502))
    snaps = []
    guard = ROUND_TIME * 60 * 12
    while f31.match_winner is None and guard > 0:
        f31.step(None)
        if f31.t % 300 == 0:
            snaps.append((round(f31.p1.hp), round(f31.p2.hp),
                          round(f31.p1.x, 2), round(f31.p2.x, 2),
                          f31.wins[0], f31.wins[1], f31.round_no))
        guard -= 1
    assert f31.match_winner is not None and len(f31.script) > 200,         "原局未完成或录像过短"
    f31r = Fight("2p", frames, bg, sfx, m1="garnet", m2="azure",
                 quiet=True, scripted=f31.script)
    snaps2 = []
    guard = ROUND_TIME * 60 * 12
    while not f31r.playback_done and f31r.match_winner is None and guard > 0:
        f31r.step(None)
        if f31r.t % 300 == 0:
            snaps2.append((round(f31r.p1.hp), round(f31r.p2.hp),
                           round(f31r.p1.x, 2), round(f31r.p2.x, 2),
                           f31r.wins[0], f31r.wins[1], f31r.round_no))
        guard -= 1
    assert snaps2 == snaps,         f"回放状态不一致（{sum(1 for a, b in zip(snaps, snaps2) if a != b)} 处）"
    assert (f31r.wins[0], f31r.wins[1]) == (f31.wins[0], f31.wins[1])
    assert f31r.match_winner is not None and         f31r.match_winner.spec_key == f31.match_winner.spec_key
    assert f31r.round_no == f31.round_no
    print(f"[31] 对局录像回放一致（{len(f31.script)} 帧输入, "
          f"{len(snaps)} 个状态采样点）: OK")

    # 32) 第四机甲 VIOLET：数据链完整 + 镜像实战可跑 + 四卡选人环绕
    assert MECH_SPECS["violet"]["palette"] == "p4"
    assert MECH_ORDER[-1] == "violet" and len(MECH_ORDER) == 4
    for k in ("heavy", "fwd_heavy", "back_heavy", "air_heavy", "dash_light",
              "fwd_bolt", "od"):
        assert MOVE_DEFS["violet"].get(k), f"violet 缺 {k}"
    f32 = Fight("cpu", frames, bg, sfx, m1="violet", m2="violet", seed=9,
                quiet=True)
    f32.ai1 = AIController(f32.p1, f32.p2, "normal", random.Random(61))
    f32.ai2 = AIController(f32.p2, f32.p1, "normal", random.Random(62))
    g32 = ROUND_TIME * 60 * 6
    while f32.match_winner is None and g32 > 0:
        f32.step(None)
        g32 -= 1
    assert f32.match_winner is not None, "VIOLET 镜像局未完成"
    sel32 = SelectState("2p")
    for _ in range(4):
        sel32.handle(P2_KEYS["right"])     # 四卡游标环绕回 0
    assert sel32.cur[1] == 0
    used = {m for i in range(16) for m in demo_pair(i)[:2]}
    assert used == set(MECH_ORDER), "演示轮换未覆盖全部机体"
    print("[32] 第四机甲 VIOLET + 四卡选人: OK")

    # 33) 街机模式流程：推进 / 失败 / 通关 + 横幅副标题
    a33 = {"m1": "garnet", "stage": 0,
           "opps": [("azure", "easy"), ("verdant", "normal"),
                    ("garnet", "hard")]}
    act, kw = arcade_next(a33, True)
    assert act == "next" and a33["stage"] == 1 and kw["difficulty"] == "normal"
    assert arcade_next(a33, False)[0] == "fail"
    a33b = {"m1": "azure", "stage": 0,
            "opps": [("a", "easy"), ("b", "normal"), ("c", "hard")]}
    for want_stage, want_diff in ((1, "normal"), (2, "hard")):
        act, kw = arcade_next(a33b, True)
        assert act == "next" and a33b["stage"] == want_stage
        assert kw["difficulty"] == want_diff
    assert arcade_next(a33b, True)[0] == "clear"
    f33 = Fight("ai", frames, bg, sfx, m1="garnet", m2="azure",
                intro_sub="街机挑战 1/3 · 苍鳍")
    f33.step(FakeKeys({}))
    assert f33.intro_sub == "街机挑战 1/3 · 苍鳍"
    print("[33] 街机模式流程: OK")

    # 34) 修复合验证：连按合并 / 重击三变体位移 / 击倒躺地 / 完美格挡时停
    from settings import (COMBO_WINDOW as _cw, PARRY_HITSTOP as _ph,
                          LAUNCH_VX_SCALE as _lvs, PARRY_WINDOW as _pw,
                          PARRY_STAGGER as _ps, DRIVE_MAX as _dm,
                          DRIVE_COST as _dc)   # 别名导入：不遮蔽函数级名字
    f34 = Fight("2p", frames, bg, sfx)
    f34.phase = ACTIVE
    f34.step(FakeKeys({pygame.K_j: True}))
    f34.step(FakeKeys({}))
    f34.step(FakeKeys({pygame.K_u: True}))
    assert f34.p1.state == "drive_impact", f"J→U 连按合并失败: {f34.p1.state}"
    f34.step(FakeKeys({pygame.K_j: True}))
    f34.step(FakeKeys({}))
    f34.step(FakeKeys({pygame.K_u: True}))
    assert f34.p1.state == "drive_impact", "U→J 反序连按合并失败"
    f34b = Fight("2p", frames, bg, sfx)
    f34b.phase = ACTIVE
    f34b.p1.drive = _dm
    f34b.step(FakeKeys({pygame.K_d: True, pygame.K_j: True}))
    f34b.step(FakeKeys({pygame.K_d: True}))
    f34b.step(FakeKeys({pygame.K_d: True, pygame.K_k: True}))
    assert f34b.p1.state == "special" and f34b.p1.move_key == "od",         f"OD 连按合并失败: {f34b.p1.state}/{f34b.p1.move_key}"
    assert f34b.p1.drive == _dm - _dc

    def heavy_probe(keys):
        fh = Fight("2p", frames, bg, sfx)
        fh.phase = ACTIVE
        fh.p1.x, fh.p2.x = 150, 320
        x0 = fh.p1.x
        for _ in range(3):
            fh.step(FakeKeys(keys))
        for _ in range(24):
            fh.step(FakeKeys({}))
        return fh.p1.move_key, fh.p1.x - x0

    mk, _ = heavy_probe({pygame.K_u: True})
    assert mk == "heavy"
    mk, dx_fwd = heavy_probe({pygame.K_d: True, pygame.K_u: True})
    assert mk == "fwd_heavy" and dx_fwd > 6, f"前重无前冲: {dx_fwd:.1f}"
    mk, dx_back = heavy_probe({pygame.K_a: True, pygame.K_u: True})
    assert mk == "back_heavy" and dx_back < -6, f"后重未后撤: {dx_back:.1f}"

    f34c = Fight("2p", frames, bg, sfx)
    f34c.phase = ACTIVE
    f34c.p2.take_damage(20, 1, f34c.fx, sfx, heavy=True, launch=True)
    landed = False
    for _ in range(90):
        f34c.step(FakeKeys({}))
        if f34c.p2.grounded and f34c.p2.state == "hurt":
            landed = True
            break
    assert landed, "击倒未落地"
    assert f34c.p2.knockdown and f34c.p2.current_frame_name() == "ko",         f"击倒未呈躺地帧: {f34c.p2.current_frame_name()}"
    rose = False
    for _ in range(12):
        f34c.step(FakeKeys({pygame.K_DOWN: True}))   # 倒地受身
        if f34c.p2.state == "idle":
            rose = True
            break
    assert rose, "倒地受身未生效"
    assert _lvs < 1.0                     # 技能击倒就近倒地

    f34d = Fight("2p", frames, bg, sfx)
    f34d.phase = ACTIVE
    f34d.p1.x, f34d.p2.x = 200, 226
    f34d.p1.state = "melee"
    f34d.p1.t = MELEE_WINDUP
    f34d.p1.melee_did_hit = False
    f34d.p2.state = "block"
    f34d.p2.parry_window = _pw
    f34d.step(FakeKeys({pygame.K_DOWN: True}))   # 按住防：保持 BLOCK 态
    assert f34d.hitstop == _ph, f"完美格挡时停缺失: {f34d.hitstop}"
    assert f34d.p2.hp == f34d.p2.max_hp, "完美格挡掉血"
    assert f34d.p1.stagger == _ps, "攻方未踉跄"
    print("[34] 同按合并 / 重击变体 / 击倒表现 / 格挡时停: OK")

    print("SELFTEST PASS")
    pygame.quit()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run_window()
