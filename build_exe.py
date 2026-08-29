# -*- coding: utf-8 -*-
"""通用 PyInstaller 打包脚本（可复用到任意 Python 项目）。

做的事：
  1. 自动探测入口脚本 / 应用名 / 图标（不写死，换项目也能用）
  2. AST 扫描项目源码，自动推断第三方依赖（排除标准库与本地模块）
  3. 在 build/.venv 里建隔离虚拟环境（优先复用系统已装好的包，不污染全局环境）
  4. 调用 PyInstaller 生成 dist/<AppName>.exe（单文件 or 单目录、窗口 or 控制台）
  5. 可选：冒烟测试（跑一遍 exe 的 --selftest）、打 zip 包

用法：
    python build_exe.py                # 按下面的 CONFIG 打包
    python build_exe.py --onedir       # 单目录模式（启动更快，便于排查）
    python build_exe.py --console      # 保留控制台窗口（调试用）
    python build_exe.py --clean        # 打包前删掉 build/ 与 dist/
    python build_exe.py --smoke        # 打包后运行 exe 自测
    python build_exe.py --zip          # 额外产出 dist/<AppName>.zip
    python build_exe.py --name Foo --entry app.py --icon icon.ico
"""

import argparse
import ast
import os
import shutil
import subprocess
import sys
import time

try:                                    # Windows 控制台中文不乱码
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ================================================================ 项目配置
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG = {
    # 留空（None）即自动探测
    "app_name":   None,      # None -> 项目目录名
    "entry":      None,      # None -> main.py / app.py / __main__.py / 唯一 *.py
    "icon":       None,      # None -> 项目根目录下的 *.ico
    "onefile":    True,      # True=单文件 exe，False=单目录
    "console":    False,     # True=带控制台（GUI 游戏一般 False）
    "zip":        False,     # 打包后是否额外压缩
    "smoke":      False,     # 打包后是否运行自测
    "smoke_args": ["--selftest"],   # 自测参数（你的项目没有就改成 []）
    "smoke_timeout": 600,
    "requirements": [],      # 额外强制安装的包（自动探测之外）
    # 依赖探测时跳过的文件（打包脚本自身 / 构建相关文件不该算作项目依赖）
    "scan_skip": ["build_exe.py", "setup.py", "conftest.py"],
    "extra_data":  [],       # 额外资源 [(源路径, 打包内目标目录), ...]
    "excludes": [            # 明确用不到的重模块，可显著减小体积
        "tkinter", "numpy", "matplotlib", "PyQt5", "PySide2",
        "IPython", "notebook", "pytest", "scipy", "pandas",
    ],
    "upx": False,            # True 时若 PATH 里有 upx 则压缩（可能因杀软误报，默认关）
}

BUILD_DIR = os.path.join(PROJECT_DIR, "build")
VENV_DIR = os.path.join(BUILD_DIR, ".venv")
DIST_DIR = os.path.join(PROJECT_DIR, "dist")

# 常见「导入名 -> pip 包名」映射（自动探测依赖时用）
IMPORT_TO_PIP = {
    "PIL": "pillow",
    "cv2": "opencv-python",
    "yaml": "pyyaml",
    "dotenv": "python-dotenv",
    "attr": "attrs",
    "dateutil": "python-dateutil",
    "requests": "requests",
    "OpenGL": "pyopengl",
    "OpenGL.GL": "pyopengl",
    "wx": "wxpython",
}

LOG_T0 = time.time()


def log(msg, level="INFO"):
    mark = {"INFO": "[..]", "OK": "[OK]", "WARN": "[!!]", "ERR": "[XX]"}.get(level, "[..]")
    print(f"{mark} {msg}", flush=True)


def sanitized_env(extra=None):
    """子进程环境：剔除注入型 PYTHONPATH（某些终端会注入 sitecustomize 钩子，
    它会劫持 os.remove，导致 PyInstaller 清理缓存时报错）。"""
    env = dict(os.environ)
    parts = [p for p in env.get("PYTHONPATH", "").split(os.pathsep)
             if p and "app.asar.unpacked" not in p and "sitecustomize" not in p.lower()]
    if parts:
        env["PYTHONPATH"] = os.pathsep.join(parts)
    else:
        env.pop("PYTHONPATH", None)
    if extra:
        env.update(extra)
    return env


