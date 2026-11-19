"""Prueba de carga de DeployWatch con Locust.

Cada usuario virtual simula a alguien con el panel abierto: registra un repo
al entrar, consulta la lista con frecuencia y lo elimina al salir. No llama a
GitHub (solo se ejercitan la API y la base de datos).

Al terminar se aplica un quality gate: si la tasa de error o el percentil 95
de latencia superan los umbrales, Locust sale con código 1 y el job falla.
"""
import os
import uuid

from locust import HttpUser, between, events, task

MAX_FAIL_RATIO = float(os.getenv("LOAD_MAX_FAIL_RATIO", "0.01"))  # 1 %
MAX_P95_MS = float(os.getenv("LOAD_MAX_P95_MS", "500"))


class DashboardUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        name = f"carga/repo-{uuid.uuid4().hex[:10]}"
        response = self.client.post(
            "/api/repos", json={"url": name}, name="POST /api/repos"
        )
        self.repo_id = response.json().get("id") if response.ok else None

    @task(5)
    def list_repos(self):
        self.client.get("/api/repos", name="GET /api/repos")

    @task(1)
    def health(self):
        self.client.get("/api/health", name="GET /api/health")

    def on_stop(self):
        if self.repo_id:
            self.client.delete(f"/api/repos/{self.repo_id}", name="DELETE /api/repos/:id")


@events.quitting.add_listener
def quality_gate(environment, **_kwargs):
    total = environment.stats.total
    p95 = total.get_response_time_percentile(0.95) or 0
    print(
        f"Quality gate de carga: {total.num_requests} peticiones, "
        f"errores {total.fail_ratio:.2%} (máx {MAX_FAIL_RATIO:.0%}), "
        f"p95 {p95:.0f} ms (máx {MAX_P95_MS:.0f} ms)"
    )
    if total.num_requests == 0 or total.fail_ratio > MAX_FAIL_RATIO or p95 > MAX_P95_MS:
        print("Quality gate de carga: FALLA")
        environment.process_exit_code = 1
    else:
        print("Quality gate de carga: OK")
        environment.process_exit_code = 0
