# Instalación de gesaula desde el archivo wheel

## Requisitos

- Python 3.11 o posterior.
- Conexión a Internet durante la instalación, para que `pip` descargue
  PySide6 y las demás dependencias adecuadas para el sistema operativo.

Se recomienda instalar la aplicación en un entorno virtual. Sustituye
`gesaula-0.1.1-py3-none-any.whl` por la ruta real del archivo descargado.

## Windows

Abre PowerShell en la carpeta que contiene el archivo `.whl` y ejecuta:

```powershell
py -m venv .venv-gesaula
.venv-gesaula\Scripts\python.exe -m pip install --upgrade pip
.venv-gesaula\Scripts\python.exe -m pip install .\gesaula-0.1.1-py3-none-any.whl
.venv-gesaula\Scripts\gesaula.exe
```

En las siguientes ocasiones solo será necesario el último comando.

## Linux y macOS

Abre una terminal en la carpeta que contiene el archivo `.whl` y ejecuta:

```bash
python3 -m venv .venv-gesaula
.venv-gesaula/bin/python -m pip install --upgrade pip
.venv-gesaula/bin/python -m pip install ./gesaula-0.1.1-py3-none-any.whl
.venv-gesaula/bin/gesaula
```

En las siguientes ocasiones solo será necesario el último comando.

## Actualización

Para instalar una versión nueva sobre el mismo entorno virtual:

```text
python -m pip install --upgrade RUTA_AL_NUEVO_ARCHIVO.whl
```

Utiliza el ejecutable de Python del entorno virtual indicado en los ejemplos
anteriores.

## Desinstalación

La aplicación queda contenida en la carpeta `.venv-gesaula`. Para eliminarla,
desinstala primero el paquete con `python -m pip uninstall gesaula` o borra ese
entorno virtual si no lo utilizas para ninguna otra aplicación.
