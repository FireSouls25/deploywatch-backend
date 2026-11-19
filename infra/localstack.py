"""Infraestructura de eventos de despliegue sobre LocalStack (emulador de AWS).

Uso:
    python infra/localstack.py aplicar  [staging|production]
    python infra/localstack.py publicar RESULTADO SHA IMAGEN [staging|production]
    python infra/localstack.py leer     [staging|production]

aplicar   despliega infra/stack.yml con CloudFormation. Es idempotente: si la
          plantilla no cambió, no modifica nada.
publicar  registra un despliegue: mensaje en SQS y reporte JSON en S3.
leer      muestra los eventos en cola y los reportes guardados.

Siempre apunta a LocalStack con credenciales de prueba e ignora cualquier
perfil o credencial real de AWS de la máquina. Requiere boto3
(requirements-infra.txt). Funciona en Linux, macOS y Windows.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

# Aislar de la configuración real de AWS antes de importar boto3.
for var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN"):
    os.environ.pop(var, None)
_vacio = str(Path(tempfile.gettempdir()) / "deploywatch-sin-config-aws")
os.environ["AWS_CONFIG_FILE"] = _vacio
os.environ["AWS_SHARED_CREDENTIALS_FILE"] = _vacio

import boto3
from botocore.exceptions import ClientError

ENDPOINT = os.getenv("LOCALSTACK_URL", "http://localhost:4566")
REGION = "us-east-1"
PLANTILLA = Path(__file__).with_name("stack.yml")


def cliente(servicio: str):
    return boto3.client(
        servicio, endpoint_url=ENDPOINT, region_name=REGION,
        aws_access_key_id="test", aws_secret_access_key="test",
    )


def esperar_localstack(segundos: int = 60) -> None:
    limite = time.time() + segundos
    while time.time() < limite:
        try:
            with urllib.request.urlopen(f"{ENDPOINT}/_localstack/health", timeout=3):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(2)
    raise SystemExit(f"LocalStack no responde en {ENDPOINT}")


def aplicar(entorno: str = "staging") -> None:
    esperar_localstack()
    cf = cliente("cloudformation")
    stack = f"deploywatch-{entorno}"
    params = {
        "StackName": stack,
        "TemplateBody": PLANTILLA.read_text(encoding="utf-8"),
        "Parameters": [{"ParameterKey": "Entorno", "ParameterValue": entorno}],
    }
    try:
        cf.describe_stacks(StackName=stack)
        existe = True
    except ClientError:
        existe = False

    try:
        if existe:
            cf.update_stack(**params)
            cf.get_waiter("stack_update_complete").wait(StackName=stack, WaiterConfig={"Delay": 2})
            print(f"Stack {stack} actualizado")
        else:
            cf.create_stack(**params)
            cf.get_waiter("stack_create_complete").wait(StackName=stack, WaiterConfig={"Delay": 2})
            print(f"Stack {stack} creado")
    except ClientError as exc:
        if "No updates are to be performed" not in str(exc):
            raise
        print(f"Sin cambios: el stack {stack} ya coincide con la plantilla")

    salidas = cf.describe_stacks(StackName=stack)["Stacks"][0].get("Outputs", [])
    for o in salidas:
        print(f"  {o['OutputKey']}: {o['OutputValue']}")


def _cola(entorno: str) -> str:
    return cliente("sqs").get_queue_url(QueueName=f"deploywatch-{entorno}-deploy-events")["QueueUrl"]


def publicar(resultado: str, sha: str, imagen: str, entorno: str = "staging") -> None:
    evento = {
        "resultado": resultado, "sha": sha, "imagen": imagen, "entorno": entorno,
        "fecha": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    cuerpo = json.dumps(evento, ensure_ascii=False)
    cliente("sqs").send_message(QueueUrl=_cola(entorno), MessageBody=cuerpo)
    cliente("s3").put_object(
        Bucket=f"deploywatch-{entorno}-deploy-reports", Key=f"despliegues/{sha}.json",
        Body=cuerpo.encode("utf-8"), ContentType="application/json",
    )
    print(f"Evento registrado: {cuerpo}")


def leer(entorno: str = "staging") -> None:
    print(f"== Cola deploywatch-{entorno}-deploy-events")
    mensajes = cliente("sqs").receive_message(
        QueueUrl=_cola(entorno), MaxNumberOfMessages=10, VisibilityTimeout=0, WaitTimeSeconds=1,
    ).get("Messages", [])
    for m in mensajes:
        print(f"  {m['Body']}")
    print(f"== Bucket deploywatch-{entorno}-deploy-reports")
    objetos = cliente("s3").list_objects_v2(
        Bucket=f"deploywatch-{entorno}-deploy-reports", Prefix="despliegues/",
    ).get("Contents", [])
    for o in objetos:
        print(f"  {o['Key']}  {o['Size']} bytes")


COMANDOS = {"aplicar": aplicar, "publicar": publicar, "leer": leer}

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    if len(sys.argv) < 2 or sys.argv[1] not in COMANDOS:
        print(__doc__)
        sys.exit(2)
    COMANDOS[sys.argv[1]](*sys.argv[2:])
