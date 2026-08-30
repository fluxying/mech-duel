# -*- coding: utf-8 -*-
"""简单 AI 控制器：输出与真人按键同构的虚拟 input，驱动 Mech。

策略：决策计时器 + 意图计划（接近/拉开/近战/射击/格挡/跳跃/观望），
带反应性防御（对手起手近战时概率格挡，光束来袭时概率跳跃/格挡）。
阶段3：全部概率/间隔/失误率收敛到 settings.AI_DIFFICULTY 三档难度表，
随机源改为实例自带（可注入种子 → 平衡回归可复现）。
"""

import random

from settings import GUARD_MAX, SUPER_MAX, AI_DIFFICULTY

PLAN_MOVE, PLAN_RETREAT, PLAN_MELEE, PLAN_SHOOT, PLAN_BLOCK, PLAN_JUMP, PLAN_WAIT, PLAN_THROW, PLAN_SUPER = (
    "move", "retreat", "melee", "shoot", "block", "jump", "wait", "throw",
    "super")


class AIController:
    def __init__(self, mech, opponent, difficulty="normal", rng=None):
        self.mech = mech
        self.opponent = opponent
        self.difficulty = difficulty
        self.p = AI_DIFFICULTY[difficulty]
        self.rng = rng if rng is not None else random.Random()
        self.plan = PLAN_WAIT
        self.plan_t = 0          # 当前计划剩余帧
        self.decide_t = 10       # 距下次决策
        self.pressed = 0         # 攻击键按住帧数

    def _reset_input(self):
        for k in self.mech.input:
            self.mech.input[k] = False

    def update(self):
        m, o = self.mech, self.opponent
        rng = self.rng
        self._reset_input()
        if m.state == "ko" or o.state == "ko":
            return

        dist = abs(o.x - m.x)
        towards = 1 if o.x > m.x else -1

        # ---- 反应性防御 ----
        if self.plan not in (PLAN_BLOCK,):
            o_windup = o.state == "melee" and o.t < 16
            # 自身防御槽告急 → 少格挡多跳（防被 GUARD BREAK）
            guard_low = m.guard <= GUARD_MAX * 0.35
            if o_windup and dist < 80 and rng.random() < self.p["react_melee"]:
                self._set_plan(PLAN_JUMP if guard_low else PLAN_BLOCK,
                               rng.randint(16, 30))
            incoming = [b for b in getattr(self, "bolts_ref", [])
                        if b.owner is o and (b.x - m.x) * towards > 0
                        and abs(b.x - m.x) < 90]
            if incoming and rng.random() < self.p["react_bolt"]:
                self._set_plan(rng.choice([PLAN_JUMP] * (3 if guard_low else 1)
                                          + [PLAN_BLOCK]),
                               rng.randint(12, 24))
            # 对手防御站桩 → 抓投破防
            if (o.state == "block" and dist < 44 and m.throw_cd <= 0
                    and rng.random() < self.p["grab_block"]):
                self._set_plan(PLAN_THROW, 6)
            # 对手投技起手 → 跳起拆投（投技只抓地面目标）
            if (o.state == "throw" and o.t < 8 and dist < 50
                    and rng.random() < self.p["dodge_throw"]):
                self._set_plan(PLAN_JUMP, 8)

        # ---- 决策 ----
        self.decide_t -= 1
        if self.decide_t <= 0:
            self.decide_t = rng.randint(*self.p["decide"])
            self._decide(dist, towards)

        # ---- 执行当前计划 ----
        self._execute(dist, towards)

    def _set_plan(self, plan, duration):
        self.plan = plan
        self.plan_t = duration

    def _decide(self, dist, towards):
        m, o = self.mech, self.opponent
        rng = self.rng
        p = self.p
        # 失误率：概率原地发呆（低难度明显、高难度罕见）
        if rng.random() < p["mistake"]:
            self._set_plan(PLAN_WAIT, rng.randint(10, 20))
            return
        # 超必杀槽满：找机会直接放（中远距离优先）
        if m.super >= SUPER_MAX and dist > 40 and rng.random() < p["super_p"]:
            self._set_plan(PLAN_SUPER, 8)
            return
        if dist > 150:
            if m.energy >= 35 and rng.random() < 0.35:
                self._set_plan(PLAN_SHOOT, 8)
            else:
                self._set_plan(PLAN_MOVE, rng.randint(14, 26))
        elif dist > 60:
            if m.energy >= 35 and rng.random() < 0.25:
                self._set_plan(PLAN_SHOOT, 8)
            elif rng.random() < 0.75:
                self._set_plan(PLAN_MOVE, rng.randint(10, 22))
            elif rng.random() < 0.85:
                self._set_plan(PLAN_JUMP, 10)
            else:
                self._set_plan(PLAN_WAIT, rng.randint(8, 16))
        else:  # 近身
            if (o.state == "block" and m.throw_cd <= 0
                    and rng.random() < p["grab_near"]):
                self._set_plan(PLAN_THROW, 6)      # 对面站桩防御就抓投
            elif m.melee_cd <= 0 and rng.random() < p["melee_p"]:
                self._set_plan(PLAN_MELEE, 6)
            elif rng.random() < p["block_p"]:
                self._set_plan(PLAN_BLOCK, rng.randint(12, 24))
            elif rng.random() < 0.5:
                self._set_plan(PLAN_RETREAT, rng.randint(10, 18))
            else:
                self._set_plan(PLAN_WAIT, rng.randint(6, 14))

    def _execute(self, dist, towards):
        m = self.mech
        inp = m.input
        if self.plan_t > 0:
            self.plan_t -= 1
        else:
            self.plan = PLAN_WAIT

        # 边界回避：贴墙时强制向场内移动
        if m.x < 55 and self.plan in (PLAN_RETREAT,):
            self.plan = PLAN_MOVE
        if m.x > 425 and self.plan in (PLAN_RETREAT,):
            self.plan = PLAN_MOVE

        if self.plan == PLAN_MOVE:
            if towards > 0:
                inp["right"] = True
            else:
                inp["left"] = True
        elif self.plan == PLAN_RETREAT:
            if towards > 0:
                inp["left"] = True
            else:
                inp["right"] = True
        elif self.plan == PLAN_MELEE:
            if dist > 46:      # 太远先贴近再打
                if towards > 0:
                    inp["right"] = True
                else:
                    inp["left"] = True
            else:
                inp["melee"] = True
        elif self.plan == PLAN_SHOOT:
            inp["ranged"] = True
        elif self.plan == PLAN_THROW:
            inp["throw"] = True
        elif self.plan == PLAN_SUPER:
            inp["super"] = True
        elif self.plan == PLAN_BLOCK:
            inp["block"] = True
        elif self.plan == PLAN_JUMP:
            inp["jump"] = True

    # 光束引用由 Fight 每帧注入（用于弹道回避判断）
    def observe_bolts(self, bolts):
        self.bolts_ref = bolts
