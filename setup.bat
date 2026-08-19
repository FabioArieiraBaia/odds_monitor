@echo off
setlocal enabledelayedexpansion

set USER_DATA_DIR=%~1
if "%USER_DATA_DIR%"=="" set USER_DATA_DIR=%~dp0

echo [SETUP] Iniciando configuracao do ambiente...

:: Buscar executavel do Python real de forma inteligente
set SYSTEM_PYTHON=
setlocal enabledelayedexpansion

:: 1. Procurar em caminhos comuns do usuario (User Local)
for %%v in (313 312 311 310) do (
    if exist "!LocalAppData!\Programs\Python\Python%%v\python.exe" (
        set "SYSTEM_PYTHON=!LocalAppData!\Programs\Python\Python%%v\python.exe"
        goto :python_found
    )
)

:: 2. Procurar em caminhos globais (System-wide)
for %%v in (313 312 311 310) do (
    if exist "!ProgramFiles!\Python%%v\python.exe" (
        set "SYSTEM_PYTHON=!ProgramFiles!\Python%%v\python.exe"
        goto :python_found
    )
)

:: 3. Testar se o comando global 'python' funciona e nao e o alias da Microsoft Store
python --version >nul 2>&1
if !errorlevel! == 0 (
    :: Verificar se nao esta na pasta WindowsApps (alias de execucao)
    where python >temp_py_path.txt 2>&1
    if exist temp_py_path.txt (
        set /p PY_PATH=<temp_py_path.txt
        del temp_py_path.txt
        echo !PY_PATH! | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
            set "SYSTEM_PYTHON=python"
            goto :python_found
        )
    )
)

:python_not_found
echo [SETUP] Python nao encontrado no sistema. Baixando instalador...
curl -L -o "%USER_DATA_DIR%\python_installer.exe" https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
if not exist "%USER_DATA_DIR%\python_installer.exe" (
    echo [ERRO] Falha ao baixar o instalador do Python.
    exit /b 1
)

echo [SETUP] Instalando Python silenciosamente...
start /wait "" "%USER_DATA_DIR%\python_installer.exe" /passive InstallAllUsers=0 PrependPath=1 Include_test=0
del "%USER_DATA_DIR%\python_installer.exe"

:: Buscar novamente apos instalacao
for %%v in (311 312 313) do (
    if exist "!LocalAppData!\Programs\Python\Python%%v\python.exe" (
        set "SYSTEM_PYTHON=!LocalAppData!\Programs\Python\Python%%v\python.exe"
        goto :python_found
    )
)

echo [ERRO] Python foi instalado mas o executavel nao foi localizado.
exit /b 1

:python_found
echo [SETUP] Python localizado em: !SYSTEM_PYTHON!
:: Exportar variavel fora do escopo local
endlocal & set "SYSTEM_PYTHON=%SYSTEM_PYTHON%"


echo [SETUP] Criando ambiente virtual Python (venv)...
if exist "%USER_DATA_DIR%\venv" (
    echo [SETUP] venv ja existe. Atualizando...
) else (
    %SYSTEM_PYTHON% -m venv "%USER_DATA_DIR%\venv"
    if !errorlevel! neq 0 (
        echo [ERRO] Falha ao criar o ambiente virtual venv.
        exit /b 1
    )
)

:: Definir o comando do Python local do venv
set PYTHON_CMD="%USER_DATA_DIR%\venv\Scripts\python.exe"

echo [SETUP] Atualizando pip no ambiente virtual...
%PYTHON_CMD% -m pip install --upgrade pip

echo [SETUP] Instalando bibliotecas do projeto no venv...
%PYTHON_CMD% -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [ERRO] Falha ao instalar as dependencias no venv.
    exit /b 1
)

echo [SETUP] Instalando navegador invisivel (Playwright Chromium)...
%PYTHON_CMD% -m playwright install chromium
if !errorlevel! neq 0 (
    echo [ERRO] Falha ao instalar o Playwright Chromium.
    exit /b 1
)

echo [SETUP] Configuracao concluida com sucesso!
exit /b 0
