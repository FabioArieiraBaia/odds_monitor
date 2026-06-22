@echo off
setlocal enabledelayedexpansion

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
set PYTHON_CMD=python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    :: Tentar o caminho padrao do usuario
    if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set PYTHON_CMD="%LocalAppData%\Programs\Python\Python311\python.exe"
    ) else if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
        set PYTHON_CMD="%LocalAppData%\Programs\Python\Python312\python.exe"
    ) else (
        echo [ERRO] Python foi instalado mas o caminho nao foi encontrado.
        exit /b 1
    )
)

echo [SETUP] Instalando bibliotecas do projeto...
%PYTHON_CMD% -m pip install --upgrade pip
%PYTHON_CMD% -m pip install -r requirements.txt

echo [SETUP] Instalando navegador invisivel (Playwright Chromium)...
%PYTHON_CMD% -m playwright install chromium

echo [SETUP] Configuracao concluida com sucesso!
exit /b 0
