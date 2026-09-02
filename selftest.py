# -*- coding: utf-8 -*-
"""无头自测：38 项回归用例（战斗/连段/超必杀/平衡矩阵/差异化/运动签名）。

从 main.py 拆出，运行方式不变：
    python main.py --selftest
    MECHDUEL_BALANCE_N=400 MECHDUEL_MATRIX_K=20 python main.py --selftest
"""

import os
import random
import sys

import pygame

from settings import (ARENA_LEFT, ARENA_RIGHT, GROUND_Y, ROUND_TIME,
                      ROUNDS_TO_WIN, KO_SLOW_FRAMES, HITSTOP_FRAMES,
                      BLOCK_REDUCE, MELEE_WINDUP, MELEE_ACTIVE, THROW_HIT_T,
                      AIR_MELEE_ACTIVE, AIR_MELEE_MULT, RANGED_DAMAGE,
                      ENERGY_MAX, SUPER_MAX, SUPER_COST, SUPER_GAIN_HIT,
                      SUPER_GAIN_TAKE, SUPER_GAIN_BLOCK, SUPER_FLASH_FRAMES,
                      AZURE_SUPER_DMG, GARNET_SUPER_DMG, GUARD_MAX,
                      DRIVE_MAX, DRIVE_PARRY_GAIN, PARRY_HITSTOP,
                      PARRY_STAGGER, PUNISH_MULT, COMBO_RESET_FRAMES,
                      COMBO_SCALE_MIN, BLOCK_STUN, THROW_TECH_LAG,
                      WALL_SPLASH_STUN, MECH_ORDER, MECH_SPECS,
                      P1_KEYS, P2_KEYS, DEFAULT_P1_KEYS, DEFAULT_P2_KEYS,
                      AFTERIMAGE_STYLES, load_keymap, save_keymap)
from assets import build_mech_frames, build_background
from mech import Mech
from effects import Fx
from ai import AIController
from scene_flow import KeyConfigState, PadMap, SelectState, demo_pair
from sfx import Sfx
from fight import Fight, arcade_next, QuietFx, INTRO, ACTIVE, SLOW, REPLAY, \
    ROUND_END, INTRO_FRAMES, ROUND_END_FRAMES


