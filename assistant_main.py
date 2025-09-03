# -*- coding: utf-8 -*-
import sys, os
scripts_dir = r"C:\RAGOS\scripts"
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from app.main import main

if __name__ == "__main__":
    main()