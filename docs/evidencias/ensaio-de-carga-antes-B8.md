# Ensaio de carga local (antes da correção do bug B8)

Guardado como evidência do bug B8 (`docs/registro-de-bugs.md`): com 200 monitores
a cada 10 s, os checks começavam quase um intervalo inteiro atrasados. O resultado
depois da correção está em `ensaio-de-carga.md`.

Gerado por `scripts/ensaio_carga.sh --monitors 200 --interval 10 --duration 120` em 2026-10-22T03:47Z.
Commit: `e8d69d9` (sem a correção do B8).

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
- Checks esperados na janela: 2402; gravados: 2239
- Resultados: {'healthy': 2239}
- Atraso de início (started_at - scheduled_at): mediana 7826 ms, p95 9688 ms, máximo 9750 ms
- Duração dos checks: mediana 39 ms, p95 81 ms
- Lacunas de cobertura registradas (primeiros 50 monitores): 0
- Worker ativo ao final: True
- API `/api/v1/monitors`: 3263 requisições, mediana 19 ms, p95 41 ms, máximo 144 ms
- API `/api/v1/summary`: 3264 requisições, mediana 17 ms, p95 41 ms, máximo 139 ms

## Uso de recursos (amostra única no meio da janela)

| Container | CPU | Memória |
|---|---|---|
| pulseops-demo-runner-run-a0092cd08fa5 | 17.77% | 31.23MiB / 15.71GiB |
| pulseops-api-1 | 68.12% | 74.61MiB / 15.71GiB |
| pulseops-worker-1 | 17.29% | 62.74MiB / 15.71GiB |
| pulseops-lab-receiver-1 | 0.17% | 37.42MiB / 15.71GiB |
| pulseops-lab-target-1 | 0.77% | 36.83MiB / 15.71GiB |
| pulseops-db-1 | 27.14% | 111MiB / 15.71GiB |
| pulseops-testdb | 0.00% | 105.7MiB / 15.71GiB |

## Como ler

Os números valem para esta máquina, esta configuração e esta duração. Não indicam
capacidade máxima nem comportamento em produção; o alvo é local e responde em
poucos milissegundos, o que não acontece com APIs reais.
