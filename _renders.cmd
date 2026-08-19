@echo off
cd /d C:\Users\natha\Projects\boyd-clips
echo === PENA oL6lV6gCyOc:3047 === > logs\pena.log
python -u -m boydclips.cli run --case oL6lV6gCyOc:3047 >> logs\pena.log 2>&1
echo === PENA EXIT %ERRORLEVEL% === >> logs\pena.log
echo === BLACKBURN UXSXYgPa_bY:6900 === > logs\blackburn.log
python -u -m boydclips.cli run --case UXSXYgPa_bY:6900 >> logs\blackburn.log 2>&1
echo === BLACKBURN EXIT %ERRORLEVEL% === >> logs\blackburn.log
