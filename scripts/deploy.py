"""Despliegue a staging con smoke test y rollback automático.

Uso:
    python scripts/deploy.py IMAGEN_NUEVA [IMAGEN_ESTABLE] [--simular-fallo]

1. Levanta PostgreSQL y la versión estable actual (si existe).
2. Reemplaza la API por la imagen nueva y ejecuta el smoke test.
3. Si el smoke test falla, vuelve a la versión estable (rollback) y
   termina con código 1 para que el pipeline quede en rojo.

--simular-fallo (o SIMULAR_FALLO=true) despliega la imagen nueva con una
DATABASE_URL inválida para demostrar el rollback sin romper el código.

Solo usa la biblioteca estándar y el cliente de Docker: funciona igual en
Linux, macOS y Windows.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request

NET = "deploywatch-staging"
DB = "staging-db"
API = "staging-api"
HEALTH_URL = "http://localhost:8000/api/health"
BROKEN_DB_URL = "postgresql+psycopg://deploywatch@host-inexistente:5432/deploywatch"
EN_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"


def docker(*args: str, check: bool = True, quiet: bool = False) -> subprocess.CompletedProcess:
    out = subprocess.DEVNULL if quiet else None
    return subprocess.run(["docker", *args], check=check, stdout=out, stderr=out)


def grupo(titulo: str) -> None:
    print(f"::group::{titulo}" if EN_ACTIONS else f"\n-- {titulo}", flush=True)


def fin_grupo() -> None:
    if EN_ACTIONS:
        print("::endgroup::", flush=True)


def salida(resultado: str) -> None:
    """Expone el resultado al workflow (GITHUB_OUTPUT) si existe."""
    ruta = os.getenv("GITHUB_OUTPUT")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"resultado={resultado}\n")
    print(f"Resultado: {resultado}")


def iniciar_db(password: str) -> None:
    grupo("PostgreSQL de staging")
    docker("network", "create", NET, check=False, quiet=True)
    docker("rm", "-f", DB, check=False, quiet=True)
    docker("run", "-d", "--name", DB, "--network", NET,
           "-e", "POSTGRES_USER=deploywatch", "-e", f"POSTGRES_PASSWORD={password}",
           "-e", "POSTGRES_DB=deploywatch", "postgres:16-alpine", quiet=True)
    for _ in range(30):
        listo = docker("exec", DB, "pg_isready", "-U", "deploywatch", check=False, quiet=True)
        if listo.returncode == 0:
            print("PostgreSQL listo")
            fin_grupo()
            return
        time.sleep(1)
    fin_grupo()
    raise SystemExit("PostgreSQL no arrancó")


def arrancar_api(imagen: str, db_url: str) -> None:
    docker("rm", "-f", API, check=False, quiet=True)
    docker("run", "-d", "--name", API, "--network", NET, "-p", "8000:8000",
           "-e", f"DATABASE_URL={db_url}", imagen, quiet=True)


def smoke_test(intentos: int = 15) -> bool:
    for _ in range(intentos):
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=3) as r:
                if json.load(r).get("status") == "ok":
                    print(f"Smoke test OK: {HEALTH_URL}")
                    return True
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(2)
    print(f'Smoke test FALLÓ: {HEALTH_URL} no respondió {{"status":"ok"}}')
    logs = subprocess.run(["docker", "logs", "--tail", "5", API],
                          capture_output=True, text=True, check=False)
    print((logs.stdout + logs.stderr).strip())
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("nueva", help="imagen a desplegar")
    parser.add_argument("estable", nargs="?", default="", help="versión estable actual")
    parser.add_argument("--simular-fallo", action="store_true")
    args = parser.parse_args()
    simular = args.simular_fallo or os.getenv("SIMULAR_FALLO", "false") == "true"
    estable = args.estable

    password = secrets.token_hex(16)
    db_url = f"postgresql+psycopg://deploywatch:{password}@{DB}:5432/deploywatch"
    iniciar_db(password)

    if estable:
        grupo(f"Versión estable actual: {estable}")
        arrancar_api(estable, db_url)
        if not smoke_test():
            print("La versión estable no pasa el smoke test: no sirve como punto de rollback.")
            estable = ""
        fin_grupo()

    grupo(f"Desplegando versión nueva: {args.nueva}")
    if simular:
        print("SIMULAR_FALLO=true (DATABASE_URL inválida)")
    arrancar_api(args.nueva, BROKEN_DB_URL if simular else db_url)
    ok = smoke_test()
    fin_grupo()
    if ok:
        salida("desplegado")
        return 0

    if not estable:
        print("No hay versión estable a la que volver.")
        salida("fallido")
        return 1

    grupo(f"ROLLBACK a {estable}")
    arrancar_api(estable, db_url)
    smoke_test()
    fin_grupo()
    salida("rollback")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    sys.exit(main())
