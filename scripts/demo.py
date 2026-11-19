"""Demostración local del pipeline completo de DeployWatch (requiere Docker).

Uso:
    python scripts/demo.py [paso]

Pasos:
    pruebas     lint, pruebas y quality gate de cobertura (80 %)
    despliegue  construye la imagen y la despliega en staging con smoke test
    rollback    despliega una versión con configuración rota: rollback automático
    carga       prueba de carga con Locust contra staging (límites de p95 y errores)
    iac         LocalStack + CloudFormation: cola SQS y bucket S3, publica y lee eventos
    limpiar     elimina los contenedores de la demo
    todo        todos los pasos anteriores en orden (por defecto)

Funciona en Linux, macOS y Windows (con Docker Desktop). La primera vez crea
un entorno virtual en .venv-demo con las dependencias fijadas por hash.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
VENV = RAIZ / ".venv-demo"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
IMG = "deploywatch-backend"
LOCALSTACK = "deploywatch-localstack"
LOCALSTACK_IMG = ("localstack/localstack:4.14@sha256:"
                  "3ebc37595918b8accb852f8048fef2aff047d465167edd655528065b07bc364a")


def titulo(texto: str) -> None:
    print(f"\n=== {texto} ===", flush=True)


def run(*cmd: str | Path, check: bool = True, quiet: bool = False) -> int:
    out = subprocess.DEVNULL if quiet else None
    r = subprocess.run([str(c) for c in cmd], cwd=RAIZ, stdout=out, stderr=out, check=False)
    if check and r.returncode != 0:
        raise SystemExit(f"Falló: {' '.join(str(c) for c in cmd)}")
    return r.returncode


def docker_salida(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=False).stdout


def puertos_libres(*puertos: int) -> None:
    for linea in docker_salida("ps", "--format", "{{.Names}} {{.Ports}}").splitlines():
        nombre = linea.split(" ", 1)[0]
        if nombre.startswith("staging-") or nombre == LOCALSTACK:
            continue
        for p in puertos:
            if f":{p}->" in linea:
                raise SystemExit(f"El puerto {p} está ocupado por {nombre}. Detenlo con: docker stop {nombre}")


def entorno_python() -> None:
    if PY.exists():
        return
    titulo(f"Preparando entorno Python ({VENV.name})")
    run(sys.executable, "-m", "venv", VENV)
    for req in ("requirements-dev.txt", "requirements-load.txt", "requirements-infra.txt"):
        run(PY, "-m", "pip", "install", "-q", "--only-binary", ":all:", "--require-hashes", "-r", req)


def health() -> str:
    try:
        with urllib.request.urlopen("http://localhost:8000/api/health", timeout=3) as r:
            return json.dumps(json.load(r))
    except (urllib.error.URLError, OSError, ValueError):
        return ""


def pruebas() -> None:
    entorno_python()
    titulo("1. Lint (ruff)")
    run(PY, "-m", "ruff", "check", "app", "tests", "load", "scripts", "infra")
    titulo("2. Pruebas + quality gate de cobertura (80 %)")
    run(PY, "-m", "coverage", "run", "-m", "pytest", "-q", "-p", "no:warnings")
    run(PY, "-m", "coverage", "report", "--fail-under=80", "--format=total")
    print("% de cobertura total (mínimo exigido: 80 %)")


def imagenes() -> None:
    titulo("Construyendo la imagen Docker")
    run("docker", "build", "-q", "-t", f"{IMG}:nueva", ".", quiet=True)
    if run("docker", "image", "inspect", f"{IMG}:stable", check=False, quiet=True) != 0:
        run("docker", "tag", f"{IMG}:nueva", f"{IMG}:stable")  # primera vez


def despliegue() -> None:
    puertos_libres(8000)
    imagenes()
    titulo("3. Despliegue a staging con smoke test")
    run(sys.executable, "scripts/deploy.py", f"{IMG}:nueva", f"{IMG}:stable")
    run("docker", "tag", f"{IMG}:nueva", f"{IMG}:stable")
    print(f"Promovida: {IMG}:nueva ahora es {IMG}:stable")


def rollback() -> None:
    puertos_libres(8000)
    imagenes()
    titulo("4. Despliegue con configuración rota: rollback automático")
    codigo = run(sys.executable, "scripts/deploy.py", f"{IMG}:nueva", f"{IMG}:stable",
                 "--simular-fallo", check=False)
    if codigo == 0:
        raise SystemExit("Inesperado: el despliegue roto pasó el smoke test")
    activa = docker_salida("inspect", "-f", "{{.Config.Image}}", "staging-api").strip()
    print("El script terminó con error (como en el CD) y staging sigue sirviendo:")
    print(f"  imagen activa: {activa}")
    print(f"  /api/health:   {health()}")


def carga() -> None:
    entorno_python()
    if not health():
        despliegue()
    titulo("5. Prueba de carga con Locust (20 usuarios, 20 s)")
    informe = RAIZ / "locust-report.html"
    run(PY, "-m", "locust", "-f", "load/locustfile.py", "--headless", "-u", "20", "-r", "10",
        "-t", "20s", "--host", "http://localhost:8000", "--only-summary", "--html", informe)
    print(f"Informe HTML: {informe}")


def iac() -> None:
    entorno_python()
    titulo("6. Infraestructura como código (LocalStack + CloudFormation)")
    if LOCALSTACK not in docker_salida("ps", "--format", "{{.Names}}").split():
        puertos_libres(4566)
        run("docker", "rm", "-f", LOCALSTACK, check=False, quiet=True)
        run("docker", "run", "-d", "--name", LOCALSTACK, "-p", "127.0.0.1:4566:4566",
            "-e", "SERVICES=cloudformation,sqs,s3", LOCALSTACK_IMG, quiet=True)
    run(PY, "infra/localstack.py", "aplicar", "staging")
    print("Aplicar de nuevo no cambia nada (idempotencia):")
    run(PY, "infra/localstack.py", "aplicar", "staging")
    run(PY, "infra/localstack.py", "publicar", "desplegado", f"demo-{int(time.time())}", f"{IMG}:nueva")
    run(PY, "infra/localstack.py", "leer", "staging")


def limpiar() -> None:
    titulo("Limpiando contenedores de la demo")
    run("docker", "rm", "-f", "staging-api", "staging-db", LOCALSTACK, check=False, quiet=True)
    run("docker", "network", "rm", "deploywatch-staging", check=False, quiet=True)
    print("Listo.")


PASOS = {f.__name__: f for f in (pruebas, despliegue, rollback, carga, iac, limpiar)}

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    paso = sys.argv[1] if len(sys.argv) > 1 else "todo"
    if paso == "todo":
        for f in PASOS.values():
            f()
    elif paso in PASOS:
        PASOS[paso]()
    else:
        print(__doc__)
        sys.exit(2)
