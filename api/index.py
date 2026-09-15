import os
import shutil
import sys
from pathlib import Path

# Add project root and src/ to sys.path so cloud_bean packages are importable
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

# Change working directory to ROOT_DIR so relative paths resolve cleanly
os.chdir(str(ROOT_DIR))

# On Vercel serverless functions, the container filesystem is read-only except /tmp.
tmp_db = Path("/tmp/state.db")
bundled_db = ROOT_DIR / ".cloud-bean" / "state.db"

if not tmp_db.exists() and bundled_db.exists():
    try:
        shutil.copy2(bundled_db, tmp_db)
    except Exception as e:
        print(f"Warning: could not copy bundled state.db to /tmp: {e}")

os.environ["CLOUD_BEAN_STATE_DB"] = str(tmp_db)

from cloud_bean.api.app import create_server_app

app = create_server_app()