def run(cmd, cwd=PROJECT_DIR, check=True, env=None):
    """执行命令并实时回显输出。"""
    printable = " ".join(f'"{c}"' if " " in c else c for c in cmd)
    log(f"$ {printable}")
    proc = subprocess.run(cmd, cwd=cwd, env=env or sanitized_env(),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, encoding="utf-8", errors="replace")
    if proc.stdout:
        for line in proc.stdout.rstrip().splitlines():
            print("     " + line, flush=True)
    if check and proc.returncode != 0:
        raise SystemExit(f"\n[XX] 命令失败（退出码 {proc.returncode}）: {printable}")
    return proc


# ================================================================ 自动探测
def find_entry():
    for name in ("main.py", "app.py", "__main__.py", "run.py", "game.py"):
        p = os.path.join(PROJECT_DIR, name)
        if os.path.isfile(p):
            return p
    roots = [f for f in os.listdir(PROJECT_DIR)
             if f.endswith(".py") and not f.startswith(("build_", "setup", "test_"))]
    if len(roots) == 1:
        return os.path.join(PROJECT_DIR, roots[0])
    raise SystemExit("[XX] 找不到入口脚本，请用 --entry 指定")


def find_icon():
    for name in sorted(os.listdir(PROJECT_DIR)):
        if name.endswith(".ico"):
            return os.path.join(PROJECT_DIR, name)
    return None


def make_icon_from_png(vpy, png_path, out_ico):
    """用虚拟环境里的 Pillow 把 PNG 转成 .ico（失败则跳过，不影响打包）。"""
    code = (
        "import sys\n"
        "from PIL import Image\n"
        "src, dst = sys.argv[1], sys.argv[2]\n"
        "img = Image.open(src).convert('RGBA')\n"
        "img.thumbnail((256, 256))\n"
        "img.save(dst, sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])\n"
    )
    try:
        r = subprocess.run([vpy, "-c", code, png_path, out_ico],
                           cwd=PROJECT_DIR, env=sanitized_env(),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=120)
        if r.returncode != 0:
            log(f"图标转换失败：{(r.stdout or '').strip()[:200]}", "WARN")
            return None
    except Exception as exc:
        log(f"图标转换失败：{exc}", "WARN")
        return None
    return out_ico if os.path.isfile(out_ico) else None


def detect_modules(entry):
    """AST 扫描项目内 *.py，返回用到的第三方顶层模块名集合。"""
    local_names = set()
    for f in os.listdir(PROJECT_DIR):
        if f.endswith(".py"):
            local_names.add(f[:-3])
    skip = set(CONFIG["scan_skip"]) | {os.path.basename(__file__)}
    found = set()
    for f in sorted(os.listdir(PROJECT_DIR)):
        if not f.endswith(".py") or f in skip or f.startswith(("test_", "build_")):
            continue
        try:
            tree = ast.parse(open(os.path.join(PROJECT_DIR, f),
                                  encoding="utf-8").read(), filename=f)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    found.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:      # 跳过相对导入
                    found.add(node.module.split(".")[0])
    stdlib = getattr(sys, "stdlib_module_names", set())
    return sorted(m for m in found
                  if m and m not in stdlib and m not in local_names
                  and m not in ("__future__",))


# ================================================================ 环境准备
def venv_python():
    exe = os.path.join(VENV_DIR, "Scripts", "python.exe")
    return exe if os.path.isfile(exe) else os.path.join(VENV_DIR, "bin", "python")


def available_modules(python_exe, modules):
    """返回该解释器上已可导入的依赖列表（逐个探测，避免一个缺失被误判为全部缺失）。"""
    if not modules:
        return []
    ok = []
    for m in modules:
        try:
            r = subprocess.run([python_exe, "-c", f"__import__({m!r})"],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=120)
            if r.returncode == 0:
                ok.append(m)
        except Exception:
            pass
    return ok


def candidate_interpreters():
    cands = []
    if os.environ.get("BUILD_PYTHON"):
        cands.append(os.environ["BUILD_PYTHON"])
    cands.append(sys.executable)
    for c in ("py -3", "py", "python3", "python"):
        cands.append(c)
    seen, out = set(), []
    for c in cands:
        if c and c not in seen and shutil.which(c.split()[0]):
            seen.add(c)
            out.append(c)
    return out


