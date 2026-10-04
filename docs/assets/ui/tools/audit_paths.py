"""Run from the repository root; generated evidence stays outside docs/."""
from pathlib import Path
import subprocess

ROOT = Path.cwd().resolve()
if not (ROOT / 'apps/desktop/src').is_dir():
    raise SystemExit('Run the screenshot tools from the repository root.')
TOOLS = Path(__file__).resolve().parent
OUT = ROOT / '.tmp/ui-audit'
OUT.mkdir(parents=True, exist_ok=True)
BASELINE = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
