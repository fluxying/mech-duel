# -*- coding: utf-8 -*-
"""战斗特效：光束弹、粒子（火花/尘土/硝烟）、浮动伤害数字、斩击弧光、屏幕震动。"""

import math
import random

import pygame

from settings import (RANGED_DAMAGE, RANGED_SPEED, ARENA_LEFT, ARENA_RIGHT,
                      INTERNAL_W, COLORS, GROUND_Y,
                      AZURE_SUPER_BOLT_DMG, AZURE_SUPER_BOLT_SPEED,
                      VERDANT_SUPER_GRAV)
from assets import build_bolts

RNG = random.Random(20260829)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "color", "grav", "size")

    def __init__(self, x, y, vx, vy, life, color, grav=0.0, size=1):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = self.max_life = life
        self.color = color
        self.grav = grav
        self.size = size

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.grav
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0:
            return
        fade = self.life / self.max_life
        col = tuple(int(c * (0.4 + 0.6 * fade)) for c in self.color)
        s = self.size
        surf.fill(col, (int(self.x), int(self.y), s, s))


class Projectile:
    """光束弹。owner 为发射者，命中其对手。"""

    def __init__(self, owner, x, y, bolts, big=False, vx=None, vy=None,
                 grav=0.0, dmg=None):
        self.owner = owner
        self.x = x
        self.y = y
        self.facing = owner.facing
        self.vx = owner.facing * RANGED_SPEED if vx is None else vx
        self.vy = 0.0 if vy is None else vy
        self.grav = grav              # >0 时为弧线弹道（VERDANT 榴弹）
        self.dmg = RANGED_DAMAGE if dmg is None else dmg
        self.t = 0
        self.dead = False
        self.big = big                 # 超必杀强化弹：判定与外形放大
        self.sprites = bolts[owner.spec["bolt_color"]]

    def update(self, fx):
        self.vy += self.grav
        self.x += self.vx
        self.y += self.vy
        self.t += 1
        if self.grav and self.y >= GROUND_Y:   # 弧线榴弹落地爆散
            fx.dust(self.x, GROUND_Y, n=7)
            fx.sparks(self.x, GROUND_Y - 4, 1 if self.vx >= 0 else -1,
                      hot=True, n=8)
            self.dead = True
            return
        if self.t % 2 == 0:
            fx.particles.append(Particle(
                self.x - self.facing * 5, self.y + RNG.randint(-1, 1),
                -self.facing * 0.4, RNG.uniform(-0.2, 0.2),
                10, self._trail_color(), 0, 1))
        if self.x < ARENA_LEFT - 30 or self.x > ARENA_RIGHT + 30:
            self.dead = True

    def _trail_color(self):
        pal = {"hot": COLORS["spark_hot"], "cool": COLORS["spark_cool"]}
        return pal["hot"] if self.owner.spec["bolt_color"] == "hot" else pal["cool"]

    def rect(self):
        if self.big:
            return pygame.Rect(int(self.x) - 9, int(self.y) - 4, 18, 8)
        return pygame.Rect(int(self.x) - 5, int(self.y) - 2, 10, 5)

    def draw(self, surf):
        img = self.sprites[(self.t // 3) % 2][self.facing]
        if self.big:
            img = pygame.transform.scale(
                img, (img.get_width() * 2, img.get_height() * 2))
            surf.blit(img, (int(self.x) - img.get_width() // 2,
                            int(self.y) - img.get_height() // 2))
        else:
            surf.blit(img, (int(self.x) - 10, int(self.y) - 5))


class Slash:
    """近战弧光：判定相展开的扇形残影。"""

    def __init__(self, mech):
        self.mech = mech
        self.t = 0
        self.life = 6

    def update(self):
        self.t += 1

    @property
    def dead(self):
        return self.t >= self.life

    def draw(self, surf):
        m = self.mech
        cx = m.x + m.facing * 12
        cy = m.y - 34
        prog = self.t / self.life
        r = 20 + 16 * prog
        w = max(1, int(3 * (1 - prog)))
        col = (255, 240, 200) if self.t < 3 else (255, 190, 110)
        if m.facing == 1:
            start, end = -75, 55
        else:
            start, end = 125, 255
        steps = 8
        for i in range(steps):
            a0 = start + (end - start) * i / steps - (end - start) * prog * 0.35
            a1 = a0 + (end - start) / steps
            pygame.draw.arc(surf, col,
                            (int(cx - r), int(cy - r), int(r * 2), int(r * 2)),
                            math.radians(a0), math.radians(a1), w)


class DamageNumber:
    def __init__(self, x, y, val, blocked=False):
        self.x = x + RNG.uniform(-3, 3)
        self.y = y
        self.val = val
        self.blocked = blocked
        self.life = 38
        self.font = None   # 延迟获取（pygame.font 就绪后）

    def update(self):
        self.y -= 0.7
        self.life -= 1

    @property
    def dead(self):
        return self.life <= 0

    def draw(self, surf, font):
        col = (170, 190, 210) if self.blocked else (255, 236, 160)
        txt = f"-{self.val}" if not self.blocked else f"-{self.val}"
        img = font.render(txt, True, col)
        shadow = font.render(txt, True, (20, 16, 28))
        p = (int(self.x - img.get_width() / 2), int(self.y))
        surf.blit(shadow, (p[0] + 1, p[1] + 1))
        surf.blit(img, p)


class Fx:
    """特效管理器：所有世界空间特效 + 屏幕震动。"""

    def __init__(self):
        self.particles = []
        self.bolts = []
        self.slashes = []
        self.dmg_numbers = []
        self.bolt_sprites = build_bolts()
        self.shake_mag = 0.0
        self.flash_a = 0.0             # 全屏白闪强度（超必杀演出）
        self._font = None

    def clear(self):
        """回合重置时清空所有瞬态特效。"""
        self.particles.clear()
        self.bolts.clear()
        self.slashes.clear()
        self.dmg_numbers.clear()
        self.shake_mag = 0
        self.flash_a = 0

    # ---------------- 生成接口 ----------------
    def spawn_bolt(self, mech, x, y):
        b = Projectile(mech, x, y, self.bolt_sprites)
        if not mech.grounded:
            # 空中射击：弹道斜向下。下坠分量按「炮口到目标头顶线」的高度差算，
            # 大致在 ~84px（20×弹速）的水平飞行距离内落到目标头顶线
            b.vy = min(2.4, max(0.3, (GROUND_Y - 52 - y) / 20))
        self.bolts.append(b)

    def spawn_super_bolt(self, mech, x, y, idx=0):
        """AZURE 超必杀强化光束：放大判定，三发速度递增。"""
        b = Projectile(mech, x, y, self.bolt_sprites, big=True)
        b.dmg = AZURE_SUPER_BOLT_DMG
        b.vx = mech.facing * (AZURE_SUPER_BOLT_SPEED + idx * 0.35)
        self.bolts.append(b)

    def spawn_arc_bolt(self, mech, x, y, vx, vy, dmg):
        """VERDANT 弧线榴弹：受重力下坠、落地爆散，可越过站立的对手从头顶砸落。"""
        b = Projectile(mech, x, y, self.bolt_sprites, big=True,
                       vx=vx, vy=vy, grav=VERDANT_SUPER_GRAV, dmg=dmg)
        self.bolts.append(b)

    def flash(self, alpha):
        """全屏白闪（超必杀发动演出）。"""
        self.flash_a = max(self.flash_a, alpha)

    def muzzle_flash(self, x, y, facing):
        for _ in range(6):
            self.particles.append(Particle(
                x, y, facing * RNG.uniform(0.5, 2.2), RNG.uniform(-0.8, 0.8),
                8, RNG.choice([(255, 240, 180), (255, 200, 90), (255, 150, 60)]),
                0, 1))

    def sparks(self, x, y, direction, hot=True, n=8):
        base = COLORS["spark_hot"] if hot else COLORS["spark_cool"]
        for _ in range(n):
            a = RNG.uniform(-1.2, 1.2)
            sp = RNG.uniform(1.0, 3.2)
            self.particles.append(Particle(
                x, y, direction * abs(math.cos(a)) * sp, math.sin(a) * sp - 1.0,
                RNG.randint(10, 22), base if RNG.random() < 0.7 else (255, 245, 220),
                0.12, 1))
        self.shake(3 if hot else 2)

    def block_spark(self, x, y):
        col = COLORS["spark_cool"]
        for _ in range(8):
            a = RNG.uniform(0, math.tau)
            self.particles.append(Particle(
                x, y, math.cos(a) * RNG.uniform(0.5, 1.8),
                math.sin(a) * RNG.uniform(0.5, 1.8) - 0.5,
                RNG.randint(8, 16), col if RNG.random() < 0.8 else (240, 250, 255),
                0.05, 1))

    def dust(self, x, y, n=3):
        for _ in range(n):
            self.particles.append(Particle(
                x + RNG.uniform(-6, 6), y - RNG.randint(0, 2),
                RNG.uniform(-0.5, 0.5), RNG.uniform(-0.9, -0.2),
                RNG.randint(10, 20), COLORS["dust"], -0.01, 1))

    def ko_burst(self, x, y):
        for _ in range(26):
            a = RNG.uniform(0, math.tau)
            sp = RNG.uniform(0.8, 3.6)
            col = RNG.choice([(255, 120, 60), (255, 210, 90), (200, 200, 210)])
            self.particles.append(Particle(
                x, y, math.cos(a) * sp, math.sin(a) * sp - 1.2,
                RNG.randint(14, 34), col, 0.08, 1 if RNG.random() < 0.7 else 2))
        for _ in range(8):   # 上升硝烟
            self.particles.append(Particle(
                x + RNG.uniform(-10, 10), y + RNG.uniform(-6, 6),
                RNG.uniform(-0.2, 0.2), RNG.uniform(-0.7, -0.3),
                RNG.randint(30, 55), COLORS["smoke"], -0.008, 2))
        self.shake(7)

    def damage_number(self, x, y, val, blocked=False):
        self.dmg_numbers.append(DamageNumber(x, y, val, blocked))

    def slash(self, mech):
        self.slashes.append(Slash(mech))

    def throw_impact(self, x, y):
        """投技命中：重火花 + 落地尘 + 大震动。"""
        self.sparks(x, y, 1, hot=True, n=14)
        self.dust(x, y + 26, n=6)
        self.shake(5)

    def shake(self, mag):
        self.shake_mag = max(self.shake_mag, mag)

    # ---------------- 更新与绘制 ----------------
    def update(self, frozen=False):
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.life > 0]
        for b in self.bolts:
            b.update(self)
        self.bolts = [b for b in self.bolts if not b.dead]
        for s in self.slashes:
            s.update()
        self.slashes = [s for s in self.slashes if not s.dead]
        for d in self.dmg_numbers:
            d.update()
        self.dmg_numbers = [d for d in self.dmg_numbers if not d.dead]
        self.shake_mag *= 0.82
        if self.shake_mag < 0.3:
            self.shake_mag = 0
        if not frozen:                    # 定格演出期间白闪保持
            self.flash_a *= 0.86
            if self.flash_a < 2:
                self.flash_a = 0

    def shake_offset(self):
        if self.shake_mag <= 0:
            return 0, 0
        return (RNG.randint(-int(self.shake_mag), int(self.shake_mag)),
                RNG.randint(-int(self.shake_mag), int(self.shake_mag)))

    def draw(self, surf, font):
        for s in self.slashes:
            s.draw(surf)
        for p in self.particles:
            p.draw(surf)
        for b in self.bolts:
            b.draw(surf)
        for d in self.dmg_numbers:
            d.draw(surf, font)
