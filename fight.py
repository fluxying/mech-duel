# -*- coding: utf-8 -*-
"""战斗核心：回合流程、输入、判定结算、KO 高光回放、街机链与渲染。

从 main.py 拆出（main.py 只留窗口/场景机入口）。Fight 是本模块唯一对外类：
    from fight import Fight
"""

import collections
import random

import pygame

from settings import (INTERNAL_W, INTERNAL_H, ROUND_TIME, ROUNDS_TO_WIN,
                      KO_SLOW_FRAMES, HITSTOP_FRAMES, MIN_SEPARATION,
                      ARENA_LEFT, ARENA_RIGHT, GROUND_Y, JUMP_SEP_Y,
                      MELEE_WINDUP, THROW_HIT_T, THROW_RANGE,
                      AIR_MELEE_ACTIVE, AIR_MELEE_MULT, REPLAY_FRAMES,
                      REPLAY_HOLD, SUPER_MAX, SUPER_GAIN_HIT, SUPER_GAIN_TAKE,
                      SUPER_GAIN_BLOCK, SUPER_FLASH_FRAMES, PARRY_HITSTOP,
                      PARRY_STAGGER, THROW_TECH_LAG, THROW_TECH_PUSH,
                      PUNISH_MULT, COMBO_RESET_FRAMES, COMBO_SCALE_MIN,
                      DRIVE_MAX, DRIVE_HIT_GAIN, DIM_DMG, WALL_SPLASH_STUN,
                      DIM_GUARD_MULT, P1_KEYS, P2_KEYS, AFTERIMAGE_STYLES)
from assets import SPRITE_W, SPRITE_H, ANCHOR_FX, PIX, get_font
from mech import Mech, IDLE
from effects import Fx
from ai import AIController
from ui import HUD, banner

# 回合阶段（main.run_window 也读 ROUND_END）
INTRO, ACTIVE, SLOW, REPLAY, ROUND_END = (
    "intro", "active", "slow", "replay", "round_end")

INTRO_FRAMES = 150
ROUND_END_FRAMES = 100


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
            self._spawn_ghosts()             # 运动签名残影（批次 C）
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
        from settings import MELEE_WINDUP, BOLT_PALETTES
        for m in (self.p1, self.p2):
            if m.state == "melee" and m.t == MELEE_WINDUP:
                self.fx.slash(m)
            elif m.state == "air_melee" and m.t == AIR_MELEE_ACTIVE[0]:
                self.fx.slash(m)
            elif (m.state in ("heavy", "special", "air_heavy")
                    and m.move is not None
                    and m.t == m.move["windup"]):
                key = m.move_key or ""
                scale = 1.0
                if "fwd" in key or key == "od":
                    scale = 1.35          # 前重/OD：大弧光
                elif "back" in key:
                    scale = 1.05          # 后重：窄弧光
                elif key == "air_heavy":
                    scale = 1.15
                # 弧光取机体光束主色：四机各具专属色（红橙/青蓝/酸绿/电紫）
                self.fx.slash(m, scale=scale,
                              col=BOLT_PALETTES[m.spec["bolt_color"]]["S"])

    def _ghost_active(self, m):
        """残影触发窗口：前冲/绿冲、突进系特殊技、超必杀突进段。
        后撤步不计（防御性位移，出残影会变成视觉噪声）。"""
        if m.state == "dash" or m.dash_rush:
            return True
        if m.state == "special" and m.move is not None and m.move.get("rush"):
            return True
        if m.state == "super":
            lv = m.spec["super_levels"].get(m.super_level)
            if lv and ("active" in lv or "dashes" in lv):
                return True
        return False

    def _spawn_ghosts(self):
        """运动签名残影（批次 C）：高速位移时按各台签名参数拍快照。纯表现层。"""
        for m in (self.p1, self.p2):
            st = AFTERIMAGE_STYLES.get(m.palette)
            if not st:
                continue
            if m.ghost_cd > 0:
                m.ghost_cd -= 1
            # 瞬移现形：blink 帧强制留一张更久的残影
            lv = (m.spec["super_levels"].get(m.super_level)
                  if m.state == "super" else None)
            if lv and lv.get("blink_t") == m.t:
                img, xo, yo = m.draw_pose(self.t)
                self.fx.afterimage(img, xo, yo, st["life"] + 8, st["tint"],
                                   bolt=st.get("bolt", False))
                continue
            if m.ghost_cd > 0 or not self._ghost_active(m):
                continue
            m.ghost_cd = st["interval"]
            img, xo, yo = m.draw_pose(self.t)
            self.fx.afterimage(img, xo, yo, st["life"], st["tint"],
                               bolt=st.get("bolt", False))
            if m.grounded:
                if st.get("dust_burst") and m.state == "dash" and m.t <= 2:
                    self.fx.dust_burst(m.x, m.y)      # GARNET 起冲尘暴
                if st.get("petals"):
                    self.fx.petals(m.x, m.y)          # VERDANT 花瓣拖尾

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

        # 超必杀判定：近身型（冲撞/瞬步）走判定盒，射击型走弹体判定
        for atk, dfn in ((self.p1, self.p2), (self.p2, self.p1)):
            hb = atk.super_hitbox()
            if hb is None or atk.super_did_hit:
                continue
            if hb.colliderect(dfn.body_rect()):
                atk.super_did_hit = True
                lv = atk.spec["super_levels"][atk.super_level]
                rush = "active" in lv      # 冲撞不可防+击飞；瞬步斩可防
                res = dfn.take_damage(lv["dmg"], atk.facing,
                                      self.fx, self.sfx,
                                      heavy=True, unblockable=rush,
                                      launch=rush)
                self.fx.shake(8 if atk.super_level < 3 else 10)
                if res == "ko":
                    self._on_ko()
                meter(atk, dfn, "hit" if res in ("hit", "break", "armor")
                      else res)
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
        # 光束判定（贯穿弹命中后继续飞行，每弹只结算一次）
        for bolt in list(self.fx.bolts):
            target = self.p2 if bolt.owner is self.p1 else self.p1
            if bolt.dead or target.state == "ko":
                continue
            if bolt.pierce and bolt.hit_done:
                continue
            if bolt.rect().colliderect(target.body_rect()):
                direction = 1 if (bolt.vx > 0 or
                                  (bolt.vx == 0 and bolt.x < target.x)) \
                    else -1
                res = target.take_damage(bolt.dmg, direction,
                                         self.fx, self.sfx, heavy=False,
                                         punish=target.punishable)
                if res is None:            # 无敌帧：光束穿透不消失
                    continue
                if res == "parried" or not bolt.pierce:
                    bolt.dead = True       # 完美格挡弹开一切弹体
                else:
                    bolt.hit_done = True   # 贯穿：结算后继续飞行
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
        # 运动签名残影压在机甲之下（批次 C）
        self.fx.draw_ghosts(w)
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
