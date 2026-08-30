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


# ---------------------------------------------------------------- BGM（程序化 chiptune 循环曲）
def _silence(dur, vol=0.0):
    return _square(dur, 55, 55, vol)


def _bgm_menu():
    """菜单曲：舒缓琶音，约 5.8s 循环。"""
    step = 0.18
    arp = (262, 330, 392, 523, 392, 330)
    bass = (131, 0, 98, 0)
    buf = array.array("h")
    for rep in range(3):
        b = bass[rep % len(bass)]
        for f in arp:
            if b:
                buf.extend(_square(step, b, b, 0.11))
            else:
                buf.extend(_silence(step))
            buf.extend(_square(step * 2, f, f, 0.075))
    return buf


def _bgm_battle():
    """战斗曲：驱动型低音 + 两条主旋律变奏，约 8s 循环。"""
    step = 0.125
    bass = (110, 110, 0, 110, 165, 0, 110, 98) * 2
    bars = (
        (440, 523, 587, 523, 440, 392, 330, 392),
        (440, 523, 587, 659, 587, 523, 440, 330),
    )
    buf = array.array("h")
    for bar in bars:
        for f in bass:
            if f:
                buf.extend(_square(step, f, f, 0.15))
            else:
                buf.extend(_silence(step))
        for f in bar:
            buf.extend(_square(step * 2, f, f, 0.09))
    return buf


def _bgm_battle2():
    """战斗曲 B：小调推进，约 8s 循环（与 A 按局轮换）。"""
    step = 0.125
    bass = (98, 98, 0, 98, 147, 0, 110, 98) * 2
    bars = (
        (440, 523, 494, 440, 392, 440, 330, 392),
        (440, 494, 523, 587, 523, 494, 440, 349),
    )
    buf = array.array("h")
    for bar in bars:
        for f in bass:
            if f:
                buf.extend(_square(step, f, f, 0.15))
            else:
                buf.extend(_silence(step))
        for f in bar:
            buf.extend(_square(step * 2, f, f, 0.09))
    return buf


class Sfx:
    """音效 + BGM 集合；初始化失败时全部 play() 静默。"""

    BGM_VOL = 0.45

    def __init__(self):
        self.ok = False
        self.snd = {}
        self.bgm = {}
        self.bgm_name = None
        self.bgm_ch = None
        self.muted = False
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
                "super": _sound(_concat(_square(0.3, 220, 880, 0.3),
                                        _noise(0.22, 0.18))),
                "break": _sound(_concat(_noise(0.3, 0.3),
                                        _square(0.25, 420, 60, 0.3))),
            }
            # BGM：专用通道循环播放
            self.bgm = {
                "menu":    _sound(_bgm_menu()),
                "battle":  _sound(_bgm_battle()),
                "battle2": _sound(_bgm_battle2()),
            }
            pygame.mixer.set_reserved(1)
            self.bgm_ch = pygame.mixer.Channel(0)
            self.bgm_ch.set_volume(self.BGM_VOL)
            self.ok = True
        except Exception:
            self.ok = False

    def play(self, name):
        if self.ok and not self.muted and name in self.snd:
            self.snd[name].play()

    # ---------------- BGM ----------------
    def play_bgm(self, name):
        """切换循环曲（同名不重启）；name=None 停止。"""
        if not self.ok or name == self.bgm_name:
            return
        if self.bgm_ch is not None:
            self.bgm_ch.stop()
        self.bgm_name = name
        if name is not None and name in self.bgm and not self.muted:
            self.bgm_ch.play(self.bgm[name], loops=-1)

    def stop_bgm(self):
        if self.bgm_ch is not None:
            self.bgm_ch.stop()
        self.bgm_name = None

    def toggle_mute(self):
        """静音开关：BGM 停/恢复，音效静默。返回当前静音状态。"""
        self.muted = not self.muted
        if self.bgm_ch is not None:
            if self.muted:
                self.bgm_ch.stop()
            elif self.bgm_name is not None:
                self.bgm_ch.play(self.bgm[self.bgm_name], loops=-1)
        return self.muted
