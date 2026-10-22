# Ensaio de carga local

Gerado por `scripts/ensaio_carga.sh --monitors 200 --interval 10 --duration 120` em 2026-10-22T03:53Z.
Commit base: `e8d69d9`, com a correção do B8 aplicada (commitada logo em seguida).

## Máquina

- Sistema: Linux 6.18.44-fc-v140 x86_64
- CPUs visíveis: 4
- Memória total: 15.7 GiB
- Docker: 29.9.1
- Worker: concorrência 20 (padrão)

## Resultado

- Monitores: 200, intervalo de 10 s, alvo `http://lab-target:8081/stable`
- Janela medida: 120 s (após 10 s de aquecimento)
- Clientes consultando a API em paralelo: 4
- Checks esperados na janela: 2403; gravados: 2390
- Resultados: {'healthy': 2390}
- Atraso de início (started_at - scheduled_at): mediana 637 ms, p95 1037 ms, máximo 1168 ms
- Duração dos checks: mediana 36 ms, p95 60 ms
- Lacunas de cobertura registradas (primeiros 50 monitores): 0
- Worker ativo ao final: True
- API `/api/v1/monitors`: 2864 requisições, mediana 31 ms, p95 104 ms, máximo 161 ms
- API `/api/v1/summary`: 2865 requisições, mediana 20 ms, p95 82 ms, máximo 161 ms

## Uso de recursos (amostra única no meio da janela)

| Container | CPU | Memória |
|---|---|---|
| pulseops-demo-runner-run-468845e49577 | 15.32% | 29.53MiB / 15.71GiB |
| pulseops-worker-1 | 1.84% | 62.33MiB / 15.71GiB |
| pulseops-api-1 | 81.71% | 78.99MiB / 15.71GiB |
| pulseops-lab-receiver-1 | 34.03% | 36.95MiB / 15.71GiB |
| pulseops-lab-target-1 | 0.23% | 37.16MiB / 15.71GiB |
| pulseops-db-1 | 19.73% | 112MiB / 15.71GiB |
| pulseops-testdb | 0.00% | 105.7MiB / 15.71GiB |

## Comparação com a execução anterior à correção do B8

| Medida | Antes (`ensaio-de-carga-antes-B8.md`) | Depois |
|---|---|---|
| Checks gravados / esperados | 2239 / 2402 | 2390 / 2403 |
| Atraso de início, mediana | 7826 ms | 637 ms |
| Atraso de início, p95 | 9688 ms | 1037 ms |
| API `/api/v1/summary`, p95 | 41 ms | 82 ms |

O atraso restante (mediana perto de 0,6 s) vem do tick de 1 s do worker: um monitor
que vence entre dois ticks espera o próximo. A latência da API subiu porque o banco
passou a gravar cerca de 7% mais checks no mesmo tempo, e API, worker e banco dividem a
mesma máquina.

## Como ler

Os números valem para esta máquina, esta configuração e esta duração. Não indicam
capacidade máxima nem comportamento em produção; o alvo é local e responde em
poucos milissegundos, o que não acontece com APIs reais.
