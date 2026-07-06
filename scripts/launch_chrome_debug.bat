@echo off
REM ──────────────────────────────────────────────────────────────────
REM  launch_chrome_debug.bat
REM  Abre o Chrome com porta de depuracao remota (CDP) para o scraper
REM  Econet. Execute este arquivo ANTES de rodar scraper_econet_ncm_st.py
REM ──────────────────────────────────────────────────────────────────

SET DEBUG_PORT=9222
SET PROFILE_DIR=%TEMP%\ChromeDebugEconet
SET URL=https://www.econeteditora.com.br/

REM Localiza o executável do Chrome em paths comuns
SET CHROME=
IF EXIST "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    SET CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
) ELSE IF EXIST "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    SET CHROME="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
) ELSE IF EXIST "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    SET CHROME="%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

IF "%CHROME%"=="" (
    echo ERRO: Chrome nao encontrado. Instale o Chrome ou ajuste o caminho neste arquivo.
    pause
    exit /b 1
)

echo ─────────────────────────────────────────────────────
echo  Abrindo Chrome com depuracao na porta %DEBUG_PORT%
echo  Perfil temporario: %PROFILE_DIR%
echo ─────────────────────────────────────────────────────
echo.
echo  INSTRUCOES:
echo   1. Faca login no Econet com seu usuario e senha
echo   2. Resolva o captcha se solicitado
echo   3. Navegue ate: ICMS ^> Substituicao Tributaria
echo   4. Deixe esta janela aberta e execute o scraper:
echo      python scripts/scraper_econet_ncm_st.py
echo.
echo ─────────────────────────────────────────────────────

start "" %CHROME% ^
    --remote-debugging-port=%DEBUG_PORT% ^
    --user-data-dir="%PROFILE_DIR%" ^
    --no-first-run ^
    --no-default-browser-check ^
    %URL%

echo Chrome iniciado. Aguarde carregar e siga as instrucoes acima.
pause
