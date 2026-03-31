import pandas as pd
import hashlib
import json
import tempfile
import time
import pickle
from pathlib import Path
from functools import wraps

CACHE_DIR = Path(tempfile.gettempdir()) / "powersim_cache"
CACHE_DIR.mkdir(exist_ok=True)

LAST_CLEANUP_FILE = CACHE_DIR / ".last_cleanup"

def _build_cache_key(func_name, args, kwargs):
    payload = {
        "func": func_name,
        "args": args,
        "kwargs": kwargs
    }
    payload_json = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.md5(payload_json.encode()).hexdigest()

def _cleanup_cache(ttl_seconds):
    now = time.time()
    if LAST_CLEANUP_FILE.exists():
        last_cleanup = float(LAST_CLEANUP_FILE.read_text())
        if now - last_cleanup < ttl_seconds:
            return  # no toca limpiar todavía

    # eliminar archivos expirados
    for file in CACHE_DIR.glob("*.pkl"):
        age = now - file.stat().st_mtime
        if age > ttl_seconds:
            try:
                file.unlink()
            except Exception:
                pass

    LAST_CLEANUP_FILE.write_text(str(now))

def df_cache(ttl_seconds=86400):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            _cleanup_cache(ttl_seconds)

            key = _build_cache_key(func.__name__, args, kwargs)
            cache_file = CACHE_DIR / f"{func.__name__}_{key}.pkl"

            if cache_file.exists():
                age = time.time() - cache_file.stat().st_mtime
                if age < ttl_seconds:
                    # print("Loading dataframe from cache")
                    with open(cache_file, "rb") as f:
                        return pickle.load(f)

            # print("Cache miss → executing function")
            df = func(*args, **kwargs)

            if not isinstance(df, pd.DataFrame):
                raise TypeError("df_cache solo soporta funciones que devuelven DataFrame")

            with open(cache_file, "wb") as f:
                pickle.dump(df, f)

            return df
        
        return wrapper
    
    return decorator