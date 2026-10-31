@echo off
set HERE=%~dp0..
set PYTHONPATH=%HERE%\src;%PYTHONPATH%
python -m edagov mcp
