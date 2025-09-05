# -*- coding: utf-8 -*-
import os, glob
import pandas as pd
from config import DATA_DIR

def _read_csv_smart(path: str):
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        for sep in (";", ","):
            try:
                return pd.read_csv(path, sep=sep, dtype=str, encoding=enc, low_memory=False).fillna("")
            except Exception:
                continue
    return pd.read_csv(path, sep=";", dtype=str, encoding="utf-8", errors="replace", low_memory=False).fillna("")

def load_dataframes():
    dfs = {}
    for path in glob.glob(os.path.join(DATA_DIR, "*.csv")):
        name = os.path.splitext(os.path.basename(path))[0]
        dfs[name] = _read_csv_smart(path)
    return dfs