@echo off
chcp 65001 >nul
setlocal
rem 双击即可打包：调用同目录下的 build_exe.py
pushd "%~dp0"

set "PY="
for %%C in ("py -3" "py" "python" "python3") do (
    if not defined PY (
        %%C -c "import sys" >nul 2>&1 && set "PY=%%~C"
    )
)
if not defined PY (
    echo [XX] 未找到 Python，请先安装并加入 PATH
    goto :end
)

%PY% build_exe.py %*

:end
echo.
pause
popd
endlocal
