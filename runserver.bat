@echo off

if not "%~0"=="%~dp0.\%~nx0" (
     start /min cmd /c,"%~dp0.\%~nx0" %*
     exit
)

pushd %~dp0
python manage.py runserver 0.0.0.0:8000
popd

REM ローカルサーバー起動用のバッチです。
REM 起動中はhttp://localhost:8000/でアクセスできます。
