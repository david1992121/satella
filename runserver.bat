@echo off

if not "%~0"=="%~dp0.\%~nx0" (
     start /min cmd /c,"%~dp0.\%~nx0" %*
     exit
)

pushd %~dp0
python manage.py runserver 0.0.0.0:8000
popd

REM ���[�J���T�[�o�[�N���p�̃o�b�`�ł��B
REM �N������http://localhost:8000/�ŃA�N�Z�X�ł��܂��B