def ensure_venv(modules, force_python=None):
    """按「已具备依赖数量」挑选最合适的解释器，创建/复用 build/.venv。"""
    if os.path.isfile(venv_python()):
        log(f"复用已有虚拟环境: {VENV_DIR}")
        return venv_python()

    picks = [force_python] if force_python else candidate_interpreters()
    scored, seen = [], set()
    for cand in picks:
        cmd = cand.split() + ["-c", "import sys;print(sys.executable)"]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, text=True, timeout=60)
            if r.returncode != 0:
                continue
            exe = r.stdout.strip().splitlines()[-1]
            if not exe or not os.path.isfile(exe) or exe.lower() in seen:
                continue
            seen.add(exe.lower())
            have = available_modules(exe, modules)
            log(f"候选解释器 {exe}：已装依赖 {have or '无'}"
                f"（共需 {modules or '无'}）")
            scored.append((len(have), exe))
        except Exception:
            continue
    if not scored:
        raise SystemExit("[XX] 未找到可用的 Python 解释器，请用 --python 指定")
    base = max(scored, key=lambda x: x[0])[1]

    log(f"使用基础解释器: {base}")
    os.makedirs(BUILD_DIR, exist_ok=True)
    # --system-site-packages：能直接复用系统里装好的 pygame 等重型依赖
    cmd = [base, "-m", "venv", "--system-site-packages", VENV_DIR]
    if run(cmd, check=False).returncode != 0:      # 退化为不带系统包的纯净 venv
        log("带 --system-site-packages 创建失败，改用纯净虚拟环境", "WARN")
        run([base, "-m", "venv", VENV_DIR])
    return venv_python()


def install_deps(vpy, modules, use_venv=True):
    """安装 PyInstaller + 缺失依赖（装进 venv，绝不动全局环境）。"""
    target = [vpy, "-m", "pip", "install", "--disable-pip-version-check"]
    run(target[:-1] + ["--quiet", "--upgrade", "pip"], check=False)

    avail = set(available_modules(vpy, modules + ["PyInstaller"]))
    need = []
    if "PyInstaller" not in avail:
        need.append("pyinstaller")
    need += [IMPORT_TO_PIP.get(m, m) for m in modules if m not in avail]
    for extra in CONFIG["requirements"]:
        if extra not in need:
            need.append(extra)

    if not need:
        log("依赖已齐备，跳过安装", "OK")
        return
    log(f"需要安装: {', '.join(need)}")
    if not use_venv:
        log("警告：--no-venv 模式，包将被装进当前 Python 环境", "WARN")
    run(target + need)


# ================================================================ 打包
def build(args, vpy, entry, icon):
    cmd = [vpy, "-m", "PyInstaller",
           "--noconfirm", "--clean",
           "--name", args.name,
           "--distpath", DIST_DIR,
           "--workpath", os.path.join(BUILD_DIR, "work"),
           "--specpath", BUILD_DIR]
    cmd += ["--onefile"] if args.onefile else ["--onedir"]
    if not args.console:
        cmd.append("--windowed")          # --noconsole
    if icon:
        cmd += ["--icon", icon]
    for mod in CONFIG["excludes"]:
        cmd += ["--exclude-module", mod]
    for src, dst in CONFIG["extra_data"]:
        cmd += ["--add-data", f"{src}{os.pathsep}{dst}"]
    if CONFIG["upx"] and shutil.which("upx"):
        cmd += ["--upx-dir", os.path.dirname(shutil.which("upx"))]
    cmd.append(entry)

    run(cmd)
    exe = os.path.join(DIST_DIR, args.name + ".exe")
    if not os.path.isfile(exe):
        raise SystemExit(f"[XX] 未生成预期的 {exe}")
    size_mb = os.path.getsize(exe) / 1024 / 1024
    log(f"生成: {exe}  ({size_mb:.1f} MB)", "OK")
    return exe


