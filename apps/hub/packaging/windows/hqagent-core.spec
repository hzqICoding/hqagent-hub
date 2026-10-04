# PyInstaller 6.22.3; explicit project resources, never user homes/credentials.
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

hub = Path(SPECPATH).resolve().parents[1]
root = hub.parents[1]
if Path(sys.prefix).resolve() != (root / '.venv').resolve():
    raise RuntimeError('Build only with this worktree .venv; global site-packages are not permitted')

datas = collect_data_files('protocol', includes=['registry/*.yaml', 'events/event-dictionary.md'])
datas += copy_metadata('keyring')
datas += [(str(hub / 'adapters/resources/pi/hub-guard.mjs'), 'adapters/resources/pi')]
hiddenimports = collect_submodules('uvicorn') + collect_submodules('keyring.backends')
hiddenimports += ['PIL.Image', 'PIL.PngImagePlugin', 'PIL.JpegImagePlugin',
                  'PIL.GifImagePlugin', 'PIL.WebPImagePlugin', 'segno',
                  'protocol.generated.python', 'tkinter', 'tkinter.filedialog']
a = Analysis([str(Path(SPECPATH) / 'core_entry.py')], pathex=[str(hub)],
             binaries=[], datas=datas, hiddenimports=hiddenimports,
             excludes=['pytest', '_pytest', 'server', 'IPython', 'matplotlib', 'numpy'],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='hqagent-core',
          debug=False, strip=False, upx=False, console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='hqagent-core')
