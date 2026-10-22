"""Ensaio de carga local, modesto e reproduzível (executado dentro da rede do Compose).

Cria N monitores apontando para o alvo estável do laboratório, deixa o worker rodar
por um tempo fixo enquanto clientes consultam a API, e mede:
- checks gravados versus esperados;
- atraso de início (started_at - scheduled_at);
- resultados diferentes de "healthy" e erros internos;
- lacunas de cobertura registradas;
- latência da API (painel JSON e lista de monitores) sob essa carga.

Ao final, arquiva os monitores do ensaio. O resultado sai em Markdown na saída padrão.
Nada aqui extrapola capacidade: os números valem só para a máquina e a configuração
registradas no relatório.
"""

import argparse
import asyncio
import os
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from typing import Any

import httpx

CSRF_FIELD = re.compile(r'name="csrf_token" value="([^"]+)"')
PREFIX = "Carga "


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank, o mesmo critério do p95 do produto."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * p // 100))
    return ordered[int(rank) - 1]


async def login(client: httpx.AsyncClient, username: str, password: str) -> str:
    page = await client.get("/login")
    token = CSRF_FIELD.search(page.text)
    if not token:
        raise RuntimeError("página de login sem token CSRF")
    response = await client.post(
        "/login", data={"username": username, "password": password, "csrf_token": token.group(1)}
    )
    if response.status_code != 303:
        raise RuntimeError(f"login recusado: HTTP {response.status_code}")
    token = CSRF_FIELD.search((await client.get("/")).text)
    if not token:
        raise RuntimeError("painel sem token CSRF")
    return token.group(1)


async def prepare(client: httpx.AsyncClient, count: int, interval: int, target: str) -> list[int]:
    """Cria ou reaproveita os monitores do ensaio, todos reiniciados."""
    existing = {m["name"]: m for m in (await client.get("/api/v1/monitors")).json()}
    ids = []
    for n in range(count):
        name = f"{PREFIX}{n:03d}"
        body = {
            "name": name,
            "url": f"{target}/stable",
            "interval_seconds": interval,
            "timeout_seconds": 5,
            "latency_threshold_ms": 1000,
        }
        if name in existing:
            monitor_id = existing[name]["id"]
            (await client.put(f"/api/v1/monitors/{monitor_id}", json=body)).raise_for_status()
            if existing[name]["state"] == "active":
                await client.post(f"/api/v1/monitors/{monitor_id}/pause")
            (await client.post(f"/api/v1/monitors/{monitor_id}/resume")).raise_for_status()
        else:
            response = await client.post("/api/v1/monitors", json=body)
            response.raise_for_status()
            monitor_id = response.json()["id"]
        ids.append(monitor_id)
    return ids


async def sample_api(
    client: httpx.AsyncClient, stop: asyncio.Event, timings: dict[str, list[float]]
) -> None:
    paths = ["/api/v1/summary", "/api/v1/monitors"]
    i = 0
    while not stop.is_set():
        path = paths[i % len(paths)]
        i += 1
        started = time.perf_counter()
        response = await client.get(path)
        elapsed = (time.perf_counter() - started) * 1000
        key = path if response.status_code == 200 else f"{path} (HTTP {response.status_code})"
        timings.setdefault(key, []).append(elapsed)
        await asyncio.sleep(0.05)


async def collect(
    client: httpx.AsyncClient, ids: list[int], since: datetime, until: datetime
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for monitor_id in ids:
        response = await client.get(
            f"/api/v1/monitors/{monitor_id}/checks",
            params={"from": since.isoformat(), "to": until.isoformat(), "limit": 200},
        )
        response.raise_for_status()
        checks.extend(response.json()["items"])
    return checks


async def main_async(args: argparse.Namespace) -> int:
    api = os.environ.get("PULSEOPS_DEMO_API", "http://api:8000")
    target = os.environ.get("PULSEOPS_DEMO_TARGET", "http://lab-target:8081")
    async with httpx.AsyncClient(base_url=api, timeout=30) as client:
        csrf = await login(
            client,
            os.environ.get("PULSEOPS_DEMO_USERNAME", "demo"),
            os.environ["PULSEOPS_DEMO_PASSWORD"],
        )
        client.headers["X-CSRF-Token"] = csrf
        ids = await prepare(client, args.monitors, args.interval, target)

        # Aquecimento: a primeira rodada de todos os monitores sai de uma vez.
        await asyncio.sleep(args.interval)
        since = datetime.now(UTC)
        stop = asyncio.Event()
        timings: dict[str, list[float]] = {}
        samplers = [
            asyncio.create_task(sample_api(client, stop, timings)) for _ in range(args.api_clients)
        ]
        await asyncio.sleep(args.duration)
        stop.set()
        await asyncio.gather(*samplers)
        until = datetime.now(UTC)
        await asyncio.sleep(args.interval)  # deixa terminar os checks iniciados na janela

        checks = await collect(client, ids, since, until)
        summary = (await client.get("/api/v1/summary")).json()
        gaps = 0
        for monitor_id in ids[: min(len(ids), 50)]:
            metrics = (
                await client.get(
                    f"/api/v1/monitors/{monitor_id}/metrics",
                    params={"from": since.isoformat(), "to": until.isoformat()},
                )
            ).json()
            gaps += len(metrics["gaps"])

        for monitor_id in ids:
            await client.post(f"/api/v1/monitors/{monitor_id}/archive")

    window = (until - since).total_seconds()
    expected = args.monitors * window / args.interval
    completed = [c for c in checks if c["outcome"] is not None]
    lateness = [
        (
            datetime.fromisoformat(c["started_at"]) - datetime.fromisoformat(c["scheduled_at"])
        ).total_seconds()
        * 1000
        for c in completed
    ]
    durations = [c["duration_ms"] for c in completed if c["duration_ms"] is not None]
    outcomes: dict[str, int] = {}
    for c in completed:
        outcomes[c["outcome"]] = outcomes.get(c["outcome"], 0) + 1

    print(f"- Monitores: {args.monitors}, intervalo de {args.interval} s, alvo `{target}/stable`")
    print(f"- Janela medida: {window:.0f} s (após {args.interval} s de aquecimento)")
    print(f"- Clientes consultando a API em paralelo: {args.api_clients}")
    print(f"- Checks esperados na janela: {expected:.0f}; gravados: {len(completed)}")
    print(f"- Resultados: {outcomes}")
    if lateness:
        print(
            "- Atraso de início (started_at - scheduled_at): "
            f"mediana {statistics.median(lateness):.0f} ms, "
            f"p95 {percentile(lateness, 95):.0f} ms, máximo {max(lateness):.0f} ms"
        )
    if durations:
        print(
            f"- Duração dos checks: mediana {statistics.median(durations):.0f} ms, "
            f"p95 {percentile(durations, 95):.0f} ms"
        )
    print(f"- Lacunas de cobertura registradas (primeiros 50 monitores): {gaps}")
    print(f"- Worker ativo ao final: {summary['worker_alive']}")
    for path, values in sorted(timings.items()):
        print(
            f"- API `{path}`: {len(values)} requisições, mediana "
            f"{statistics.median(values):.0f} ms, p95 {percentile(values, 95):.0f} ms, "
            f"máximo {max(values):.0f} ms"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--monitors", type=int, default=200)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--duration", type=int, default=120)
    parser.add_argument("--api-clients", type=int, default=4)
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
