"""Roteiro do laboratório de falhas (executado pelo serviço demo-runner).

Cada passo imprime o que está verificando e encerra com código 1 se a verificação
não se confirmar dentro do prazo. Pode ser executado várias vezes: os monitores e o
destino são procurados pelo nome antes de serem criados.

Variáveis: PULSEOPS_DEMO_API, PULSEOPS_DEMO_TARGET, PULSEOPS_DEMO_RECEIVER,
PULSEOPS_DEMO_USERNAME e PULSEOPS_DEMO_PASSWORD.
"""

import os
import re
import sys
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx

T = TypeVar("T")
TOTAL_STEPS = 11
CSRF_FIELD = re.compile(r'name="csrf_token" value="([^"]+)"')

MAIN: dict[str, Any] = {
    "name": "Lab: serviço principal",
    "description": "Alvo controlado pelo roteiro da demonstração.",
    "url": "http://lab-target:8081/service",
    "method": "GET",
    "interval_seconds": 3,
    "timeout_seconds": 2,
    "accepted_status_codes": "200-299",
    "latency_threshold_ms": 800,
    "failure_threshold": 3,
    "recovery_threshold": 2,
}
STABLE: dict[str, Any] = {
    **MAIN,
    "name": "Lab: serviço estável",
    "description": "Responde sempre 200; serve de comparação no painel.",
    "url": "http://lab-target:8081/stable",
    "interval_seconds": 5,
}
DESTINATION = {"name": "Receptor do laboratório", "url": "http://lab-receiver:8082/webhook"}


class StepFailedError(Exception):
    pass


