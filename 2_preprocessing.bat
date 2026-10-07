@echo off
title preprocessing.py - Pham Gia Huy B23DCAT131
cd /d %~dp0
.venv\Scripts\python.exe preprocessing.py --range=-1h --interval=1min
pause
