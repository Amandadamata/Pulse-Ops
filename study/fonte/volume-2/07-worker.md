# D7 — Worker: o processo que verifica e avisa

## `src/pulseops/worker/runner.py`

**Finalidade.** A classe `Worker`: três laços (checks, entregas, manutenção) no
mesmo processo, em tarefas `asyncio` separadas, com limite de checks simultâneos.

**Dados.** Recebe sessões, verificador, notificador, relógio e configuração.
Produz linhas no banco (via serviços) e logs. **Relações.** Montado em
`worker/__main__.py`; usa `services/processing.py` e `services/alerts.py`.
**Testes.** `tests/integration/test_consistency.py`
(`test_worker_loop_survives_unreachable_database`,
`test_dispatcher_refills_freed_slots_without_waiting_a_tick`),
`test_slow_webhook_does_not_block_checks`, `test_maintenance_runs_retention` e
quase todos os testes de integração, que usam `run_checks_once` e
`run_deliveries_once`.

@@trecho src/pulseops/worker/runner.py 1-30

- Linhas 1–5: a docstring dá a razão dos três laços separados: um webhook lento não
  atrasa verificação nenhuma (RF06.3).
- Linha 29: até 10 entregas por rodada.
- Linha 30: a retenção roda no máximo uma vez por hora.

@@trecho src/pulseops/worker/runner.py 33-54

- Linhas 34–43: tudo é recebido pronto, com argumentos só nomeados (`*`).
- Linha 49: identificação `hostname:pid`, usada no heartbeat.
- Linha 51: o conjunto das tarefas de check em andamento. O tamanho dele é o número
  de vagas ocupadas.
- Linha 53: o evento "uma vaga abriu" (correção do bug B8).
- Linha 54: começa "uma hora atrás", para a retenção rodar logo na primeira
  manutenção.

@@trecho src/pulseops/worker/runner.py 58-100

- Linhas 58–65: interface pública que devolve só quantas foram reservadas.
- Linhas 67–75: calcula as vagas livres, reserva até esse número e cria uma tarefa
  por execução. `add_done_callback` registra uma função chamada quando a tarefa
  termina, com sucesso ou erro.
- Linhas 77–79: ao terminar, a tarefa sai do conjunto e o evento é sinalizado.
- Linhas 81–90: a espera depois de cada rodada (volume 1, H29). Se reservou menos que
  as vagas pedidas, não há fila: dorme o tick. Se preencheu tudo, espera uma vaga
  abrir, com o tick como limite (`wait_for` com `timeout`;
  `contextlib.suppress(TimeoutError)` ignora o estouro, que é normal aqui).
- Linhas 92–94: espera as tarefas em andamento; `return_exceptions=True` evita que
  a falha de uma interrompa a espera das outras.
- Linhas 96–100: usado nos testes: reserva, executa e espera tudo.

@@trecho src/pulseops/worker/runner.py 102-122

- Linha 103: contexto de log com monitor e `run_key`.
- Linhas 104–116: o verificador já trata os próprios erros; este `except` é a
  última barreira. Uma exceção vira observação de erro interno, não falha do alvo.
  `logger.exception` registra o *traceback*.
- Linhas 117–122: se a gravação falhar (banco fora do ar), só registra. O check fica
  `running`; a manutenção o marca como interrompido depois.

@@trecho src/pulseops/worker/runner.py 126-159

- Linhas 126–135: reserva até 10 entregas, com reserva valendo o timeout do webhook
  mais 30 s, e envia todas **em paralelo** (`gather`).
- Linhas 137–159: envia, grava o resultado e loga a tentativa (INFO se deu certo,
  WARNING se não).

@@trecho src/pulseops/worker/runner.py 163-188

- Linhas 163–176: heartbeat com "upsert": `INSERT ... ON CONFLICT (worker_id) DO
  UPDATE SET last_seen_at = ...`. A primeira vez insere; as seguintes atualizam.
- Linhas 178–188: a manutenção: heartbeat, checks abandonados e, a cada hora,
  retenção.

@@trecho src/pulseops/worker/runner.py 192-245

- Linhas 192–204: `run` executa os três laços até o evento `stop`. Depois de
  parar, espera os checks em andamento terminarem (desligamento gracioso: o
  resultado é gravado em vez de ficar `running`).
- Linhas 206–226: o laço de checks. Linha 209 limpa o evento antes de reservar.
  Linhas 213–221: erro (banco fora do ar) espera `tick × 2^falhas`, até 30 s, mas
  acorda na hora se receber `stop`. Linhas 222–226: espera o que vier primeiro, o
  fim da espera normal ou o sinal de parada, e cancela a outra tarefa.
- Linhas 228–245: o laço genérico das entregas e da manutenção, com o mesmo
  tratamento de erro. A espera usa `wait_for(stop.wait(), timeout=delay)`: dorme
  `delay`, mas acorda antes se `stop` for sinalizado.

**Falhas possíveis.** Banco indisponível: os laços registram, esperam e tentam de
novo (`test_worker_loop_survives_unreachable_database`). Um bug que lance exceção
fora desses `try` derrubaria o processo; o Compose o reinicia
(`restart: unless-stopped`).

## `src/pulseops/worker/__main__.py`

**Finalidade.** Ponto de entrada do processo (`python -m pulseops.worker`): monta
as peças, garante um worker só por banco e trata os sinais de parada.

**Dados.** Configuração do ambiente. **Relações.** É o comando do serviço `worker`
no `compose.yaml`. **Testes.** `try_acquire_worker_lock` em
`test_second_worker_is_refused`; o resto é exercitado pela demonstração e pelo job
`docker` do CI (a cobertura deste arquivo nos testes é baixa, 44%; volume 1, parte
G).

@@trecho src/pulseops/worker/__main__.py 24-49

- Linhas 24–25: a chave do advisory lock: os bytes de "PULS" como número.
- Linhas 28–32: tenta o lock (volume 1, parte F). O `commit` da linha 31 fecha a
  transação aberta pelo `SELECT`; o lock de sessão continua.
- Linhas 35–41: configuração, logs, engine com conexões suficientes (uma por check
  simultâneo, mais 5), sessões, relógio, política e `User-Agent`.
- Linhas 45–49: uma conexão dedicada segura o lock enquanto o processo vive (o
  `async with` só termina no fim). Se outro worker já tem o lock, registra o erro e
  sai com código 1.

@@trecho src/pulseops/worker/__main__.py 51-80

- Linhas 51–54: dois clientes HTTP protegidos: um para checks (tantas conexões
  quanto checks simultâneos) e outro para webhooks (10).
- Linhas 55–63: a composição de tudo.
- Linhas 65–68: `SIGINT` (Ctrl+C) e `SIGTERM` (`docker compose stop`) sinalizam o
  evento `stop`, em vez de matar o processo no meio de uma gravação.
- Linhas 69–73: roda até parar e fecha os clientes em qualquer caso.
- Linhas 74–76: fecha o engine (libera o lock) e sai com 0.
- Linhas 79–80: `asyncio.run(main())` e o código de saída para o sistema.

**Falhas possíveis.** Banco inacessível na inicialização: a conexão do lock falha
e o processo sai com erro; o Compose tenta de novo. Segundo worker: sai com código
1 e a mensagem "outro worker já está rodando neste banco; apenas um é suportado".
