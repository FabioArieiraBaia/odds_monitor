@echo off
setlocal enabledelayedexpansion

set USER_DATA_DIR=%~1
if "%USER_DATA_DIR%"=="" set USER_DATA_DIR=%~dp0

echo [SETUP] Iniciando configuracao do ambiente...

:: Verificar se o python ja existe
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [SETUP] Python nao encontrado. Baixando instalador...
    curl -o python_installer.exe https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
    if not exist python_installer.exe (
        echo [ERRO] Falha ao baixar o instalador do Python.
        exit /b 1
    )
    
    echo [SETUP] Instalando Python...
    start /wait python_installer.exe /passive InstallAllUsers=0 PrependPath=1 Include_test=0
    
    echo [SETUP] Instalacao concluida.
    del python_installer.exe
) else (
    echo [SETUP] Python ja esta instalado.
)

:: Definir caminho do Python (caso o PATH nao tenha sido atualizado na sessao atual do CMD)
set SYSTEM_PYTHON=python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    :: Tentar o caminho padrao do usuario
    if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set SYSTEM_PYTHON="%LocalAppData%\Programs\Python\Python311\python.exe"
    ) else if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
        set SYSTEM_PYTHON="%LocalAppData%\Programs\Python\Python312\python.exe"
    ) else (
        echo [ERRO] Python foi instalado mas o caminho nao foi encontrado.
        exit /b 1
    )
)

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
