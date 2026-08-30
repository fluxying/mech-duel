# -*- coding: utf-8 -*-
"""场景流模块（阶段 8 自 main.py 拆出）：选人 / 按键设置 / 手柄输入 / 演示轮换 / 战绩存档。

只依赖 pygame 与 settings，不接触战斗核心——Fight 的判定与回放仍在 main.py。
"""

import json
import random

import pygame

from settings import (P1_KEYS, P2_KEYS, DEFAULT_P1_KEYS, DEFAULT_P2_KEYS,
                      save_keymap, MECH_ORDER, AI_LEVELS, STATS_FILE)


# ================================================================ 手柄输入

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
    十字键/左摇杆 移动+跳+防，按钮 0/1/2/3 = 斩/束/投/超，4=防御 5=跳 6=重击。"""

    BTN = {"melee": 0, "ranged": 1, "throw": 2, "super": 3, "block": 4,
           "jump": 5, "heavy": 6}

    def __init__(self):
        self.joys = []
        try:
            pygame.joystick.init()
            for i in range(pygame.joystick.get_count()):
                self.joys.append(pygame.joystick.Joystick(i))
        except Exception:
            self.joys = []

    def rumble(self, low, high, ms):
        """手柄震动：命中轻震 / 破防中震 / KO 长震。无手柄/设备不支持时静默。"""
        for joy in self.joys:
            try:
                joy.rumble(low, high, ms)
            except Exception:
                pass

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


# ================================================================ 选人 / 按键设置

SEL_ACTS = ("left", "right", "jump", "block", "melee", "heavy", "ranged",
            "throw", "super")


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


# ================================================================ 演示轮换 / 战绩

def demo_pair(i):
    """AI 演示自动轮换：第 i 局的 (机体1, 机体2, 难度)。"""
    n = len(MECH_ORDER)
    return (MECH_ORDER[i % n], MECH_ORDER[(i // n + 1) % n],
            AI_LEVELS[i % len(AI_LEVELS)])


def load_stats():
    """战绩存档：{matches, wins{机甲:数}, picks{机甲:数}}。损坏即重置。"""
    try:
        with open(STATS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict) and "matches" in d:
            d.setdefault("wins", {})
            d.setdefault("picks", {})
            return d
    except Exception:
        pass
    return {"matches": 0, "wins": {}, "picks": {}}


def save_stats(stats):
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False)
    except Exception:
        pass
