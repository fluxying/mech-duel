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
                      GARNET_SUPER_ACTIVE, AZURE_SUPER_SHOTS,
                      AZURE_SUPER_BOLT_SPEED,
                      GUARD_MAX, GUARD_REGEN, GUARD_GAIN_MELEE, GUARD_GAIN_BOLT,
                      GUARD_BREAK_STUN, JUMP_BOOST)
from assets import SPRITE_W, SPRITE_H, ANCHOR_FX, PIX

IDLE, WALK, JUMP, MELEE, SHOOT, BLOCK, HURT, KO = (
    "idle", "walk", "jump", "melee", "shoot", "block", "hurt", "ko")
THROW, DASH, BACKSTEP, AIR_MELEE, THROWN = (
    "throw", "dash", "backstep", "air_melee", "thrown")
SUPER, GBREAK = "super", "guard_break"

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
        self.state = IDLE
        self.t = 0                # 状态内计时
        self.anim_t = 0
        self.flash = 0            # 受击白闪剩余帧
        self._stun_extra = 0      # 受击附加硬直
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
        self.input = {k: False for k in
                      ("left", "right", "jump", "block", "melee", "ranged",
                       "throw", "super")}

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
        """GARNET 超必杀冲撞判定盒（AZURE 为射击型，无近身判定）。"""
        if self.state != SUPER or self.spec_key != "garnet":
            return None
        if not (GARNET_SUPER_ACTIVE[0] <= self.t < GARNET_SUPER_ACTIVE[1]):
            return None
        f = self.facing
        x0 = self.x + f * 4
        x1 = self.x + f * 66
        left, right = sorted((x0, x1))
        return pygame.Rect(int(left), int(self.y) - 56, int(right - left), 56)

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
        if self.state != BLOCK:
            self.guard = min(GUARD_MAX, self.guard + GUARD_REGEN)  # 防御槽回复
        self.energy = min(ENERGY_MAX, self.energy + ENERGY_REGEN)

        inp = self.input
        st = self.state
        # 新按下检测（供双击冲刺用），随后快照本帧输入
        fresh = {k for k, v in inp.items() if v and not self._prev_input.get(k)}
        self._prev_input = dict(inp)

        # 面向对手（动作进行中锁定朝向）
        if st not in (MELEE, SHOOT, THROW, DASH, BACKSTEP, AIR_MELEE, THROWN,
                      SUPER, GBREAK, KO):
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

        if st == GBREAK:                  # 防御崩坏：大硬直，无法防御
            self.t += 1
            self.vx *= 0.85
            if self.t >= GUARD_BREAK_STUN and self.grounded:
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == SUPER:                   # 超必杀（发动演出由 Fight 处理）
            self.t += 1
            if self.spec_key == "garnet":
                # 熔核冲击：判定相高速突进
                self.vx = (self.facing * 6.0
                           if GARNET_SUPER_ACTIVE[0] <= self.t < GARNET_SUPER_ACTIVE[1]
                           else 0)
            else:
                self.vx = 0
                if self.t in AZURE_SUPER_SHOTS:
                    self._fire_super_shot(fx, sfx)
            if self.t >= SUPER_TOTAL:
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == MELEE:
            self.t += 1
            # 判定相小幅突进
            if MELEE_WINDUP <= self.t < MELEE_WINDUP + MELEE_ACTIVE:
                self.vx = self.facing * 0.9
            else:
                self.vx = 0
            # 命中取消：命中后的后摇期可接光束/投技/跳跃（连段核心）
            if (self.melee_did_hit and self.grounded
                    and MELEE_WINDUP <= self.t < MELEE_TOTAL):
                if (inp["ranged"] and self.ranged_cd <= 0
                        and self.energy >= RANGED_COST):
                    self._enter(SHOOT)
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
                    self.wake_invuln = WAKE_INVULN
                else:
                    self._enter(HURT)
                    self._stun_extra = THROWN_LAND_STUN
                    fx.dust(self.x, GROUND_Y, n=6)
                    fx.shake(4)
                    sfx.play("hit")
            return

        if st == THROW:                   # 投技出招（抓取判定在 Fight._combat）
            self.t += 1
            self.vx *= 0.8
            if self.t >= THROW_TOTAL:
                self.throw_cd = THROW_COOLDOWN
                self._enter(IDLE)
            self._physics(fx)
            return

        if st == DASH:                    # 前冲：第 4 帧起可取消出攻击
            self.t += 1
            self.anim_t += 1
            self.vx = self.facing * DASH_SPEED * max(0.25, 1 - self.t / DASH_FRAMES)
            if self.t >= 4 and self.grounded:
                if inp["melee"] and self.melee_cd <= 0:
                    self._enter(MELEE)
                    self.melee_did_hit = False
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

        # ---- 可自由行动：IDLE / WALK / JUMP / BLOCK ----
        # 超必杀：槽满 + 专用键（最高优先级），发动即清空槽位
        if (inp["super"] and self.grounded and self.super >= SUPER_MAX):
            self.super = 0
            self._enter(SUPER)
            self.super_did_hit = False
            self.super_pending = True    # 通知 Fight 播放发动演出
            self._physics(fx)
            return

        # 双击方向 → 前冲 / 后撤步（仅地面自由态）
        if (self.grounded and st in (IDLE, WALK)
                and (("left" in fresh) ^ ("right" in fresh))):
            dirn = -1 if "left" in fresh else 1
            last = self._tap_age.get(dirn)
            if last is not None and self.age - last <= TAP_WINDOW:
                self._tap_age[dirn] = None
                forward = 1 if opponent.x >= self.x else -1
                if dirn == forward:
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
        elif inp["melee"] and self.grounded and self.melee_cd <= 0:
            self._enter(MELEE)
            self.melee_did_hit = False
        elif inp["throw"] and self.grounded and self.throw_cd <= 0:
            self._enter(THROW)
            self.throw_hit_done = False
        elif (inp["ranged"] and self.grounded and self.ranged_cd <= 0
              and self.energy >= RANGED_COST):
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
            if inp["melee"] and self.melee_cd <= 0:
                self._enter(AIR_MELEE)          # 空中下劈
                self.melee_did_hit = False
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
                if self.state == JUMP:
                    self._enter(IDLE)
        self.x = max(ARENA_LEFT, min(ARENA_RIGHT, self.x))

    def _enter(self, state):
        self.state = state
        self.t = 0
        self.anim_t = 0

    # ------------------------------------------------ 攻击
    def _fire(self, fx, sfx):
        self.energy -= RANGED_COST
        mx, my = self.muzzle_pos()
        # 空中射击弹道斜向下：下坠分量在 effects.spawn_bolt 中按高度计算
        fx.spawn_bolt(self, mx, my)
        fx.muzzle_flash(mx, my, self.facing)
        self.flash = max(self.flash, 0)  # 射击不闪白
        sfx.play("shoot")

    def _fire_super_shot(self, fx, sfx):
        """AZURE 超必杀「苍蓝齐射」：三连强化光束之一。"""
        idx = AZURE_SUPER_SHOTS.index(self.t)
        mx, my = self.muzzle_pos()
        fx.spawn_super_bolt(self, mx, my, idx)
        fx.muzzle_flash(mx, my, self.facing)
        fx.shake(4)
        sfx.play("shoot")

    def take_damage(self, dmg, from_dir, fx, sfx, heavy=False,
                    unblockable=False, launch=False):
        """from_dir: 击退方向（+1 向右）。返回 'hit' / 'blocked' / 'break' / 'ko' / None。

        unblockable: 无视格挡（投技）；launch: 击飞浮空（被投）；
        无敌帧期间直接返回 None（攻击穿透，不消耗攻击方判定）。
        """
        if not self.alive:
            return None
        if self.invuln:
            return None

        if self.state == BLOCK and not unblockable:
            real = max(1, round(dmg * BLOCK_REDUCE))     # 格挡削血（chip）
            self.hp = max(0, self.hp - real)
            self.guard -= GUARD_GAIN_MELEE if heavy else GUARD_GAIN_BOLT
            self.vx = from_dir * 1.3
            fx.block_spark(self.x + self.facing * 14, self.y - 34)
            fx.damage_number(self.x, self.y - 62, real, blocked=True)
            sfx.play("block")
            if self.guard <= 0:              # GUARD BREAK：防御崩坏
                self.guard = 0
                self.state = GBREAK
                self.t = 0
                fx.shake(6)
                sfx.play("break")
                return "break"
            return "blocked"

        self.hp = max(0, self.hp - dmg)
        self.flash = 5
        self.vx = from_dir * self.spec["knockback"] * (1.0 if heavy else 0.7)
        fx.damage_number(self.x, self.y - 62, dmg)
        fx.sparks(self.x + from_dir * -8, self.y - 34, from_dir,
                  hot=heavy, n=10 if heavy else 6)
        sfx.play("hit")
        if self.hp <= 0:
            self.state = KO
            self.t = 0
            self.vy = -3.4
            self.vx = from_dir * 2.4
            fx.ko_burst(self.x, self.y - 30)
            return "ko"
        if launch:                       # 被投飞/超必杀击飞：浮空坠落
            self.state = THROWN
            self.t = 0
            self._stun_extra = 0
            self._air_hurt = True
            self._ground_t = 0
            self.vy = THROW_VY
            self.vx = from_dir * THROW_VX
            fx.throw_impact(self.x, self.y - 30)
            return "hit"
        self.state = HURT
        self.t = 0
        self._stun_extra = 6 if heavy else 0
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
        if st == SHOOT:
            return "shoot"
        if st == SUPER:
            if self.spec_key == "garnet":
                if GARNET_SUPER_ACTIVE[0] <= self.t < GARNET_SUPER_ACTIVE[1]:
                    return "atk1"
                return "atk0" if self.t < GARNET_SUPER_ACTIVE[0] else "atk2"
            return "shoot" if self.t >= AZURE_SUPER_SHOTS[0] else "atk0"
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

    def draw(self, surf, t):
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
