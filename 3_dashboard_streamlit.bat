@echo off
title Streamlit app.py - Pham Gia Huy B23DCAT131
cd /d %~dp0
.venv\Scripts\python.exe -m streamlit run app.py --browser.gatherUsageStats false
pause
