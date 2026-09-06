# -*- mode: python ; coding: utf-8 -*-
"""Local Hub 打包规格（onedir）。

用 onedir 而不是 onefile：onefile 每次启动都要把整包解压到临时目录，
Hub 是被桌面壳拉起的常驻进程，启动延迟会直接顶到用户脸上；
而且解压目录的 ACL 不受我们控制，与 W5 那套「运行时文件只留当前用户」的
校验冲突。

协议包必须显式收集：它的 registry / schema / fixtures 是**数据文件**，
PyInstaller 的静态分析看不见它们。漏掉的话打出来的 exe 能启动、
但一读错误码表就炸——这正是 W1 的 R1 同款坑（见
.hqagent/reviews/INT-smoke-W1xW5.md）。
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

HUB = Path(SPECPATH)

datas = collect_data_files("protocol", include_py_files=False)

a = Analysis(
    [str(HUB / "runtime" / "main.py")],
    pathex=[str(HUB)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # uvicorn 用字符串动态载入这些实现，静态分析看不到。
        # 少了 websockets 那层，/api/v1/events/stream 会退化成普通 HTTP
        # 被 Bearer 中间件拦成 401——测试套件发现不了，因为 Starlette
        # TestClient 在进程内自实现 WS。
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.protocols.websockets.websockets_sansio_impl",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespan.on",
        "uvicorn.loops.asyncio",
        # W2/W3 的包由 Composition Root 按名字装配，不是静态 import
        "adapters",
        "orchestrator",
        "security",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyInstaller"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hqagent-core",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="hqagent-core",
)
