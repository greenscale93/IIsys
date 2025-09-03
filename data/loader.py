# -*- coding: utf-8 -*-
import os, glob
import pandas as pd
from config import DATA_DIR

def load_dataframes():
    dfs = {}
    csv_paths = glob.glob(os.path.join(DATA_DIR, "*.csv"))
    for path in csv_paths:
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8", low_memory=False).fillna("")
        except Exception:
            df = pd.read_csv(path, sep=",", dtype=str, encoding="utf-8", low_memory=False).fillna("")
        dfs[name] = df
    return dfs