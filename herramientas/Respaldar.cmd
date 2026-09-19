@echo off
rem Copia de seguridad de Mukuwareru, con doble clic.
rem
rem Deja el respaldo verificado en OneDrive y espera a que pulses una tecla, para
rem que la ventana no se cierre antes de poder leer si fue bien.

cd /d "%~dp0\.."
python herramientas\respaldar.py %*
echo.
pause