def decode_best(data):
    """冻结程序不认 PYTHONIOENCODING，只能按字节兜底猜编码。"""
    if isinstance(data, str):
        return data
    for enc in ("utf-8", "gbk", "mbcs", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def smoke(exe):
    log("运行冒烟测试 ...")
    try:
        r = subprocess.run([exe] + CONFIG["smoke_args"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           env=sanitized_env({"PYTHONIOENCODING": "utf-8"}),
                           timeout=CONFIG["smoke_timeout"])
    except subprocess.TimeoutExpired:
        log(f"冒烟测试超时（{CONFIG['smoke_timeout']}s）", "WARN")
        return False
    out = decode_best(r.stdout or b"")
    if out.strip():
        for line in out.rstrip().splitlines():
            print("     " + line)
    ok = r.returncode == 0
    log(f"冒烟测试 {'通过' if ok else '失败'}（退出码 {r.returncode}）",
        "OK" if ok else "ERR")
    return ok


def make_zip(name, is_onefile):
    src = os.path.join(DIST_DIR, name + (".exe" if is_onefile else ""))
    if not os.path.exists(src):
        return None
    zpath = os.path.join(DIST_DIR, name)
    if is_onefile:                       # 单文件模式：先放进同名目录再压缩
        stage = os.path.join(BUILD_DIR, "zip", name)
        os.makedirs(stage, exist_ok=True)
        shutil.copy2(src, os.path.join(stage, name + ".exe"))
        shutil.make_archive(zpath, "zip", root_dir=os.path.dirname(stage),
                            base_dir=name)
    else:
        shutil.make_archive(zpath, "zip", root_dir=DIST_DIR, base_dir=name)
    log(f"压缩包: {zpath}.zip", "OK")
    return zpath + ".zip"


# ================================================================ 主流程
def main():
    p = argparse.ArgumentParser(description="PyInstaller 一键打包脚本")
    p.add_argument("--name", default=CONFIG["app_name"])
    p.add_argument("--entry", default=CONFIG["entry"])
    p.add_argument("--icon", default=CONFIG["icon"])
    p.add_argument("--onefile", dest="onefile", action="store_true",
                   default=CONFIG["onefile"])
    p.add_argument("--onedir", dest="onefile", action="store_false")
    p.add_argument("--console", action="store_true", default=CONFIG["console"])
    p.add_argument("--zip", action="store_true", default=CONFIG["zip"])
    p.add_argument("--smoke", action="store_true", default=CONFIG["smoke"])
    p.add_argument("--clean", action="store_true", help="先清理 build/ 与 dist/")
    p.add_argument("--no-venv", action="store_true", help="直接用当前解释器，不建 venv")
    p.add_argument("--python", default=None, help="指定基础解释器路径")
    args = p.parse_args()

    if args.clean:
        for d in (BUILD_DIR, DIST_DIR):
            if os.path.isdir(d):
                log(f"清理 {d}")
                shutil.rmtree(d, ignore_errors=True)

    entry = os.path.abspath(args.entry) if args.entry else find_entry()
    if not os.path.isfile(entry):
        raise SystemExit(f"[XX] 入口脚本不存在: {entry}")
    if not args.name:                    # 目录名 -> 驼峰应用名，如 mech-duel -> MechDuel
        raw = os.path.basename(PROJECT_DIR).replace("-", " ").replace("_", " ")
        args.name = "".join(w[:1].upper() + w[1:] for w in raw.split()) or "App"
    log(f"项目: {PROJECT_DIR}")
    log(f"入口: {os.path.relpath(entry, PROJECT_DIR)}")
    log(f"名称: {args.name}   模式: "
        f"{'单文件' if args.onefile else '单目录'}/{'控制台' if args.console else '窗口'}")

    icon = args.icon or find_icon()

    modules = detect_modules(entry)
    log(f"探测到第三方依赖: {', '.join(modules) if modules else '无'}")

    # 没有 .ico 但有 PNG 时，多装一个 pillow 用来现转图标
    if not icon and os.path.isfile(os.path.join(PROJECT_DIR, "preview.png")):
        if "pillow" not in CONFIG["requirements"]:
            CONFIG["requirements"].append("pillow")

    vpy = sys.executable if args.no_venv else ensure_venv(modules, args.python)
    log(f"构建环境: {vpy}")
    install_deps(vpy, modules, use_venv=not args.no_venv)

    # 图标转换放在装完依赖之后，此时 Pillow 才可用
    if not icon:
        png = os.path.join(PROJECT_DIR, "preview.png")
        if os.path.isfile(png):
            os.makedirs(BUILD_DIR, exist_ok=True)
            icon = make_icon_from_png(vpy, png, os.path.join(BUILD_DIR, "icon.ico"))
    if icon:
        log(f"图标: {os.path.relpath(icon, PROJECT_DIR)}")
    else:
        log("未找到图标，使用 PyInstaller 默认图标（可放 icon.ico 到项目根目录）", "WARN")

    exe = build(args, vpy, entry, icon)

    ok = True
    if args.smoke:
        ok = smoke(exe)
    if args.zip:
        make_zip(args.name, args.onefile)

    log(f"全部完成，用时 {time.time() - LOG_T0:.1f}s -> {exe}",
        "OK" if ok else "WARN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
