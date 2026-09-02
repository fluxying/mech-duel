# -*- coding: utf-8 -*-
"""机甲角色：状态机（待机/行走/跳跃/近战/射击/防御/受击/倒地）+ 动画 + 战斗判定。

坐标约定：x 为机体中心，y 为脚底高度（越大越靠下），facing 1=朝右 -1=朝左。
所有动作均为地面动作，跳跃用于规避。角色始终自动面向对手。
"""

import pygame

from settings import (GRAVITY, GROUND_Y, ARENA_LEFT, ARENA_RIGHT,
                      MELEE_WINDUP, MELEE_ACTIVE, MELEE_RECOVER, MELEE_COOLDOWN,
                      RANGED_COOLDOWN, RANGED_COST, ENERGY_MAX, ENERGY_REGEN,
                      BLOCK_REDUCE, HURT_STUN, MECH_SPECS, COLORS,
                      THROW_TOTAL, THROW_HIT_T, THROW_COOLDOWN,
                      THROW_VX, THROW_VY, THROWN_LAND_STUN,
                      TAP_WINDOW, DASH_FRAMES, DASH_SPEED,
                      BACKSTEP_FRAMES, BACKSTEP_SPEED, BACKSTEP_INVULN,
                      AIR_MELEE_TOTAL, AIR_MELEE_ACTIVE, AIR_MELEE_MULT,
                      JUGGLE_VY, WAKE_INVULN,
                      SUPER_MAX, SUPER_TOTAL, SUPER_INVULN_FRAMES,
                      VERDANT_SUPER_VY,
                      GUARD_MAX, GUARD_REGEN, GUARD_GAIN_MELEE, GUARD_GAIN_BOLT,
                      GUARD_BREAK_STUN, JUMP_BOOST,
                      BLOCK_STUN, BLOCK_PUSH, COMBO_RESET_FRAMES, combo_scale,
                      PUNISH_MULT, PUNISH_STUN_BONUS,
                      THROW_TECH_WINDOW, MOVE_DEFS, SPECIAL_CD, RANGED_SPEED,
                      DRIVE_MAX, DRIVE_REGEN, DRIVE_COST, DRIVE_REVERSAL_COST,
                      DRIVE_HIT_LOSS, DRIVE_BLOCK_LOSS, DRIVE_PARRY_GAIN,
                      DRIVE_HIT_GAIN, PARRY_WINDOW, PARRY_STAGGER,
                      PARRY_RUSH_WINDOW, RUSH_FRAMES, RUSH_SPEED,
                      DIM_CHARGE_MIN, DIM_CHARGE_MAX, DIM_DMG, DIM_RANGE,
                      DIM_GUARD_MULT, REVERSAL_DEF, WALL_SPLASH_STUN,
                      SUPER_COST, COMBO_WINDOW, LAUNCH_VX_SCALE)
from assets import SPRITE_W, SPRITE_H, ANCHOR_FX, PIX
from effects import Projectile

IDLE, WALK, JUMP, MELEE, SHOOT, BLOCK, HURT, KO = (
    "idle", "walk", "jump", "melee", "shoot", "block", "hurt", "ko")
THROW, DASH, BACKSTEP, AIR_MELEE, THROWN = (
    "throw", "dash", "backstep", "air_melee", "thrown")
SUPER, GBREAK = "super", "guard_break"
HEAVY, AIR_HEAVY, SPECIAL = "heavy", "air_heavy", "special"  # MOVE_DEFS 驱动
DIMPACT, DREVERSAL = "drive_impact", "drive_reversal"        # 相位槽技

# 状态 -> 动画帧序列 [(帧名, 时长帧)]；MELEE/THROW/AIR_MELEE/SUPER 相位由 t 直接推算
ANIMS = {
    IDLE:      [("idle", 36), ("idle", 36)],
    WALK:      [("walk_a", 9), ("walk_b", 9)],
    JUMP:      [("jump", 4)],
    MELEE:     [("atk0", MELEE_WINDUP), ("atk1", MELEE_ACTIVE), ("atk2", MELEE_RECOVER)],
    SHOOT:     [("shoot", 7), ("shoot", 11)],
    BLOCK:     [("block", 4)],
    HURT:      [("hurt", 4)],
    KO:        [("ko", 4)],
    DASH:      [("walk_a", 4), ("walk_b", 4)],
    BACKSTEP:  [("jump", 4)],
    THROWN:    [("hurt", 4)],
    SUPER:     [("atk0", 8), ("atk1", 20), ("atk2", 12)],
    GBREAK:    [("hurt", 4)],
}

MELEE_TOTAL = MELEE_WINDUP + MELEE_ACTIVE + MELEE_RECOVER
SHOOT_TOTAL = 18
SHOOT_FIRE_T = 7      # 该帧发射光束


