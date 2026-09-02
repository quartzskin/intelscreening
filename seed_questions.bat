@echo off
cd /d "%~dp0"
echo Seeding question bank...
py -3.12 seed_questions.py
pause
