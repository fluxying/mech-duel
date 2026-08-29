# -*- coding: utf-8 -*-
"""简单 AI 控制器：输出与真人按键同构的虚拟 input，驱动 Mech。

策略：决策计时器 + 意图计划（接近/拉开/近战/射击/格挡/跳跃/观望），
带反应性防御（对手起手近战时概率格挡，光束来袭时概率跳跃/格挡）。
随机延迟与概率让它可被击败，难度适中。
"""

import random

RNG = random.Random(77)

PLAN_MOVE, PLAN_RETREAT, PLAN_MELEE, PLAN_SHOOT, PLAN_BLOCK, PLAN_JUMP, PLAN_WAIT = (
    "move", "retreat", "melee", "shoot", "block", "jump", "wait")


class AIController:
    def __init__(self, mech, opponent):
        self.mech = mech
        self.opponent = opponent
        self.plan = PLAN_WAIT
        self.plan_t = 0          # 当前计划剩余帧
        self.decide_t = 10       # 距下次决策
        self.pressed = 0         # 攻击键按住帧数

    def _reset_input(self):
        for k in self.mech.input:
            self.mech.input[k] = False

    def update(self):
        m, o = self.mech, self.opponent
        self._reset_input()
        if m.state == "ko" or o.state == "ko":
            return
        if o.state == "ko":
            return

        dist = abs(o.x - m.x)
        towards = 1 if o.x > m.x else -1

        # ---- 反应性防御 ----
        if self.plan not in (PLAN_BLOCK,):
            o_windup = o.state == "melee" and o.t < 16
            if o_windup and dist < 80 and RNG.random() < 0.035:
                self._set_plan(PLAN_BLOCK, RNG.randint(16, 30))
            incoming = [b for b in getattr(self, "bolts_ref", [])
                        if b.owner is o and (b.x - m.x) * towards > 0
                        and abs(b.x - m.x) < 90]
            if incoming and RNG.random() < 0.05:
                self._set_plan(RNG.choice([PLAN_JUMP, PLAN_BLOCK]),
                               RNG.randint(12, 24))

        # ---- 决策 ----
        self.decide_t -= 1
        if self.decide_t <= 0:
            self.decide_t = RNG.randint(8, 16)
            self._decide(dist, towards)

        # ---- 执行当前计划 ----
        self._execute(dist, towards)

    def _set_plan(self, plan, duration):
        self.plan = plan
        self.plan_t = duration

    def _decide(self, dist, towards):
        m, o = self.mech, self.opponent
        r = RNG.random()
        if dist > 150:
            if m.energy >= 35 and r < 0.35:
                self._set_plan(PLAN_SHOOT, 8)
            else:
                self._set_plan(PLAN_MOVE, RNG.randint(14, 26))
        elif dist > 60:
            if m.energy >= 35 and r < 0.25:
                self._set_plan(PLAN_SHOOT, 8)
            elif r < 0.75:
                self._set_plan(PLAN_MOVE, RNG.randint(10, 22))
            elif r < 0.85:
                self._set_plan(PLAN_JUMP, 10)
            else:
                self._set_plan(PLAN_WAIT, RNG.randint(8, 16))
        else:  # 近身
            if m.melee_cd <= 0 and r < 0.5:
                self._set_plan(PLAN_MELEE, 6)
            elif r < 0.65:
                self._set_plan(PLAN_BLOCK, RNG.randint(12, 24))
            elif r < 0.8:
                self._set_plan(PLAN_RETREAT, RNG.randint(10, 18))
            else:
                self._set_plan(PLAN_WAIT, RNG.randint(6, 14))

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
        elif self.plan == PLAN_BLOCK:
            inp["block"] = True
        elif self.plan == PLAN_JUMP:
            inp["jump"] = True

    # 光束引用由 Fight 每帧注入（用于弹道回避判断）
    def observe_bolts(self, bolts):
        self.bolts_ref = bolts
