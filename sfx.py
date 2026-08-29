# -*- coding: utf-8 -*-
"""8-bit 音效：标准库 array 实时合成方波/噪声，无外部音频文件。

 mixer 以 (22050, 16bit, mono) 预初始化；若无声卡则自动降级为静音。
"""

import array
import math
import random

import pygame

SR = 22050
RNG = random.Random(9)


def _square(dur, f0, f1=None, vol=0.26):
    """方波扫频：f0 -> f1，线性衰减包络。"""
    f1 = f1 if f1 is not None else f0
    n = int(SR * dur)
    buf = array.array("h")
    phase = 0.0
    for i in range(n):
        t = i / n
        freq = f0 + (f1 - f0) * t
        phase += freq / SR
        s = 1.0 if (phase % 1.0) < 0.5 else -1.0
        env = (1.0 - t) ** 1.3
        buf.append(int(s * vol * 32767 * env))
    return buf


def _noise(dur, vol=0.22):
    n = int(SR * dur)
    buf = array.array("h")
    for i in range(n):
        t = i / n
        env = (1.0 - t) ** 1.6
        buf.append(int(RNG.uniform(-1, 1) * vol * 32767 * env))
    return buf


def _concat(*parts):
    out = array.array("h")
    for p in parts:
        out.extend(p)
    return out


def _sound(samples):
    return pygame.mixer.Sound(buffer=samples.tobytes())


class Sfx:
    """音效集合；初始化失败时全部 play() 静默。"""

    def __init__(self):
        self.ok = False
        self.snd = {}
        try:
            if pygame.mixer.get_init() is None:
                return
            self.snd = {
                "menu":  _sound(_square(0.07, 880, 880, 0.2)),
                "fight": _sound(_concat(_square(0.09, 523, 523, 0.24),
                                        _square(0.14, 784, 784, 0.26))),
                "shoot": _sound(_square(0.13, 950, 260, 0.22)),
                "hit":   _sound(_concat(_noise(0.09, 0.26),
                                        _square(0.08, 150, 90, 0.26))),
                "block": _sound(_concat(_square(0.05, 1250, 700, 0.2),
                                        _noise(0.05, 0.12))),
                "ko":    _sound(_concat(_square(0.5, 520, 55, 0.3),
                                        _noise(0.25, 0.2))),
                "jump":  _sound(_square(0.09, 240, 520, 0.13)),
                "win":   _sound(_concat(_square(0.1, 523, 523, 0.24),
                                        _square(0.1, 659, 659, 0.24),
                                        _square(0.22, 784, 784, 0.28))),
            }
            self.ok = True
        except Exception:
            self.ok = False

    def play(self, name):
        if self.ok and name in self.snd:
            self.snd[name].play()