class Demo:
    def __init__(self, api: str, target: str, receiver: str) -> None:
        self.api = httpx.Client(base_url=api, timeout=10)
        self.target = httpx.Client(base_url=target, timeout=10)
        self.receiver = httpx.Client(base_url=receiver, timeout=10)
        self.csrf = ""

    # ---- saída e verificação -------------------------------------------------------

    @staticmethod
    def step(number: int, title: str) -> None:
        print(f"\n[{number}/{TOTAL_STEPS}] {title}", flush=True)

    @staticmethod
    def ok(message: str) -> None:
        print(f"    ok: {message}", flush=True)

    def expect(self, condition: bool, message: str) -> None:
        if not condition:
            raise StepFailedError(message)
        self.ok(message)

    @staticmethod
    def wait_for(description: str, probe: Callable[[], T | None], timeout: float) -> T:
        print(f"    aguardando: {description} (até {timeout:.0f} s)", flush=True)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = probe()
            if value:
                return value
            time.sleep(0.5)
        raise StepFailedError(f"tempo esgotado esperando: {description}")

    # ---- API do PulseOps -------------------------------------------------------------

    def login(self, username: str, password: str) -> None:
        page = self.api.get("/login")
        token = CSRF_FIELD.search(page.text)
        if not token:
            raise StepFailedError("página de login sem token CSRF")
        response = self.api.post(
            "/login",
            data={"username": username, "password": password, "csrf_token": token.group(1)},
        )
        if response.status_code != 303:
            raise StepFailedError(f"login recusado (HTTP {response.status_code})")
        token = CSRF_FIELD.search(self.api.get("/").text)
        if not token:
            raise StepFailedError("painel sem token CSRF depois do login")
        self.csrf = token.group(1)

    def get(self, path: str, **params: Any) -> Any:
        response = self.api.get(f"/api/v1{path}", params=params)
        response.raise_for_status()
        return response.json()

    def send(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        response = self.api.request(
            method, f"/api/v1{path}", json=body, headers={"X-CSRF-Token": self.csrf}
        )
        if response.status_code >= 400:
            raise StepFailedError(f"{method} {path}: HTTP {response.status_code} {response.text}")
        return response.json()

    def monitors_named(self, name: str) -> list[dict[str, Any]]:
        monitors: list[dict[str, Any]] = self.get("/monitors")
        return [m for m in monitors if m["name"].lower() == name.lower()]

    def ensure_monitor(self, spec: dict[str, Any], *, reset: bool) -> dict[str, Any]:
        found = self.monitors_named(spec["name"])
        if not found:
            created: dict[str, Any] = self.send("POST", "/monitors", spec)
            self.ok(f"monitor criado: {spec['name']} (id {created['id']})")
            return created
        monitor = found[0]
        self.send("PUT", f"/monitors/{monitor['id']}", spec)
        if monitor["state"] == "active" and reset:
            # Pausar fecha um incidente que tenha sobrado de execução anterior e zera a
            # contagem; retomar agenda a primeira verificação para já.
            self.send("POST", f"/monitors/{monitor['id']}/pause")
        if monitor["state"] == "paused" or reset:
            self.send("POST", f"/monitors/{monitor['id']}/resume")
        self.ok(f"monitor já existia e foi reaproveitado: {spec['name']} (id {monitor['id']})")
        refreshed: dict[str, Any] = self.get(f"/monitors/{monitor['id']}")
        return refreshed

    def ensure_destination(self) -> None:
        destinations: list[dict[str, Any]] = self.get("/destinations")
        for d in destinations:
            if d["name"] == DESTINATION["name"]:
                if not d["enabled"]:
                    self.send("PATCH", f"/destinations/{d['id']}", {"enabled": True})
                self.ok(f"destino de alerta já existia: {d['name']}")
                return
        self.send("POST", "/destinations", {**DESTINATION, "enabled": True})
        self.ok(f"destino de alerta criado: {DESTINATION['name']}")

    def checks_after(self, monitor_id: int, after_id: int) -> list[dict[str, Any]]:
        """Checks concluídos com id maior que `after_id`, do mais antigo ao mais novo."""
        page = self.get(f"/monitors/{monitor_id}/checks", limit=100)
        items = [c for c in page["items"] if c["id"] > after_id and c["outcome"] is not None]
        return sorted(items, key=lambda c: c["id"])

    def last_check_id(self, monitor_id: int) -> int:
        page = self.get(f"/monitors/{monitor_id}/checks", limit=1)
        return int(page["items"][0]["id"]) if page["items"] else 0

    def open_incidents(self, monitor_id: int) -> list[dict[str, Any]]:
        page = self.get("/incidents", status="open", monitor_id=monitor_id)
        items: list[dict[str, Any]] = page["items"]
        return items

    # ---- laboratório -----------------------------------------------------------------

    def set_target(self, mode: str) -> None:
        self.target.post("/control/mode", json={"mode": mode}).raise_for_status()
        self.ok(f"alvo do laboratório agora em modo '{mode}'")

    def set_receiver(self, available: bool) -> None:
        self.receiver.post(
            "/control/availability", json={"available": available}
        ).raise_for_status()
        self.ok(f"receptor de alertas {'disponível' if available else 'indisponível (503)'}")

    def received(self) -> dict[str, Any]:
        data: dict[str, Any] = self.receiver.get("/control/received").json()
        return data


def run(demo: Demo, username: str, password: str) -> None:
    demo.step(1, "Ambiente no ar: API pronta, banco acessível e worker ativo")
    ready = demo.api.get("/health/ready")
    demo.expect(ready.status_code == 200, f"/health/ready respondeu {ready.status_code}")
    demo.login(username, password)
    demo.ok(f"login como '{username}'")
    demo.wait_for("worker enviar sinal de vida", lambda: demo.get("/summary")["worker_alive"], 30)
    demo.ok("worker ativo segundo /api/v1/summary")

    demo.step(2, "Preparar monitores sem duplicar (idempotente)")
    demo.set_target("healthy")
    demo.set_receiver(True)
    demo.ensure_destination()
    main = demo.ensure_monitor(MAIN, reset=True)
    demo.ensure_monitor(STABLE, reset=False)
    for spec in (MAIN, STABLE):
        count = len(demo.monitors_named(spec["name"]))
        demo.expect(
            count == 1, f"existe exatamente 1 monitor '{spec['name']}' (encontrados {count})"
        )
    mid = main["id"]
    baseline = demo.last_check_id(mid)

    demo.step(3, "Verificações saudáveis")
    demo.wait_for(
        "2 checks com sucesso e saúde 'healthy'",
        lambda: (
            sum(c["outcome"] == "healthy" for c in demo.checks_after(mid, baseline)) >= 2
            and demo.get(f"/monitors/{mid}")["health"] == "healthy"
        ),
        30,
    )
    demo.ok(f"motivo exibido: {demo.get(f'/monitors/{mid}')['health_reason']}")
    demo.set_target("slow")
    mark = demo.last_check_id(mid)
    slow = demo.wait_for(
        "um check lento (acima de 800 ms, abaixo do timeout de 2 s)",
        lambda: [c for c in demo.checks_after(mid, mark) if c["outcome"] == "slow"],
        20,
    )
    monitor = demo.get(f"/monitors/{mid}")
    demo.expect(
        monitor["health"] == "degraded" and not demo.open_incidents(mid),
        f"lentidão ({slow[0]['duration_ms']} ms) deixa o monitor degradado sem abrir incidente",
    )

    demo.step(4, "Provocar uma falha (timeout)")
    demo.set_target("timeout")
    mark = demo.last_check_id(mid)
    demo.wait_for(
        "um check com resultado 'timeout'",
        lambda: [c for c in demo.checks_after(mid, mark) if c["outcome"] == "timeout"],
        20,
    )
    monitor = demo.get(f"/monitors/{mid}")
    demo.expect(not demo.open_incidents(mid), "uma falha isolada ainda não abre incidente")
    demo.ok(f"motivo exibido: {monitor['health_reason']}")

    demo.step(5, "Limiar de abertura: 3 falhas consecutivas confirmam o incidente")
    demo.set_target("error")
    incident = demo.wait_for("incidente aberto", lambda: demo.open_incidents(mid), 40)[0]
    demo.expect(
        incident["opening_reason"].startswith("Incidente confirmado após 3 falhas consecutivas"),
        f"motivo de abertura: {incident['opening_reason']}",
    )
    detail = demo.get(f"/incidents/{incident['id']}")
    kinds = [e["kind"] for e in detail["events"]]
    demo.expect(
        kinds[:2] == ["first_failure", "opened"],
        f"linha do tempo começa com primeira falha e confirmação: {kinds}",
    )
    demo.wait_for(
        "alerta incident.opened chegar ao receptor",
        lambda: f"incident:{incident['id']}:opened" in demo.received()["event_ids"],
        20,
    )
    demo.ok("receptor recebeu incident.opened")

    demo.step(6, "Falhas seguintes não abrem outro incidente")
    mark = demo.last_check_id(mid)
    demo.wait_for(
        "mais 2 checks com falha",
        lambda: sum(c["outcome"] == "unexpected_status" for c in demo.checks_after(mid, mark)) >= 2,
        20,
    )
    still_open = demo.open_incidents(mid)
    demo.expect(
        len(still_open) == 1 and still_open[0]["id"] == incident["id"],
        f"existe apenas UM incidente aberto (id {incident['id']})",
    )

    demo.step(7, "Restaurar o alvo")
    demo.set_target("healthy")
    mark = demo.last_check_id(mid)
    demo.wait_for(
        "1 check com sucesso",
        lambda: [c for c in demo.checks_after(mid, mark) if c["outcome"] == "healthy"],
        20,
    )
    monitor = demo.get(f"/monitors/{mid}")
    if demo.open_incidents(mid):
        demo.ok(f"um sucesso ainda não encerra: {monitor['health_reason']}")

    demo.step(8, "Recuperação: 2 sucessos consecutivos encerram o incidente")
    demo.wait_for("incidente resolvido", lambda: not demo.open_incidents(mid), 20)
    resolved = demo.get(f"/incidents/{incident['id']}")["incident"]
    demo.expect(resolved["status"] == "resolved", f"motivo: {resolved['resolution_explanation']}")
    demo.expect(demo.get(f"/monitors/{mid}")["health"] == "healthy", "monitor voltou a 'healthy'")
    demo.wait_for(
        "alerta incident.resolved chegar ao receptor",
        lambda: f"incident:{incident['id']}:resolved" in demo.received()["event_ids"],
        20,
    )
    demo.ok("receptor recebeu incident.resolved")

    demo.step(9, "Indisponibilizar o receptor de alertas e provocar novo incidente")
    demo.set_receiver(False)
    rejected_before = demo.received()["rejected"]
    demo.set_target("error")
    second = demo.wait_for("novo incidente aberto", lambda: demo.open_incidents(mid), 40)[0]
    event_id = f"incident:{second['id']}:opened"

    def failed_delivery() -> dict[str, Any] | None:
        for alert in demo.get(f"/incidents/{second['id']}")["alerts"]:
            for delivery in alert["deliveries"]:
                if alert["event_id"] == event_id and delivery["attempt_count"] >= 1:
                    return dict(delivery)
        return None

    delivery = demo.wait_for("tentativa de entrega recusada pelo receptor", failed_delivery, 20)
    demo.expect(
        delivery["status"] == "pending" and "503" in (delivery["last_error"] or ""),
        f"entrega pendente, último erro: {delivery['last_error']}",
    )
    demo.expect(demo.received()["rejected"] > rejected_before, "receptor registrou a recusa")

    demo.step(10, "O monitoramento continua com o receptor fora do ar")
    mark = demo.last_check_id(mid)
    demo.wait_for("mais 2 checks gravados", lambda: len(demo.checks_after(mid, mark)) >= 2, 20)
    demo.expect(
        event_id not in demo.received()["event_ids"],
        "checks continuam sendo gravados enquanto o alerta espera",
    )

    demo.step(11, "Restaurar o receptor e ver a retentativa entregar o alerta")
    demo.set_receiver(True)
    demo.wait_for(
        "entrega concluída",
        lambda: event_id in demo.received()["event_ids"],
        30,
    )
    final = next(
        d
        for a in demo.get(f"/incidents/{second['id']}")["alerts"]
        if a["event_id"] == event_id
        for d in a["deliveries"]
    )
    demo.expect(
        final["status"] == "delivered" and final["attempt_count"] >= 2,
        f"entregue na tentativa {final['attempt_count']}",
    )
    # Entrega "pelo menos uma vez": se o mesmo evento chegar de novo, o receptor o
    # reconhece pelo id e não processa duas vezes.
    payload = demo.received()
    repost = demo.receiver.post(
        "/webhook", json={"type": "incident.opened"}, headers={"X-PulseOps-Event-Id": event_id}
    ).json()
    after = demo.received()
    demo.expect(
        repost["duplicate"] and after["duplicates"] == payload["duplicates"] + 1,
        "reenvio do mesmo evento foi reconhecido como duplicado",
    )
    demo.set_target("healthy")
    print("\nDemonstração concluída: os 11 passos foram verificados.", flush=True)


def main() -> int:
    password = os.environ.get("PULSEOPS_DEMO_PASSWORD", "")
    if not password:
        print("erro: defina PULSEOPS_DEMO_PASSWORD (o scripts/demo.sh faz isso)", file=sys.stderr)
        return 2
    demo = Demo(
        os.environ.get("PULSEOPS_DEMO_API", "http://api:8000"),
        os.environ.get("PULSEOPS_DEMO_TARGET", "http://lab-target:8081"),
        os.environ.get("PULSEOPS_DEMO_RECEIVER", "http://lab-receiver:8082"),
    )
    try:
        run(demo, os.environ.get("PULSEOPS_DEMO_USERNAME", "demo"), password)
    except (StepFailedError, httpx.HTTPError) as exc:
        print(f"\nFALHOU: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