class Mech:
    def __init__(self, spec_key, x, facing, frames):
        self.spec = MECH_SPECS[spec_key]
        self.spec_key = spec_key
        self.frames = frames                      # assets.build_mech_frames() 结果
        self.max_hp = self.spec["hp"]
        self.x = float(x)
        self.y = float(GROUND_Y)                  # 脚底
        self.vx = 0.0
        self.vy = 0.0
        self.facing = facing
        self.reset_round(x, facing)

    # ------------------------------------------------ 重置（每局开始）
    def reset_round(self, x, facing):
        self.x = float(x)
        self.y = float(GROUND_Y)
        self.vx = self.vy = 0.0
        self.facing = facing
        self.hp = self.max_hp
        self.energy = ENERGY_MAX
        self.super = 0               # 超必杀槽
        self.guard = GUARD_MAX       # 破防值槽
        self.air_jumps_used = 0      # 已用空中跳跃次数（VERDANT 二段跳）
        self.state = IDLE
        self.t = 0                # 状态内计时
        self.anim_t = 0
        self.flash = 0            # 受击白闪剩余帧
        self._stun_extra = 0      # 受击附加硬直
        self.block_stun = 0       # 受防硬直剩余帧
        self.combo_count = 0      # 作为受击方：当前连段已承受段数（衰减依据）
        self.combo_timer = 0      # 距上次被命中帧数（超时重置连段）
        self.tech_window = 0      # 拆投判定窗剩余帧（按投即置位）
        self.tech_stun = 0        # 被拆投后投方附加硬直帧
        self.press_age = {}       # 攻击键最近按下帧号（连按合并窗用）
        self.knockdown = False    # 倒地中（渲染躺地帧）
        self.melee_cd = 0
        self.ranged_cd = 0
        self.throw_cd = 0
        self.melee_did_hit = False
        self.throw_hit_done = False
        self.super_did_hit = False
        self.super_pending = False   # 通知 Fight 播放定格演出
        self.wake_invuln = 0         # 受身起身无敌剩余帧
        self._air_hurt = False       # 浮空受击标记（落地后允许受身）
        self._ground_t = 0           # HURT 落地后的帧数（受身窗口）
        self.age = 0              # 总帧数（双击检测用）
        self._prev_input = {}     # 上一帧输入（新按下检测）
        self._tap_age = {}        # 方向 -> 上次单按帧号
        self._prev_taps = {}      # 上一帧的 _tap_age 快照（双击判定用）
        self.melee_blocked = False  # 上一次轻斩被防（被防取消依据）
        self.chain_count = 0      # 轻斩连打段数（上限 2 链）
        self.move_key = None      # 当前 MOVE_DEFS 技键（HEAVY/SPECIAL 系）
        self.move = None          # 当前技 def
        self.move_did_hit = False
        self.armor_on = False     # 霸体生效中（吃半伤不中断）
        self.armor_left = 0       # 霸体剩余吸收段数
        self.bolt_shots_left = 0  # 特殊技待发弹数
        self.bolt_next_t = 0      # 下一发弹的帧号
        self.drive = DRIVE_MAX    # 相位槽（6 格）
        self.parry_window = 0     # 完美格挡判定窗剩余帧
        self.parry_rush = 0       # 完美格挡后免费绿冲窗口剩余帧
        self.stagger = 0          # 被完美格挡后的踉跄帧
        self.dash_rush = False    # 当前冲刺是否为 Drive Rush
        self.ghost_cd = 0         # 运动签名残影快照冷却（Fight._spawn_ghosts）
        self.dim_t0 = None        # Drive 冲击出手帧（None=蓄力中）
        self.super_level = 1      # 本局超必杀等级（1-3）
        self.gb_stun = GUARD_BREAK_STUN  # 破防/墙崩硬直帧（墙崩较短）
        self.input = {k: False for k in
                      ("left", "right", "jump", "block", "melee", "heavy",
                       "ranged", "throw", "super")}

    # ------------------------------------------------ 辅助量
    @property
    def grounded(self):
        return self.y >= GROUND_Y - 0.01

    @property
    def alive(self):
        return self.hp > 0

    @property
    def invuln(self):
        """无敌帧：后撤步中段 / 受身起身 / 超必杀发动初期。"""
        if self.state == BACKSTEP and BACKSTEP_INVULN[0] <= self.t < BACKSTEP_INVULN[1]:
            return True
        if self.wake_invuln > 0:
            return True
        return self.state == SUPER and self.t < SUPER_INVULN_FRAMES

    @property
    def palette(self):
        return self.spec["palette"]

    @property
    def punishable(self):
        """处于可被惩罚反击的状态：出招后摇 / 投技硬直 / 防御崩坏。"""
        if self.state == GBREAK:
            return True
        if self.state == MELEE and self.t >= MELEE_WINDUP + MELEE_ACTIVE:
            return True
        if self.state == SHOOT and self.t >= SHOOT_FIRE_T:
            return True
        if self.state == THROW and self.t >= THROW_HIT_T:
            return True
        if (self.state in (HEAVY, SPECIAL) and self.move is not None
                and self.t >= self.move["windup"] + self.move["active"]):
            return True
        return False

    def body_rect(self):
        """机体碰撞盒（受击/推挤/中弹判定）。"""
        return pygame.Rect(int(self.x) - 11, int(self.y) - 56, 22, 56)

    def melee_hitbox(self):
        """近战判定盒：斩击/空中下劈判定相存在。"""
        if self.state == AIR_MELEE:
            if not (AIR_MELEE_ACTIVE[0] <= self.t < AIR_MELEE_ACTIVE[1]):
                return None
            f = self.facing
            x0 = self.x + f * 4
            x1 = self.x + f * 36
            left, right = sorted((x0, x1))
            return pygame.Rect(int(left), int(self.y) - 46, int(right - left), 42)
        if self.state != MELEE:
            return None
        if not (MELEE_WINDUP <= self.t < MELEE_WINDUP + MELEE_ACTIVE):
            return None
        f = self.facing
        x0 = self.x + f * 8
        x1 = self.x + f * self.spec["melee_range"]
        left, right = sorted((x0, x1))
        return pygame.Rect(int(left), int(self.y) - 46, int(right - left), 30)

    def muzzle_pos(self):
        """炮口世界坐标（用于光束弹生成与炮口焰）。"""
        return self.x + self.facing * 21, self.y - 38

    def super_hitbox(self):
        """超必杀近身判定：冲撞型（GARNET 系）全身大箱；瞬步型（VIOLET Lv2）
        每段斩击箱；射击型（贯穿/追踪/榴弹）无近身判定，走弹体判定。"""
        if self.state != SUPER:
            return None
        lv = self.spec["super_levels"][self.super_level]
        f = self.facing
        if "active" in lv:
            a0, a1 = lv["active"]
            if not (a0 <= self.t < a1):
                return None
            x0, x1, h = self.x + f * 4, self.x + f * 66, 56
        elif "dashes" in lv:
            if not any(s0 <= self.t < s1 for s0, s1 in lv["dashes"]):
                return None
            x0, x1, h = self.x + f * 2, self.x + f * 46, 52
        else:
            return None
        left, right = sorted((x0, x1))
        return pygame.Rect(int(left), int(self.y) - h, int(right - left), h)

    # ------------------------------------------------ MOVE_DEFS 出招（数据驱动）
    def _start_move(self, state, key, d=None, armor_left=0):
        """按表出招：HEAVY / AIR_HEAVY / SPECIAL / DREVERSAL 共用入口。"""
        d = d or MOVE_DEFS[self.spec_key][key]
        self.move_key = key
        self.move = d
        self.move_did_hit = False
        self.armor_on = False
        self.armor_left = armor_left
        bd = d.get("bolt")
        self.bolt_shots_left = bd.get("shots", 1) if bd else 0
        self.bolt_next_t = d["windup"] + 1 if bd else 0
        self._enter(state)

    def _dbl_fwd(self):
        """本帧是否构成「双击前方向」（用于取消窗内触发 Drive Rush）。"""
        fwd_dir = 1 if self.facing == 1 else -1
        last = self._prev_taps.get(fwd_dir)
        return last is not None and self.age - last <= TAP_WINDOW

    def _drive_rush(self, fx, free=False):
        """绿冲：免费（完美格挡后）或消耗 1 格 Drive。"""
        if free:
            self.parry_rush = 0
        else:
            self.drive = max(0, self.drive - DRIVE_COST)
        self._enter(DASH)
        self.dash_rush = True
        fx.dust(self.x, self.y, n=5)

    def _try_super(self):
        """按超必杀键：依据方向与槽位选择 Lv1/2/3。成功返回 True。"""
        inp = self.input
        if not inp["super"] or self.super < SUPER_COST:
            return False
        fwd = (self.facing == 1 and inp["right"]) or \
              (self.facing == -1 and inp["left"])
        back = (self.facing == 1 and inp["left"]) or \
               (self.facing == -1 and inp["right"])
        lvl = 3 if (back and self.super >= 300) else \
            2 if (fwd and self.super >= 200) else 1
        self.super -= SUPER_COST * lvl
        self.super_level = lvl
        lv = self.spec["super_levels"][lvl]
        self.armor_left = 1 if lv.get("armor") else 0   # 重装冲撞霸体（GARNET Lv2/3）
        self._enter(SUPER)
        self.super_did_hit = False
        self.super_pending = lvl         # 通知 Fight 播放对应等级演出
        return True

    def _pair(self, act_a, act_b):
        """两攻击键在 COMBO_WINDOW 帧内先后按下（含同帧）且仍新鲜。"""
        pa, pb = self.press_age.get(act_a), self.press_age.get(act_b)
        if pa is None or pb is None:
            return False
        return (abs(pa - pb) <= COMBO_WINDOW
                and self.age - max(pa, pb) <= COMBO_WINDOW)

    def _combo_convert(self):
        """攻击键快速连按合并：J+U=Drive 冲击，前方向+J+K=OD。

        人手无法严格同帧，靠 COMBO_WINDOW 容错窗把先落下的键「扣住」等待
        伙伴键（首个键已启动的招式由 MELEE/HEAVY/SHOOT 前摇期调用本函数转换）。
        命中返回状态名并消耗按键记录。
        """
        if not self.grounded:
            return None
        if self._pair("melee", "heavy"):
            self.press_age.pop("melee", None)
            self.press_age.pop("heavy", None)
            self.dim_t0 = None
            self.armor_left = 1          # 蓄力全程吸收一段伤害
            self._enter(DIMPACT)
            return DIMPACT
        fwd = (self.facing == 1 and self.input["right"]) or               (self.facing == -1 and self.input["left"])
        if fwd and self.drive >= DRIVE_COST and self._pair("melee", "ranged"):
            self.press_age.pop("melee", None)
            self.press_age.pop("ranged", None)
            self.drive -= DRIVE_COST
            self._start_move(SPECIAL, "od")
            return SPECIAL
        return None

    def move_hitbox(self):
        """HEAVY / AIR_HEAVY / SPECIAL 判定盒（读 move def，判定相内有效）。"""
        d = self.move
        if d is None:
            return None
        w0, a1 = d["windup"], d["windup"] + d["active"]
        if not (w0 <= self.t < a1):
            return None
        f = self.facing
        x0 = self.x + f * 4
        x1 = self.x + f * d.get("range", 40)
        left, right = sorted((x0, x1))
        return pygame.Rect(int(left), int(self.y) - 46, int(right - left), 30)

    def dim_hitbox(self):
        """Drive 冲击出手相判定盒。"""
        if self.state != DIMPACT or self.dim_t0 is None:
            return None
        rel = self.dim_t0
        if not (rel <= self.t < rel + 6):
            return None
        f = self.facing
        x0 = self.x + f * 4
        x1 = self.x + f * DIM_RANGE
        left, right = sorted((x0, x1))
        return pygame.Rect(int(left), int(self.y) - 56, int(right - left), 56)

    def _special_cmd(self):
        """识别 Modern 特殊技指令（方向+光束键），返回 move key 或 None。"""
        inp = self.input
        fwd = (self.facing == 1 and inp["right"]) or \
              (self.facing == -1 and inp["left"])
        back = (self.facing == 1 and inp["left"]) or \
               (self.facing == -1 and inp["right"])
        defs = MOVE_DEFS[self.spec_key]
        if fwd and inp["ranged"] and defs.get("fwd_bolt"):
            return "fwd_bolt"
        if back and inp["ranged"] and defs.get("back_bolt"):
            return "back_bolt"
        return None

    def _fire_move_bolt(self, fx, sfx):
        """特殊技弹体（含连发/延时雷/弧线榴弹/下投种子）。"""
        bd = self.move["bolt"]
        if bd.get("drop"):                     # 空中下投：从身体处落下
            mx, my = self.x, self.y - 24
        elif bd.get("mine"):                   # 布雷：脚前落地
            mx, my = self.x + self.facing * 42, GROUND_Y - 6
        else:
            mx, my = self.muzzle_pos()
        b = Projectile(self, mx, my, fx.bolt_sprites,
                       vx=self.facing * bd.get("speed", RANGED_SPEED),
                       vy=bd.get("vy", 0.0), grav=bd.get("grav", 0.0),
                       dmg=self.move["dmg"])
        b.max_dist = bd.get("dist")
        b.delay_t = bd.get("delay")
        fx.bolts.append(b)
        fx.muzzle_flash(mx, my, self.facing)
        sfx.play("shoot")

    # ------------------------------------------------ 主更新
    def update(self, opponent, fx, sfx):
        self.age += 1
        if self.melee_cd > 0:
            self.melee_cd -= 1
        if self.ranged_cd > 0:
            self.ranged_cd -= 1
        if self.throw_cd > 0:
            self.throw_cd -= 1
        if self.flash > 0:
            self.flash -= 1
        if self.wake_invuln > 0:
            self.wake_invuln -= 1
        if self.tech_window > 0:
            self.tech_window -= 1
        if self.parry_window > 0:
            self.parry_window -= 1
        if self.parry_rush > 0:
            self.parry_rush -= 1
        self.drive = min(DRIVE_MAX, self.drive + DRIVE_REGEN)
        if self.combo_count > 0:          # 脱离受击超时：连段重置
            self.combo_timer += 1
            if self.combo_timer > COMBO_RESET_FRAMES:
                self.combo_count = 0
        if self.state != BLOCK:
            self.guard = min(GUARD_MAX, self.guard + GUARD_REGEN)  # 防御槽回复
        self.energy = min(ENERGY_MAX, self.energy + ENERGY_REGEN)

        inp = self.input
        st = self.state
        # 新按下检测（供双击冲刺/拆投窗/完美格挡用），随后快照本帧输入
        fresh = {k for k, v in inp.items() if v and not self._prev_input.get(k)}
        if "throw" in fresh:
            self.tech_window = THROW_TECH_WINDOW   # 按投即置位拆投窗
        if "block" in fresh:
            self.parry_window = PARRY_WINDOW       # 按防即置位完美格挡窗
        self._prev_taps = dict(self._tap_age)      # 双击判定取上一次按下帧
        for dname in ("left", "right"):
            if dname in fresh:
                self._tap_age[-1 if dname == "left" else 1] = self.age
        for act in ("melee", "heavy", "ranged"):
            if act in fresh:
                self.press_age[act] = self.age   # 连按合并窗计时
        self._prev_input = dict(inp)

        # 面向对手（动作进行中锁定朝向）
        if st not in (MELEE, SHOOT, THROW, DASH, BACKSTEP, AIR_MELEE, THROWN,
                      SUPER, GBREAK, KO, HEAVY, AIR_HEAVY, SPECIAL,
                      DIMPACT, DREVERSAL):
            self.facing = 1 if opponent.x >= self.x else -1

        if st == KO:
            self._physics(fx)
            self.t += 1
            return

        if st == HURT:
            self.t += 1
            self.vx *= 0.86
            if self.grounded:
                self._ground_t += 1
                # 受身：浮空受击/被投落地后 12 帧内按住跳/防 → 快速起身+无敌
                if (self._air_hurt and self._ground_t <= 12
                        and (inp["jump"] or inp["block"])):
                    self._enter(IDLE)
                    self.combo_count = 0         # 受身成功：连段重置
                    self.knockdown = False
                    self.wake_invuln = WAKE_INVULN
                    fx.dust(self.x, self.y, n=3)
                    self._physics(fx)
                    return
                if self.t >= HURT_STUN + self._stun_extra:
                    self._enter(IDLE)
            else:
                self._ground_t = 0
            self._physics(fx)
            return

        if st == GBREAK:                  # 防御崩坏/墙崩：大硬直，无法防御
            self.t += 1
            self.vx *= 0.85
            if self.t >= self.gb_stun and self.grounded:
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == SUPER:                   # 超必杀（等级由 super_level 决定）
            lv = self.spec["super_levels"][self.super_level]
            self.t += 1
            self.armor_on = self.armor_left > 0
            if "active" in lv:            # 冲撞型（GARNET）：判定相高速突进
                a0, a1 = lv["active"]
                self.vx = self.facing * lv["rush"] if a0 <= self.t < a1 else 0
                if lv.get("wave") and self.t == a1 + 2:
                    self._fire_wave(fx)   # Lv2 地裂冲击波
            elif "dashes" in lv:          # 瞬步乱舞（VIOLET Lv2）：段间重置判定
                self.vx = 0
                for s0, s1 in lv["dashes"]:
                    if self.t == s0:
                        self.super_did_hit = False
                        fx.slash(self, scale=1.25)
                        fx.dust(self.x, self.y, n=4)
                    if s0 <= self.t < s1:
                        self.vx = self.facing * lv["rush"]
            elif "shots" in lv:
                if lv.get("blink_t") == self.t:   # 瞬移到对手背后（VIOLET Lv3）
                    side = 1 if self.x <= opponent.x else -1
                    fx.dust(self.x, self.y, n=5)
                    self.x = max(ARENA_LEFT, min(ARENA_RIGHT,
                                                 opponent.x + side * 30))
                    self.facing = -side
                    fx.dust(self.x, self.y, n=5)
                    fx.shake(4)
                self.vx = self.facing * lv["drift"] if lv.get("drift") else 0
                if self.t in lv["shots"]:
                    if lv.get("rain"):
                        self._fire_rain(opponent, fx, sfx)
                    elif lv.get("arc"):
                        self._fire_super_arc(opponent, fx, sfx)
                    elif lv.get("home"):
                        self._fire_home_shot(opponent, fx, sfx)
                    elif lv.get("pierce"):
                        self._fire_pierce_shot(fx, sfx)
            if self.t >= lv["total"]:
                self.armor_on = False
                self.armor_left = 0
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == DIMPACT:                 # Drive 冲击：蓄力 → 出手（全程霸体）
            self.t += 1
            self.armor_on = self.armor_left > 0
            held = inp["melee"] and inp["heavy"]
            if self.dim_t0 is None:       # 蓄力相
                self.vx = 0
                if ((not held and self.t >= DIM_CHARGE_MIN)
                        or self.t >= DIM_CHARGE_MAX):
                    self.dim_t0 = self.t  # 出手
            else:                         # 出手 + 收招
                rel = self.dim_t0
                self.vx = self.facing * 1.6 if rel <= self.t < rel + 6 else 0
                if self.t >= rel + 26:
                    self.armor_on = False
                    self.dim_t0 = None
                    self._enter(IDLE)
            self._physics(fx)
            return

        if st == DREVERSAL:               # 逆转反技（读 REVERSAL_DEF）
            d = self.move
            self.t += 1
            w0, a1 = d["windup"], d["windup"] + d["active"]
            self.vx = self.facing * 1.0 if w0 <= self.t < a1 else 0
            if self.t >= a1 + d["recover"]:
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == MELEE:
            self.t += 1
            # 前摇期连按合并：轻斩启动后 6 帧内补按伙伴键 → 冲击/OD
            if self.t <= MELEE_WINDUP and self._combo_convert() is not None:
                self._physics(fx)
                return
            # 判定相小幅突进
            if MELEE_WINDUP <= self.t < MELEE_WINDUP + MELEE_ACTIVE:
                self.vx = self.facing * 0.9
            else:
                self.vx = 0
            # 取消阶梯：命中（或被防）后的后摇期可取消（连段核心）
            if (self.grounded and (self.melee_did_hit or self.melee_blocked)
                    and self.t >= MELEE_WINDUP):
                key = self._special_cmd()
                if key is not None:            # 轻斩取消 → 特殊技
                    self._start_move(SPECIAL, key)
                    self._physics(fx)
                    return
                if (inp["ranged"] and self.ranged_cd <= 0
                        and self.energy >= RANGED_COST):
                    self._enter(SHOOT)         # 轻斩取消 → 光束
                    self._physics(fx)
                    return
                if inp["super"] and self._try_super():
                    self._physics(fx)
                    return
                if self._dbl_fwd():            # 取消窗内双击前 → 绿冲
                    self._drive_rush(fx)
                    self._physics(fx)
                    return
                if inp["heavy"]:               # 目标连段：轻 → 重
                    self._start_move(HEAVY, "heavy")
                    self._physics(fx)
                    return
                if "melee" in fresh and self.chain_count < 2:
                    cc = self.chain_count + 1  # 轻斩链（≤2 链）
                    self._enter(MELEE)
                    self.chain_count = cc
                    self._physics(fx)
                    return
                if inp["throw"] and self.throw_cd <= 0:
                    self._enter(THROW)
                    self.throw_hit_done = False
                    self._physics(fx)
                    return
                if inp["jump"]:
                    self.vy = -self.spec["jump_power"] * 0.85
                    self.y -= 0.1
                    fx.dust(self.x, self.y, n=4)
                    sfx.play("jump")
                    self._enter(JUMP)
                    self._physics(fx)
                    return
            if self.t >= MELEE_TOTAL:
                self.melee_cd = MELEE_COOLDOWN
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == SHOOT:
            self.t += 1
            # 启动期连按合并：光束启动后 6 帧内补按轻斩 → OD
            if self.t <= SHOOT_FIRE_T and self._combo_convert() is not None:
                self._physics(fx)
                return
            if self.grounded:
                self.vx = 0
            else:
                self.vx *= 0.96        # 空中射击保留水平动量（缓衰）
            if self.t == SHOOT_FIRE_T:
                self._fire(fx, sfx)
            if self.t >= SHOOT_TOTAL:
                self.ranged_cd = RANGED_COOLDOWN
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == THROWN:                  # 被投出：浮空坠落，落地进硬直
            self.t += 1
            self.vx *= 0.99
            self._physics(fx)
            if self.grounded:
                if self.t >= 2 and (inp["jump"] or inp["block"]):
                    self._enter(IDLE)     # 被投落地也可受身
                    self.combo_count = 0
                    self.knockdown = False
                    self.wake_invuln = WAKE_INVULN
                else:
                    self._enter(HURT)
                    self._stun_extra = THROWN_LAND_STUN
                    self.knockdown = True   # 倒地：渲染躺地帧，可快速起身
                    fx.dust(self.x, GROUND_Y, n=6)
                    fx.shake(4)
                    sfx.play("hit")
            return

        if st == THROW:                   # 投技出招（抓取判定在 Fight._combat）
            self.t += 1
            self.vx *= 0.8
            if self.t >= THROW_TOTAL + self.tech_stun:   # 被拆投附加硬直
                self.throw_cd = THROW_COOLDOWN
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == DASH:                    # 前冲：第 4 帧起可取消出攻击
            self.t += 1
            self.anim_t += 1
            self.vx = self.facing * DASH_SPEED * max(0.25, 1 - self.t / DASH_FRAMES)
            if self.t >= 4 and self.grounded:
                if "melee" in fresh:      # 冲刺轻 → 机体专属突进技
                    self._start_move(SPECIAL, "dash_light")
                    self._physics(fx)
                    return
                if "heavy" in fresh:      # 冲刺重 → 前重
                    self._start_move(HEAVY, "fwd_heavy")
                    self._physics(fx)
                    return
                if (inp["ranged"] and self.ranged_cd <= 0
                        and MOVE_DEFS[self.spec_key].get("fwd_bolt")):
                    self._start_move(SPECIAL, "fwd_bolt")
                    self._physics(fx)
                    return
                if inp["throw"] and self.throw_cd <= 0:
                    self._enter(THROW)
                    self.throw_hit_done = False
                    self._physics(fx)
                    return
                if (inp["ranged"] and self.ranged_cd <= 0
                        and self.energy >= RANGED_COST):
                    self._enter(SHOOT)
                    self._physics(fx)
                    return
            if self.t >= DASH_FRAMES:
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == BACKSTEP:                # 后撤步：中段无敌帧
            self.t += 1
            self.anim_t += 1
            if self.t < 10:
                self.vx = -self.facing * BACKSTEP_SPEED
            else:
                self.vx *= 0.75
            if self.t >= BACKSTEP_FRAMES:
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == AIR_MELEE:               # 空中下劈
            self.t += 1
            if AIR_MELEE_ACTIVE[0] <= self.t < AIR_MELEE_ACTIVE[1]:
                self.vx = self.facing * 0.4
            self._physics(fx)
            if self.grounded:
                self.melee_cd = MELEE_COOLDOWN
                fx.dust(self.x, GROUND_Y, n=3)
                self._enter(IDLE)
            elif self.t >= AIR_MELEE_TOTAL:
                self.melee_cd = MELEE_COOLDOWN
                self._enter(JUMP)
            return

        if st == HEAVY:                   # 重击系（MOVE_DEFS：站重/前重/后重）
            d = self.move
            self.t += 1
            w0, a1 = d["windup"], d["windup"] + d["active"]
            # 前摇期连按合并：重击启动后 6 帧内补按轻斩 → 冲击
            if self.t <= w0 and self._combo_convert() is not None:
                self._physics(fx)
                return
            if self.t < a1:
                if d.get("retreat"):
                    self.vx = -self.facing * 1.1   # 后重：边后撤边横扫
                else:
                    self.vx = self.facing * d.get("lunge", 0)
            else:
                self.vx = 0
            if self.grounded and self.move_did_hit and self.t >= a1:
                key = self._special_cmd()     # 重击命中取消 → 特殊技
                if key is not None:
                    self._start_move(SPECIAL, key)
                    self._physics(fx)
                    return
                if inp["super"] and self._try_super():
                    self._physics(fx)
                    return
                if self._dbl_fwd():            # 取消窗内双击前 → 绿冲
                    self._drive_rush(fx)
                    self._physics(fx)
                    return
            if self.t >= a1 + d["recover"]:
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == AIR_HEAVY:               # 空中重击（下投/急坠，读表）
            d = self.move
            self.t += 1
            self._physics(fx)
            if self.grounded:
                fx.dust(self.x, GROUND_Y, n=4)
                self._enter(IDLE)
            elif self.t >= d["windup"] + d["active"] + d["recover"]:
                self._enter(JUMP)
            return

        if st == SPECIAL:                 # 特殊技（Modern 指令技，读表）
            d = self.move
            self.t += 1
            a1 = d["windup"] + d["active"]
            if self.t < a1:               # 前摇+判定相：突进与霸体生效区
                self.vx = self.facing * d.get("rush", 0)
                self.armor_on = d.get("armor", False)
            else:
                self.vx = 0
                self.armor_on = False
            if self.bolt_shots_left > 0 and self.t >= self.bolt_next_t:
                self._fire_move_bolt(fx, sfx)
                self.bolt_shots_left -= 1
                self.bolt_next_t += d["bolt"].get("interval", 0)
            if self.grounded and self.move_did_hit and self.t >= a1:
                if inp["super"] and self._try_super():   # 特殊技命中 → 超必杀
                    self._physics(fx)
                    return
                if self._dbl_fwd():            # 取消窗内双击前 → 绿冲
                    self._drive_rush(fx)
                    self._physics(fx)
                    return
            if self.t >= a1 + d["recover"]:
                if d.get("bolt"):
                    self.ranged_cd = SPECIAL_CD   # 射击系共享冷却
                else:
                    self.melee_cd = MELEE_COOLDOWN
                self._enter(IDLE)
            self._physics(fx)
            return

        # ---- 可自由行动：IDLE / WALK / JUMP / BLOCK ----
        if self.stagger > 0:              # 被完美格挡后的踉跄
            self.stagger -= 1
            self.vx *= 0.85
            self._physics(fx)
            return

        if st == BLOCK and self.block_stun > 0:   # 受防硬直：防御中无法行动
            if self._combo_convert() is not None:  # 硬直中仍可拆招反击
                self._physics(fx)
                return
            self.block_stun -= 1
            self.vx *= 0.85
            self._physics(fx)
            return

        # Drive 冲击 / OD 强化技：攻击键快速连按合并（同按容错窗）
        if st in (IDLE, WALK, BLOCK) and self._combo_convert() is not None:
            self._physics(fx)
            return

        # 超必杀：依据方向与槽位选择 Lv1/2/3（最高优先级）
        if self.grounded and self._try_super():
            self._physics(fx)
            return

        # 双击方向 → 前冲 / 后撤步（仅地面自由态）
        if (self.grounded and st in (IDLE, WALK)
                and (("left" in fresh) ^ ("right" in fresh))):
            dirn = -1 if "left" in fresh else 1
            last = self._prev_taps.get(dirn)
            if last is not None and self.age - last <= TAP_WINDOW:
                self._prev_taps[dirn] = None
                forward = 1 if opponent.x >= self.x else -1
                if dirn == forward:
                    if self.parry_rush > 0:       # 完美格挡后：免费绿冲
                        self._drive_rush(fx, free=True)
                    else:
                        self._enter(DASH)
                else:
                    self._enter(BACKSTEP)
                fx.dust(self.x, self.y, n=4)
                self._physics(fx)
                return
            self._tap_age[dirn] = self.age

        if inp["block"] and self.grounded:
            if st != BLOCK:
                self._enter(BLOCK)
            self.vx = 0
            fwd_held = (self.facing == 1 and inp["right"]) or \
                       (self.facing == -1 and inp["left"])
            if (fwd_held and "heavy" in fresh
                    and self.drive >= DRIVE_REVERSAL_COST):
                # 逆转反技：防御中 前方向+重，耗 2 格 Drive
                self.drive -= DRIVE_REVERSAL_COST
                self._start_move(DREVERSAL, "reversal", d=REVERSAL_DEF)
        elif "heavy" in fresh and self.grounded:
            # 重击三变体：方向+重 = 前重（贴脸突进）/ 后重（对空/扫击）
            fwd = (self.facing == 1 and inp["right"]) or \
                  (self.facing == -1 and inp["left"])
            back = (self.facing == 1 and inp["left"]) or \
                   (self.facing == -1 and inp["right"])
            if fwd:
                self._start_move(HEAVY, "fwd_heavy")
            elif back:
                self._start_move(HEAVY, "back_heavy")
            else:
                self._start_move(HEAVY, "heavy")
        elif inp["melee"] and self.grounded and self.melee_cd <= 0:
            self._enter(MELEE)
            self.melee_did_hit = False
        elif inp["throw"] and self.grounded and self.throw_cd <= 0:
            self._enter(THROW)
            self.throw_hit_done = False
        elif inp["ranged"] and self.grounded and self.ranged_cd <= 0:
            key = self._special_cmd()     # 方向+光束 = 特殊技
            if key is not None:
                self._start_move(SPECIAL, key)
            elif self.energy >= RANGED_COST:
                self._enter(SHOOT)
        elif inp["jump"] and self.grounded:
            self.vy = -self.spec["jump_power"]
            self.vx *= JUMP_BOOST            # 起跳动量：保留并放大水平速度
            self.y -= 0.1
            fx.dust(self.x, self.y, n=5)
            sfx.play("jump")
            self._enter(JUMP)
        elif (inp["left"] or inp["right"]) and self.grounded:
            direction = -1 if inp["left"] else 1
            self.vx = direction * self.spec["walk_speed"]
            if st != WALK:
                self._enter(WALK)
            self.anim_t += 1
            if self.anim_t % 14 == 0:
                fx.dust(self.x - self.facing * 8, self.y, n=1)
        elif self.grounded:
            if st != IDLE:
                self._enter(IDLE)
            self.vx *= 0.6
            self.anim_t += 1
        else:
            # 空中
            self.anim_t += 1
            if ("jump" in fresh
                    and self.air_jumps_used < self.spec.get("air_jumps", 0)):
                # 专属机动：空中二段跳（VERDANT）
                self.vy = -self.spec["jump_power"] * 0.92
                self.air_jumps_used += 1
                fx.dust(self.x, self.y, n=4)
                sfx.play("jump")
            elif inp["melee"] and self.melee_cd <= 0:
                self._enter(AIR_MELEE)          # 空中下劈
                self.melee_did_hit = False
            elif "heavy" in fresh:
                self._start_move(AIR_HEAVY, "air_heavy")   # 空中重击
            elif (inp["ranged"] and self.ranged_cd <= 0
                  and self.energy >= RANGED_COST):
                self._enter(SHOOT)              # 空中射击
            elif inp["left"]:
                air_cap = self.spec["walk_speed"] * JUMP_BOOST
                self.vx = max(self.vx - 0.12, -air_cap)
            elif inp["right"]:
                air_cap = self.spec["walk_speed"] * JUMP_BOOST
                self.vx = min(self.vx + 0.12, air_cap)

        self._physics(fx)

    def _physics(self, fx):
        self.x += self.vx
        if not self.grounded or self.vy < 0:
            self.vy += GRAVITY
            self.y += self.vy
            if self.y >= GROUND_Y:
                if self.vy > 2.0:
                    fx.dust(self.x, GROUND_Y, n=4)
                self.y = GROUND_Y
                self.vy = 0.0
                self.air_jumps_used = 0    # 落地恢复空中跳跃次数
                if self.state == JUMP:
                    self._enter(IDLE)
        self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))

    def _enter(self, state):
        self.state = state
        self.t = 0
        self.anim_t = 0
        if state == IDLE:
            self.knockdown = False       # 起身不再呈倒地
        if state == THROW:
            self.tech_stun = 0           # 新投技不带拆投硬直
        if state == MELEE:
            self.melee_did_hit = False
            self.melee_blocked = False
            self.chain_count = 0

    # ------------------------------------------------ 攻击
    def _fire(self, fx, sfx):
        self.energy -= RANGED_COST
        mx, my = self.muzzle_pos()
        # 空中射击弹道斜向下：下坠分量在 effects.spawn_bolt 中按高度计算
        fx.spawn_bolt(self, mx, my)
        fx.muzzle_flash(mx, my, self.facing)
        self.flash = max(self.flash, 0)  # 射击不闪白
        sfx.play("shoot")

    def _fire_pierce_shot(self, fx, sfx):
        """AZURE 系贯穿激光：全屏直线穿透，命中后继续飞行。"""
        mx, my = self.muzzle_pos()
        dmg = self.spec["super_levels"][self.super_level]["dmg"]
        fx.spawn_pierce_bolt(self, mx, my, dmg)
        fx.muzzle_flash(mx, my, self.facing)
        fx.shake(4)
        sfx.play("shoot")

    def _fire_home_shot(self, opponent, fx, sfx):
        """VIOLET 系追踪电弹：弹道逐帧向对手转向。"""
        lv = self.spec["super_levels"][self.super_level]
        mx, my = self.muzzle_pos()
        fx.spawn_home_bolt(self, mx, my, lv["shots"].index(self.t),
                           lv["dmg"], opponent)
        fx.muzzle_flash(mx, my, self.facing)
        fx.shake(2)
        sfx.play("shoot")

    def _fire_rain(self, opponent, fx, sfx):
        """VERDANT Lv3 天降轰炸：落点环绕对手当前位置，从屏幕上方砸落。"""
        lv = self.spec["super_levels"][self.super_level]
        idx = lv["shots"].index(self.t)
        offs = (-6, 6, -14, 14, -26, 26)   # 内侧落点保底直击，外侧覆盖走位
        x = max(ARENA_LEFT + 10, min(ARENA_RIGHT - 10,
                                     opponent.x + offs[idx % len(offs)]))
        fx.spawn_rain_bolt(self, x, lv["dmg"])
        fx.shake(2)
        sfx.play("shoot")

    def _fire_super_arc(self, opponent, fx, sfx):
        """VERDANT 系超必杀：弧线榴弹，按对手当前位置解算落点。"""
        lv = self.spec["super_levels"][self.super_level]
        idx = lv["shots"].index(self.t)
        dx = opponent.x - self.x
        vx = max(-4.2, min(4.2, dx / 48.0)) + (idx * 2 - 1) * 0.30
        sx, sy = self.x + self.facing * 6, self.y - 58
        fx.spawn_arc_bolt(self, sx, sy, vx, VERDANT_SUPER_VY, lv["dmg"])
        fx.muzzle_flash(sx, sy, self.facing)
        fx.shake(3)
        sfx.play("shoot")

    def _fire_wave(self, fx):
        """GARNET Lv2「地裂冲击」：命中后贴地冲击波二段。"""
        sx, sy = self.x + self.facing * 30, GROUND_Y - 10
        fx.spawn_arc_bolt(self, sx, sy, self.facing * 2.2, 0.0, 12)
        fx.shake(4)

    def take_damage(self, dmg, from_dir, fx, sfx, heavy=False,
                    unblockable=False, launch=False, punish=False,
                    guard_mult=1.0):
        """from_dir: 击退方向（+1 向右）。返回 'hit' / 'blocked' / 'parried' /
        'armor' / 'break' / 'ko' / None。

        unblockable: 无视格挡（投技）；launch: 击飞浮空（被投）；
        punish: 惩罚反击（×1.2 + 地面强制击倒 + 附加硬直 + PUNISH 弹字）；
        guard_mult: 被防时对防御槽的伤害倍率（前重特长）；
        无敌帧期间直接返回 None（攻击穿透，不消耗攻击方判定）。
        命中伤害按受击方 combo_count 统一衰减（被防/受身/超时重置）。
        """
        if not self.alive:
            return None
        if self.invuln:
            return None
        if self.knockdown:                # 倒地（躺地帧）：攻击穿透，留起身机会
            return None                   #   否则会被无限压起身连打、硬直反复刷新

        if self.armor_on and not unblockable:
            # 霸体：吃半伤不中断动作（返回 'armor'，攻击方判定照常消耗）
            half = max(1, dmg // 2)
            self.hp = max(0, self.hp - half)
            fx.damage_number(self.x, self.y - 62, half)
            fx.sparks(self.x, self.y - 34, from_dir, hot=False, n=4)
            sfx.play("block")
            if self.hp <= 0:
                self.state = KO
                self.t = 0
                self.vy = -3.4
                self.vx = from_dir * 2.4
                fx.ko_burst(self.x, self.y - 30)
                return "ko"
            return "armor"

        if self.state == BLOCK and not unblockable:
            if self.parry_window > 0:                    # 完美格挡：弹开
                self.parry_window = 0
                self.parry_rush = PARRY_RUSH_WINDOW      # 免费绿冲窗口
                self.drive = min(DRIVE_MAX, self.drive + DRIVE_PARRY_GAIN)
                fx.block_spark(self.x + self.facing * 14, self.y - 34)
                fx.callout(self.x, self.y - 74, "PERFECT", (120, 230, 255))
                sfx.play("block")
                return "parried"
            real = max(1, round(dmg * BLOCK_REDUCE))     # 格挡削血（chip）
            self.hp = max(0, self.hp - real)
            self.guard -= (GUARD_GAIN_MELEE * guard_mult if heavy
                           else GUARD_GAIN_BOLT)
            self.drive = max(0, self.drive - DRIVE_BLOCK_LOSS)
            self.block_stun = BLOCK_STUN                 # 受防硬直
            self.vx = from_dir * BLOCK_PUSH
            self.combo_count = 0                         # 被防重置连段
            self.combo_timer = 0
            fx.block_spark(self.x + self.facing * 14, self.y - 34)
            fx.damage_number(self.x, self.y - 62, real, blocked=True)
            sfx.play("block")
            if self.guard <= 0:              # GUARD BREAK：防御崩坏
                self.guard = 0
                self.block_stun = 0
                self.gb_stun = GUARD_BREAK_STUN
                self.state = GBREAK
                self.t = 0
                fx.shake(6)
                sfx.play("break")
                return "break"
            return "blocked"

        if punish:
            dmg = max(1, round(dmg * PUNISH_MULT))
            if self.grounded:
                launch = True               # 强制击倒（浮空坠落→落地硬直）
        dmg = max(1, round(dmg * combo_scale(self.combo_count)))
        self.combo_count += 1
        self.combo_timer = 0

        self.hp = max(0, self.hp - dmg)
        self.flash = 5
        self.block_stun = 0
        self.drive = max(0, self.drive - DRIVE_HIT_LOSS)
        self.vx = from_dir * self.spec["knockback"] * (1.0 if heavy else 0.7)
        fx.damage_number(self.x, self.y - 62, dmg)
        fx.sparks(self.x + from_dir * -8, self.y - 34, from_dir,
                  hot=heavy, n=10 if heavy else 6)
        sfx.play("hit")
        if punish:
            fx.callout(self.x, self.y - 74, "PUNISH")
        if self.hp <= 0:
            self.state = KO
            self.t = 0
            self.vy = -3.4
            self.vx = from_dir * 2.4
            fx.ko_burst(self.x, self.y - 30)
            return "ko"
        if launch:                       # 被投飞/超必杀击飞/惩罚击倒：浮空坠落
            self.state = THROWN
            self.t = 0
            self._stun_extra = 0
            self._air_hurt = True
            self._ground_t = 0
            self.vy = THROW_VY
            # 技能击倒就近倒地（便于压制），投技/超必杀保留全距离击飞
            scale = 1.0 if unblockable else LAUNCH_VX_SCALE
            self.vx = from_dir * THROW_VX * scale
            fx.throw_impact(self.x, self.y - 30)
            return "hit"
        self.state = HURT
        self.t = 0
        self._stun_extra = (6 if heavy else 0) + (PUNISH_STUN_BONUS if punish
                                                  else 0)
        self._air_hurt = not self.grounded
        self._ground_t = 0
        if not self.grounded:            # 空中追打（juggle）：向上刷新浮空
            self.vy = JUGGLE_VY
            self.vx = from_dir * self.spec["knockback"] * 0.5
        return "hit"

    # ------------------------------------------------ 绘制
    def current_frame_name(self):
        st = self.state
        if st == MELEE:
            if self.t < MELEE_WINDUP:
                return "atk0"
            if self.t < MELEE_WINDUP + MELEE_ACTIVE:
                return "atk1"
            return "atk2"
        if st == THROW:
            if self.t < THROW_HIT_T:
                return "atk0"
            if self.t < THROW_HIT_T + 10:
                return "atk1"
            return "atk2"
        if st == AIR_MELEE:
            return "atk1" if self.t < AIR_MELEE_ACTIVE[1] else "atk2"
        if st == DIMPACT:                 # 冲击：蓄力/出手/收招
            if self.dim_t0 is None:
                return "atk0"
            return "atk1" if self.t < self.dim_t0 + 6 else "atk2"
        if st in (HEAVY, AIR_HEAVY, SPECIAL, DREVERSAL):
            # MOVE_DEFS 驱动：按相位取帧（anim 三元组指定各相位专属动作）
            d = self.move or {}
            w0 = d.get("windup", 9)
            a1 = w0 + d.get("active", 5)
            anim = d.get("anim")
            if anim:
                if self.t < w0:
                    return anim[0]
                return anim[1] if self.t < a1 else anim[2]
            if self.t < w0:
                return "atk0"
            if self.t < a1:
                return "atk1"
            return "atk2"
        if st == SHOOT:
            return "shoot"
        if st == SUPER:
            lv = self.spec["super_levels"][self.super_level]
            if "active" in lv:            # 冲撞型：蓄势→突进→收招
                a0, a1 = lv["active"]
                if a0 <= self.t < a1:
                    return "atk1"
                return "atk0" if self.t < a0 else "atk2"
            if "dashes" in lv:            # 瞬步乱舞：瞬步窗呈斩击姿态
                for s0, s1 in lv["dashes"]:
                    if s0 <= self.t < s1:
                        return "atk1"
                return "atk0"
            first = lv["shots"][0]
            if lv.get("pierce"):
                return "shoot"            # 举炮瞄准全程（狙击手感）
            if lv.get("arc") or lv.get("rain"):
                return "atk0" if self.t < first else "shoot"  # 装填投掷→发射
            return "shoot" if self.t >= first else "atk0"
        if st == HURT and self.knockdown:
            return "ko"                   # 击倒：躺地帧（可受身起身）
        if st == GBREAK:
            return "hurt"
        seq = ANIMS[st]
        # 帧循环
        total = sum(d for _, d in seq)
        pos = self.anim_t % total
        for nm, d in seq:
            if pos < d:
                return nm
            pos -= d
        return seq[0][0]

    def draw_pose(self, t):
        """当前姿态 (帧图, x偏移, y偏移)——draw() 与运动签名残影快照同源。"""
        name = self.current_frame_name()
        key = f"flash{self.facing}" if self.flash > 0 else self.facing
        img = self.frames[self.palette][name][key]

        x_off = int(self.x) - int(ANCHOR_FX * PIX)
        if self.facing == -1:
            x_off = int(self.x) - (SPRITE_W - int(ANCHOR_FX * PIX))
        y_off = int(self.y) - SPRITE_H

        # 待机/射击呼吸与后坐微动
        if self.state == IDLE and (t // 18) % 2 == 0:
            y_off += PIX
        if self.state == SHOOT and self.t >= SHOOT_FIRE_T:
            x_off -= self.facing * PIX
        return img, x_off, y_off

    def draw(self, surf, t):
        img, x_off, y_off = self.draw_pose(t)
        surf.blit(img, (x_off, y_off))

        # 防御能量护盾弧
        if self.state == BLOCK:
            self._draw_shield(surf, t)

    def _draw_shield(self, surf, t):
        pulse = 150 + int(60 * ((t // 4) % 2))
        w, h = 14, 40
        shield = pygame.Surface((w, h), pygame.SRCALPHA)
        col = COLORS["spark_cool"] if self.palette == "p1" else COLORS["spark_hot"]
        pygame.draw.ellipse(shield, (*col, pulse), (0, 0, w, h), 2)
        pygame.draw.ellipse(shield, (*col, pulse // 2), (2, 3, w - 4, h - 6), 1)
        sx = self.x + self.facing * 16 - (0 if self.facing == 1 else w)
        surf.blit(shield, (int(sx), int(self.y) - h - 12))
