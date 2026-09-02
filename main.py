# -*- coding: utf-8 -*-
"""《钢铁对决 MECH DUEL》入口：主循环、场景机（菜单/选人/对战/按键设置/结算）。

战斗核心在 fight.py，自测在 selftest.py —— 本文件只负责窗口与场景流转。

运行：
    python main.py            # 正常启动
    python main.py --demo     # AI 演示模式
    python main.py --selftest # 无窗口逻辑自测（回归验证；含 AI vs AI 平衡回归，
                              #  可用环境变量 MECHDUEL_BALANCE_N 调整局数，默认 100）
"""

import os
import random
import sys

import pygame

from settings import (INTERNAL_W, INTERNAL_H, WINDOW_W, WINDOW_H, FPS, TITLE,
                      AI_LEVELS, MECH_SPECS, MECH_ORDER, STAGES, STAGE_ORDER,
                      STATS_FILE, P1_KEYS, P2_KEYS, load_keymap, save_keymap)
from assets import build_mech_frames, build_background
from scene_flow import (InputMux, PadMap, SelectState, KeyConfigState,
                        demo_pair, load_stats, save_stats)
from sfx import Sfx
from ui import (draw_menu, draw_victory, draw_select, draw_keyconfig)
from fight import Fight, arcade_next, ROUND_END

MENU, SELECT, FIGHT, VICTORY, KEYCONFIG = (
    "menu", "select", "fight", "victory", "keyconfig")


def build_scanlines():
    surf = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
    for y in range(0, WINDOW_H, 3):
        surf.fill((0, 0, 0, 26), (0, y, WINDOW_W, 1))
    return surf