class FakeKeys:
    """自测用：模拟 pygame.key.get_pressed() 的按位取值接口。"""

    def __init__(self, pressed):
        self.pressed = pressed

    def __getitem__(self, keycode):
        return self.pressed.get(keycode, False)


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

    # 13) AZURE 超必杀「苍蓝射线」：全屏贯穿激光，命中后继续飞行
    f13 = Fight("2p", frames, bg, sfx)
    f13.phase = ACTIVE
    f13.p1.x, f13.p2.x = 160, 320
    f13.p2.super = SUPER_MAX
    f13.step(FakeKeys({P2_KEYS["super"]: True}))
    assert f13.p2.state == "super", f"未进入超必杀: {f13.p2.state}"
    b13 = None
    for _ in range(90):
        f13.step(FakeKeys({}))
        if f13.fx.bolts:
            b13 = f13.fx.bolts[0]
            break
    assert b13 is not None, "苍蓝射线未发射"
    assert b13.dmg == AZURE_SUPER_DMG and b13.big and b13.pierce,     "贯穿激光参数不符"
    for _ in range(120):
        f13.step(FakeKeys({}))
        if f13.p1.hp <= f13.p1.max_hp - 18:   # 两连命中（第二发受连段衰减）
            break
    assert f13.p1.hp <= f13.p1.max_hp - 18,     "两连贯穿未全部命中"
    assert b13.hit_done and not b13.dead, "贯穿激光应命中后继续飞行"
    print("[13] AZURE 超必杀贯穿射线: OK")

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
    f29c = Fight("2p", frames, bg, sfx)    # AZURE Lv3 苍穹风暴：6 连贯穿
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

    # 35) 超必杀差异化：天降轰炸 / 追踪电弹 / 瞬步乱舞 / 瞬移背袭 / 冲撞霸体 / 滑步贯穿
    # a) VERDANT Lv3 世界树降临：弹体自屏幕上方落下，落点环绕对手
    f35a = Fight("2p", frames, bg, sfx, m1="verdant")
    f35a.phase = ACTIVE
    f35a.p1.x, f35a.p2.x = 180, ARENA_RIGHT - 24
    f35a.p1.super = 300
    f35a.step(FakeKeys({pygame.K_a: True, pygame.K_i: True}))
    assert f35a.p1.state == "super" and f35a.p1.super_level == 3
    saw_rain = False
    for _ in range(220):
        f35a.step(FakeKeys({}))
        if any(b.y < GROUND_Y - 150 for b in f35a.fx.bolts):
            saw_rain = True
    assert saw_rain, "天降轰炸未从高空落下"
    loss35a = f35a.p2.max_hp - f35a.p2.hp
    assert loss35a >= 16, f"天降轰炸命中段数不足: {loss35a}"
    # b) VIOLET Lv1 紫电狂涛：追踪电弹命中上升中的目标（直线弹会从脚下穿过）
    f35b = Fight("2p", frames, bg, sfx, m1="violet")
    f35b.phase = ACTIVE
    f35b.p1.x, f35b.p2.x = 180, 300
    f35b.p1.super = SUPER_MAX
    f35b.step(FakeKeys({pygame.K_i: True}))
    f35b.p2.vy = -6.2
    f35b.p2.state = "jump"
    hit35b = False
    for _ in range(140):
        f35b.step(FakeKeys({}))
        if f35b.p2.hp < f35b.p2.max_hp:
            hit35b = True
            break
    assert hit35b, "追踪电弹未命中上升目标"
    # c) VIOLET Lv2 瞬影乱舞：三段瞬步连续命中（对手贴墙无法拉开）
    f35c = Fight("2p", frames, bg, sfx, m1="violet")
    f35c.phase = ACTIVE
    f35c.p1.x, f35c.p2.x = 330, ARENA_RIGHT - 24
    f35c.p1.super = 200
    f35c.step(FakeKeys({pygame.K_d: True, pygame.K_i: True}))
    assert f35c.p1.state == "super" and f35c.p1.super_level == 2
    for _ in range(140):
        f35c.step(FakeKeys({}))
        if f35c.p1.state != "super":
            break
    loss35c = f35c.p2.max_hp - f35c.p2.hp
    assert loss35c >= 24, f"瞬步乱舞命中段数不足: {loss35c}"
    assert f35c.p1.x > 330, "瞬步未向前位移"
    # d) VIOLET Lv3 九天雷罚：瞬移到对手背后再放追踪电弹
    f35d = Fight("2p", frames, bg, sfx, m1="violet")
    f35d.phase = ACTIVE
    f35d.p1.x, f35d.p2.x = 160, 280
    f35d.p1.super = 300
    f35d.step(FakeKeys({pygame.K_a: True, pygame.K_i: True}))
    assert f35d.p1.state == "super" and f35d.p1.super_level == 3
    blinked = False
    for _ in range(90):
        f35d.step(FakeKeys({}))
        if f35d.p1.x > f35d.p2.x and f35d.p1.facing == -1:
            blinked = True
            break
    assert blinked, "九天雷罚未瞬移至对手背后"
    # e) GARNET Lv2 地裂冲击：冲撞判定相全程霸体
    f35e = Fight("2p", frames, bg, sfx)
    f35e.phase = ACTIVE
    f35e.p1.x, f35e.p2.x = 200, 320
    f35e.p1.super = 300
    f35e.step(FakeKeys({pygame.K_d: True, pygame.K_i: True}))
    for _ in range(60):
        f35e.step(FakeKeys({}))
        if f35e.p1.state == "super" and f35e.p1.t >= 10:
            break
    assert f35e.p1.armor_on, "Lv2 冲撞霸体缺失"
    # f) AZURE Lv2 疾影射线：滑步 + 三连贯穿
    f35f = Fight("2p", frames, bg, sfx, m1="azure")
    f35f.phase = ACTIVE
    f35f.p1.x, f35f.p2.x = 120, 300
    f35f.p1.super = 200
    f35f.step(FakeKeys({pygame.K_d: True, pygame.K_i: True}))
    assert f35f.p1.state == "super" and f35f.p1.super_level == 2
    shots35f = 0
    for _ in range(120):
        f35f.step(FakeKeys({}))
        if f35f.fx.bolts:
            shots35f += 1
            assert all(b.pierce for b in f35f.fx.bolts)
            f35f.fx.bolts.clear()
    assert shots35f >= 3, f"疾影射线连射数不足: {shots35f}"
    assert f35f.p1.x > 120, "疾影射线未滑步"
    print("[35] 超必杀差异化（天降/追踪/瞬步/瞬移/霸体/贯穿）: OK")

    # 36) 重击动作差异化：anim 三元组 + 机内三变体判定相互异 + 渲染链贯通
    from assets import FRAMES as _FR
    for mk in MECH_ORDER:
        trio = [MOVE_DEFS[mk][k] for k in ("heavy", "fwd_heavy", "back_heavy")]
        for d in trio:
            if "anim" in d:
                for fn in d["anim"]:
                    assert fn in _FR, f"{mk} anim 帧不存在: {fn}"
        act = [d.get("anim", ("atk0", "atk1", "atk2"))[1] for d in trio]
        assert len(set(act)) == 3, f"{mk} 三重击判定相动作雷同: {act}"
    assert _FR["bash"][3] is None and _FR["toss"][3] is None, "bash/toss 应无光剑"
    f36 = Fight("2p", frames, bg, sfx, m1="azure")
    f36.phase = ACTIVE
    m36 = f36.p1
    m36.state = "heavy"
    m36.move_key = "fwd_heavy"
    m36.move = MOVE_DEFS["azure"]["fwd_heavy"]
    m36.t = m36.move["windup"] + 1
    assert m36.current_frame_name() == "thrust",     f"azure 突刺帧缺失: {m36.current_frame_name()}"
    assert m36.frames["p2"]["thrust"][1], "thrust 帧未构建"
    m36b = Fight("2p", frames, bg, sfx).p1           # garnet：肩撞（无剑）
    m36b.state = "heavy"
    m36b.move_key = "fwd_heavy"
    m36b.move = MOVE_DEFS["garnet"]["fwd_heavy"]
    m36b.t = m36b.move["windup"] + 1
    assert m36b.current_frame_name() == "bash",     f"garnet 肩撞帧缺失: {m36b.current_frame_name()}"
    print("[36] 重击动作差异化（突刺/升斩/低扫/肩撞/投掷）: OK")

    # 37) 机甲间剪影/光刃差异化（批次 A）：防回退到「同骨架换皮」
    import assets as assets_mod
    from assets import (PAL_PARTS as _PP, PAL_SABER as _PS, BASE_PARTS as _BP,
                        FRAMES as _FRAMES)
    from settings import MECH_PALETTES
    import hashlib as _hl

    def _fhash(pal, fname):
        return _hl.md5(bytes(frames[pal][fname][1].get_view("1"))).hexdigest()

    _pals = [MECH_SPECS[k]["palette"] for k in MECH_ORDER]
    # a) 四台机甲 idle 帧必须互不相同（剪影差异化存在）
    _idle = {p: _fhash(p, "idle") for p in _pals}
    assert len(set(_idle.values())) == len(_pals), f"机甲 idle 剪影雷同: {_idle}"
    # b) 每台至少覆盖 6 个部件（上身六件套：idle/atk0/atk1/shoot/block/hurt），
    #    且覆盖的部件确实与通用骨架不同
    for _p in _pals:
        _ov = _PP.get(_p, {})
        assert len(_ov) >= 6, f"{_p} 差异化部件不足: {len(_ov)}"
        for _k, _v in _ov.items():
            assert _v != _BP[_k], f"{_p}.{_k} 与通用骨架相同（覆盖无效）"
    # c) 四台机甲光刃 style 互不相同，且每台覆盖的帧都能渲染出不同像素
    #    （shoot 帧武器是炮、无刃，PAL_SABER 里记 None，推导 style 时跳过）
    _styles = {}
    for _p in _pals:
        _sb = _PS.get(_p, {})
        assert _sb, f"{_p} 无光刃覆盖"
        _st = {fn: (p[4] if len(p) > 4 else "blade")
               for fn, p in _sb.items() if p}
        _styles[_p] = tuple(sorted(set(_st.values())))
    assert len(set(_styles.values())) == len(_pals), f"光刃风格雷同: {_styles}"
    # d) 批次 B：atk0/atk1/shoot/block/hurt 五帧上身差异化 —— 四台渲染互不相同
    for _fn in ("atk0", "atk1", "shoot", "block", "hurt"):
        _h = {p: _fhash(p, _fn) for p in _pals}
        assert len(set(_h.values())) == len(_pals), (
            f"{_fn} 招式表现雷同: {_h}")
    # e) 像素连通性：每帧（机体 + 光刃 + 电弧）必须是单一 4-连通块。
    #    字符画最容易出的错是「数错填充格」——部件之间差一格就会在 2x 放大后
    #    变成悬空碎块（肩甲脱离躯干、武器浮在半空、电弧离脚两格）。
    from assets import FRAME_W as _FW, FRAME_H as _FH

    def _comps(pal, fname):
        _tag, _uk, _lk, _sab = _FRAMES[fname]
        _pts = dict(_BP)
        _pts.update(_PP.get(pal, {}))
        _up = _pts[_uk] if isinstance(_uk, str) else _uk
        _lg = _pts[_lk] if isinstance(_lk, str) else _lk
        _g = assets_mod._grid_from_rows(list(_up) + (list(_lg) if _lg else []))
        assets_mod._draw_saber(_g, _PS.get(pal, {}).get(fname, _sab),
                               MECH_PALETTES[pal])
        _seen, _out = set(), []
        for _y in range(_FH):
            for _x in range(_FW):
                if _g[_y][_x] == "." or (_x, _y) in _seen:
                    continue
                _st, _cur = [(_x, _y)], []
                _seen.add((_x, _y))
                while _st:
                    cx, cy = _st.pop()
                    _cur.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if (0 <= nx < _FW and 0 <= ny < _FH
                                and (nx, ny) not in _seen and _g[ny][nx] != "."):
                            _seen.add((nx, ny))
                            _st.append((nx, ny))
                _out.append(_cur)
        return sorted(_out, key=len, reverse=True)

    _frames_checked = 0
    for _p in _pals:
        for _fn in ("idle", "walk_a", "walk_b", "jump", "atk0", "atk1", "atk2",
                    "thrust", "rise", "sweep", "bash", "toss", "shoot",
                    "block", "hurt"):
            if _fn not in _FRAMES:
                continue
            _cs = _comps(_p, _fn)
            assert len(_cs) == 1, (
                f"{_p}.{_fn} 存在悬空碎块：{len(_cs)} 块，"
                f"游离像素 {[len(c) for c in _cs[1:]]}")
            _frames_checked += 1

    print(f"[37] 机甲剪影/光刃/攻击姿态差异化（{len(_pals)} 台 · "
          f"部件 {sum(len(_PP.get(p, {})) for p in _pals)} 项 · "
          f"上身五帧互异 · 连通性 {_frames_checked} 帧）: OK")

    # 38) 运动签名残影（批次 C）：四台签名互异、会消散、且纯表现层不影响判定
    from settings import AFTERIMAGE_STYLES as _AIS, DASH_FRAMES as _DF

    def _dash_run(key, ghosts=True):
        """双击前冲跑完整个冲刺窗口。返回 (峰值残影, 收尾残影, 位移)。"""
        f = Fight("2p", frames, bg, sfx, m1=key, m2=key)
        f.phase = ACTIVE
        f.p1.x, f.p2.x = 200, 360
        if not ghosts:                      # 对照组：掐掉残影生成
            f._spawn_ghosts = lambda: None
        x0 = f.p1.x
        for ks in ({pygame.K_d: True}, {pygame.K_d: True}, {}, {},
                   {pygame.K_d: True}):
            f.step(FakeKeys(ks))
        assert f.p1.state == "dash", f"{key} 未进入冲刺: {f.p1.state}"
        peak = 0
        for _ in range(_DF):
            f.step(FakeKeys({pygame.K_d: True}))
            peak = max(peak, len(f.fx.ghosts))
        for _ in range(70):                 # 停手：残影须自然消散干净
            f.step(FakeKeys({}))
        return peak, len(f.fx.ghosts), f.p1.x - x0

    # a) 四台签名参数互异（间隔/存活/染色三元组各不相同）
    _sigs = {p: (v["interval"], v["life"], tuple(v["tint"]))
             for p, v in _AIS.items()}
    assert len(_sigs) == len(_pals), "签名表未覆盖全部机体"
    assert len(set(_sigs.values())) == len(_pals), f"签名参数雷同: {_sigs}"
    # b) 四台冲刺都产生残影，停手后自动清空
    _peak = {}
    for _k in MECH_ORDER:
        _pk, _left, _dx = _dash_run(_k)
        assert _pk > 0, f"{_k} 冲刺未产生运动签名残影"
        assert _left == 0, f"{_k} 残影未消散: 余 {_left}"
        _peak[_k] = _pk
    # c) 残影纯表现层：开/关残影的位移完全一致（判定与推进不受影响）
    for _k in MECH_ORDER:
        _, _, _dx_on = _dash_run(_k, ghosts=True)
        _, _, _dx_off = _dash_run(_k, ghosts=False)
        assert _dx_on == _dx_off, (
            f"{_k} 残影改变了位移: {_dx_on} vs {_dx_off}")
    # d) VIOLET Lv3 瞬移帧留「现形残影」（blink_t 强制出一张，不受间隔限制）
    _f38 = Fight("2p", frames, bg, sfx, m1="violet", m2="violet")
    _f38.phase = ACTIVE
    _f38.p1.x, _f38.p2.x = 200, 300
    _f38.p1.super = SUPER_MAX
    _f38.step(FakeKeys({pygame.K_a: True, pygame.K_i: True}))
    assert _f38.p1.state == "super" and _f38.p1.super_level == 3, \
        f"VIOLET Lv3 未触发: {_f38.p1.super_level}"
    _bt = _f38.p1.spec["super_levels"][3]["blink_t"]
    _seen = 0
    for _ in range(80):
        _f38.step(FakeKeys({}))
        if _f38.p1.t == _bt:
            _seen = len(_f38.fx.ghosts)
            break
    assert _seen > 0, f"瞬移帧未留现形残影 (blink_t={_bt})"
    # e) 残影是染色快照：与原帧不雷同，且随存活帧淡出（alpha 递减）
    _f38b = Fight("2p", frames, bg, sfx, m1="verdant", m2="verdant")
    _f38b.phase = ACTIVE
    _f38b.p1.x, _f38b.p2.x = 200, 360
    for ks in ({pygame.K_d: True}, {pygame.K_d: True}, {}, {},
               {pygame.K_d: True}):
        _f38b.step(FakeKeys(ks))
    for _ in range(3):
        _f38b.step(FakeKeys({pygame.K_d: True}))
    assert _f38b.fx.ghosts, "对照组未生成残影（无法校验染色）"

    def _avg_rgb(surf):
        w, h = surf.get_size()
        tot = [0, 0, 0]
        n = 0
        for y in range(0, h, 3):
            for x in range(0, w, 3):
                c = surf.get_at((x, y))
                if c.a > 128:
                    tot[0] += c.r
                    tot[1] += c.g
                    tot[2] += c.b
                    n += 1
        return tuple(v // max(1, n) for v in tot)

    _g = _f38b.fx.ghosts[0]
    _orig = _f38b.p1.draw_pose(_f38b.t)[0]
    assert _avg_rgb(_g.img) != _avg_rgb(_orig), "残影未染色（与原帧雷同）"
    #    alpha 在 draw() 时按存活帧比例设定，故画一次再比对
    _tmp = pygame.Surface(_g.img.get_size(), pygame.SRCALPHA)
    _g.draw(_tmp)
    _a0 = _g.img.get_alpha()
    _g.update()
    _g.draw(_tmp)
    _a1 = _g.img.get_alpha()
    assert _a1 < _a0, f"残影未随存活帧淡出: {_a0} → {_a1}"

    print(f"[38] 运动签名残影（{len(_pals)} 台签名互异 · 冲刺峰值 {_peak} · "
          f"瞬移现形 · 染色淡出 · 位移无影响）: OK")

    # 39) 倒地免疫：被投/击倒躺地（knockdown）期间攻击穿透，起身恢复可被攻击
    f39 = Fight("2p", frames, bg, sfx)
    f39.phase = ACTIVE
    f39.p1.x, f39.p2.x = 200, 250
    p39 = f39.p2
    p39.take_damage(16, 1, f39.fx, sfx, unblockable=True, launch=True)  # 投技击飞
    for _ in range(80):
        p39.update(f39.p1, f39.fx, sfx)
        if p39.knockdown and p39.grounded:
            break
    assert p39.knockdown, f"被投落地未倒地: state={p39.state}"
    hp0 = p39.hp
    for _ in range(5):                                  # 躺地期间连打：全部穿透
        res = p39.take_damage(10, 1, f39.fx, sfx)
        assert res is None, f"倒地免疫失效: 返回 {res}"
    assert p39.hp == hp0, f"倒地仍被扣血: {hp0} → {p39.hp}"
    for _ in range(120):                                # 硬直结束正常起身
        p39.update(f39.p1, f39.fx, sfx)
        if p39.state == "idle":
            break
    assert p39.state == "idle", f"倒地后未能起身: {p39.state}"
    assert not p39.knockdown, "起身后 knockdown 未清除"
    hp1 = p39.hp
    assert p39.take_damage(10, 1, f39.fx, sfx) == "hit"  # 起身恢复可被攻击
    assert p39.hp < hp1, "起身后攻击未命中"
    print("[39] 倒地免疫（躺地攻击穿透 · 起身恢复可被攻击）: OK")

    print("SELFTEST PASS")
    pygame.quit()