def run_window():
    pygame.mixer.pre_init(22050, -16, 1, 256)
    pygame.init()
    pygame.mixer.init(22050, -16, 1, 256)
    pygame.key.stop_text_input()   # 纯按键游戏：禁用 IME 文本合成，防止中文输入法吞键
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption(TITLE)
    clock = pygame.time.Clock()

    load_keymap()                  # 启动读取重映射键位（keymap.json）
    stats = load_stats()           # 战绩存档
    frames = build_mech_frames()
    stage_i = 0
    bg = build_background(theme=STAGE_ORDER[stage_i])
    sfx = Sfx()
    pads = PadMap()                # 手柄：1号→P1 2号→P2，即插即用无需配置
    scanlines = build_scanlines()

    demo = "--demo" in sys.argv            # 演示模式：AI 对 AI，直接开打
    difficulty = "normal"
    battle_i = 0                           # 战斗曲 A/B 按局轮换
    scene = FIGHT if demo else MENU
    fight = None                           # 菜单场景下尚无对战实例
    sel = None                             # 选人界面状态
    kc = None                              # 按键设置界面状态
    if demo:
        battle_i += 1
        fight = Fight("demo", frames, bg, sfx, difficulty=difficulty,
                      pads=pads, record_script=True)
    victory_fight = None                   # 回放前的结算局引用
    arcade = None                          # 街机模式状态（None=非街机）
    arcade_result = None                   # ("clear"/"fail", 通过层数)
    menu_t = 0
    victory_t = 0
    demo_i = 0                             # 演示轮换计数（demo_pair）
    running = True
    # 冒烟钩子：MECHDUEL_SMOKE=N 帧后自动退出（配合 dummy 驱动无头自检）
    smoke = int(os.environ.get("MECHDUEL_SMOKE", "0") or 0)
    smoke_scene = os.environ.get("MECHDUEL_SMOKE_SCENE", "")
    if smoke and not demo:
        if smoke_scene == "select":
            sel = SelectState("ai", difficulty)
            scene = SELECT
        elif smoke_scene == "keyconfig":
            kc = KeyConfigState()
            scene = KEYCONFIG
        elif smoke_scene == "training":
            fight = Fight("training", frames, bg, sfx, pads=pads,
                      record_script=True)
    frame_i = 0

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_m:           # 全局静音开关
                    sfx.toggle_mute()
                elif ev.key == pygame.K_ESCAPE:
                    if scene in (FIGHT, VICTORY):
                        scene, fight = MENU, None
                        arcade, arcade_result = None, None
                    elif scene == SELECT:
                        scene, sel = MENU, None
                    elif scene == KEYCONFIG:
                        scene, kc = MENU, None
                    else:
                        running = False
                elif scene == MENU:
                    if ev.key == pygame.K_1:
                        sel = SelectState("2p", difficulty)
                        scene = SELECT
                        sfx.play("menu")
                    elif ev.key == pygame.K_2:
                        sel = SelectState("ai", difficulty)
                        scene = SELECT
                        sfx.play("menu")
                    elif ev.key == pygame.K_3:
                        sel = SelectState("training", difficulty)
                        scene = SELECT
                        sfx.play("menu")
                    elif ev.key == pygame.K_4:
                        battle_i += 1
                        fight = Fight("demo", frames, bg, sfx,
                                      difficulty=difficulty, pads=pads,
                                      record_script=True)
                        scene = FIGHT
                        sfx.play("menu")
                    elif ev.key == pygame.K_5:
                        kc = KeyConfigState()
                        scene = KEYCONFIG
                        sfx.play("menu")
                    elif ev.key == pygame.K_6:
                        sel = SelectState("arcade", difficulty)
                        scene = SELECT
                        sfx.play("menu")
                    elif ev.key == pygame.K_TAB:   # AI 难度三档轮换
                        difficulty = AI_LEVELS[
                            (AI_LEVELS.index(difficulty) + 1) % len(AI_LEVELS)]
                        sfx.play("menu")
                    elif ev.key == pygame.K_e:     # 场地轮换
                        stage_i = (stage_i + 1) % len(STAGE_ORDER)
                        bg = build_background(theme=STAGE_ORDER[stage_i])
                        sfx.play("menu")
                elif scene == SELECT and sel is not None:
                    act, payload = sel.handle(ev.key)
                    if act == "back":
                        scene, sel = MENU, None
                    elif act == "start":
                        m1, m2 = payload
                        if sel.mode == "arcade":
                            import random as _rnd
                            arcade = {
                                "m1": m1, "stage": 0,
                                "opps": [(MECH_ORDER[_rnd.randrange(
                                    len(MECH_ORDER))], AI_LEVELS[i])
                                    for i in range(3)],
                            }
                            m2, diff = arcade["opps"][0]
                            mode, intro_sub = "ai", (
                                f"街机挑战 1/3 · "
                                f"{MECH_SPECS[m2]['cn_name']}")
                        else:
                            arcade = None
                            mode = ("2p" if sel.mode == "2p"
                                    else "ai" if sel.mode == "ai"
                                    else "training")
                            intro_sub = None
                        battle_i += 1
                        fight = Fight(mode, frames, bg, sfx, m1=m1, m2=m2,
                                      difficulty=diff if sel.mode == "arcade"
                                      else difficulty, pads=pads,
                                      record_script=True,
                                      intro_sub=intro_sub)
                        scene, sel = FIGHT, None
                        sfx.play("menu")
                elif scene == FIGHT and fight is not None:
                    if ev.key == pygame.K_r and not fight.scripted:
                        if arcade is not None:  # 街机：重开当前层
                            fight.reset_round()
                        else:
                            battle_i += 1       # 重开一局换曲
                            if fight.training:
                                fight.reset_round()    # 训练：仅重启假人
                            else:
                                fight.restart_match()
                        sfx.play("menu")
                    elif fight.training and ev.key == pygame.K_F1:
                        fight.show_hitboxes = not fight.show_hitboxes
                    elif fight.training and ev.key == pygame.K_F2:
                        fight.dummy_block = not fight.dummy_block
                elif scene == VICTORY and ev.key == pygame.K_v:
                    if fight is not None and fight.script and not demo:
                        victory_fight = fight           # 整局回放
                        fight = Fight("2p", frames, bg, sfx,
                                      m1=fight.p1.spec_key,
                                      m2=fight.p2.spec_key,
                                      scripted=fight.script, pads=pads)
                        scene = FIGHT
                        sfx.play("menu")
                elif scene == VICTORY and ev.key == pygame.K_r:
                    if arcade is not None:          # 街机：整链重开
                        arcade["stage"] = 0
                        m2, diff = arcade["opps"][0]
                        sub = f"街机挑战 1/3 · {MECH_SPECS[m2]['cn_name']}"
                        battle_i += 1
                        fight = Fight("ai", frames, bg, sfx, m1=arcade["m1"],
                                      m2=m2, difficulty=diff, pads=pads,
                                      record_script=True, intro_sub=sub)
                        arcade_result = None
                        scene = FIGHT
                    elif fight:
                        fight.restart_match()
                        scene = FIGHT
                    sfx.play("menu")
                elif scene == KEYCONFIG and kc is not None:
                    res = kc.handle(ev.key)
                    if res == "back":
                        scene, kc = MENU, None
                    elif res == "changed":
                        save_keymap()

        frame = pygame.Surface((INTERNAL_W, INTERNAL_H))
        if scene == MENU:
            menu_t += 1
            draw_menu(frame, bg, frames, menu_t, difficulty,
                      STAGES[STAGE_ORDER[stage_i]]["name"], stats)
        elif scene == SELECT and sel is not None:
            menu_t += 1
            draw_select(frame, bg, frames, sel, menu_t)
        elif scene == KEYCONFIG and kc is not None:
            menu_t += 1
            draw_keyconfig(frame, bg, kc.rows(), kc.idx, kc.waiting, menu_t)
        elif scene == FIGHT and fight is not None:
            inp = InputMux(pygame.key.get_pressed(),
                           pads.poll([P1_KEYS, P2_KEYS]))
            fight.step(inp)
            fight.render(frame)
            if fight.playback_done and fight.phase == ROUND_END:
                fight, scene = victory_fight, VICTORY   # 回放结束回结算页
                victory_t = 0
            elif fight.match_winner:
                if (not demo and fight.mode != "training"
                        and not fight.scripted):        # 回放不重复记战绩
                    stats["matches"] += 1
                    wname = fight.match_winner.spec_key
                    stats["wins"][wname] = stats["wins"].get(wname, 0) + 1
                    for p in (fight.p1, fight.p2):
                        stats["picks"][p.spec_key] = stats["picks"].get(p.spec_key, 0) + 1
                    save_stats(stats)
                if arcade is not None:                  # 街机流程推进
                    act, kw = arcade_next(arcade, fight.match_winner is fight.p1)
                    if act == "next":
                        battle_i += 1
                        sub = (f"街机挑战 {kw['stage'] + 1}/3 · "
                               f"{MECH_SPECS[kw['m2']]['cn_name']}")
                        fight = Fight("ai", frames, bg, sfx, m1=arcade["m1"],
                                      m2=kw["m2"], difficulty=kw["difficulty"],
                                      pads=pads, record_script=True,
                                      intro_sub=sub)
                        sfx.play("fight")
                    else:
                        arcade_result = ("clear" if act == "clear" else "fail",
                                         arcade["stage"])
                        scene = VICTORY
                        victory_t = 0
                        sfx.play("win")
                        if act == "clear" and not fight.scripted:
                            stats["arcade_clears"] = stats.get("arcade_clears", 0) + 1
                            save_stats(stats)
                else:
                    scene = VICTORY
                    victory_t = 0
                    sfx.play("win")
        else:  # VICTORY
            victory_t += 1
            draw_victory(frame, bg, fight.match_winner.spec,
                         fight.wins[0], fight.wins[1],
                         has_replay=bool(fight.script) and not demo,
                         arcade_result=arcade_result[0] if arcade_result else None,
                         arcade_stage=arcade_result[1] if arcade_result else 0)
            if demo and victory_t > FPS * 6:   # 演示模式：轮换机体与难度再来一局
                demo_i += 1
                battle_i += 1
                m1, m2, diff = demo_pair(demo_i)
                fight = Fight("demo", frames, bg, sfx, m1=m1, m2=m2,
                              difficulty=diff, pads=pads)
                scene = FIGHT

        scaled = pygame.transform.scale(frame, (WINDOW_W, WINDOW_H))
        screen.blit(scaled, (0, 0))
        screen.blit(scanlines, (0, 0))
        flash_a = fight.fx.flash_a if fight else 0
        if flash_a > 0:                       # 超必杀发动全屏白闪
            overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
            overlay.fill((255, 250, 235, int(min(255, flash_a))))
            screen.blit(overlay, (0, 0))
        pygame.display.flip()
        sfx.play_bgm(("battle2" if battle_i % 2 else "battle")
                     if scene in (FIGHT, VICTORY) else "menu")
        clock.tick(FPS)
        frame_i += 1
        if smoke and frame_i >= smoke:
            running = False

    pygame.quit()


# ================================================================ 自测


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from selftest import selftest      # 延迟导入：selftest 不反向依赖 main
        selftest()
    else:
        run_window()
