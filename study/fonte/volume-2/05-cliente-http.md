# D5 — Cliente HTTP: o verificador e o envio de webhooks

## `src/pulseops/checks/checker.py`

**Finalidade.** Faz **uma** requisição HTTP ao alvo e classifica o resultado numa
das oito categorias, com uma explicação curta.

**Dados.** Entrada: `CheckTarget`, montado pelo worker a partir das colunas do
monitor. Saída: `CheckObservation` (resultado, horários, duração em ms, status
HTTP ou nulo, explicação). Nunca levanta exceção. **Relações.** Criado em
`worker/__main__.py` com o cliente protegido; chamado por `worker/runner.py`; a
observação é gravada por `services/processing.py`. **Testes.**
`tests/unit/test_checker.py` (treze testes: saudável, lento, status inesperado,
rede e TLS, DNS, handshake TLS, prazo total, redirecionamento, destino bloqueado,
exceção inesperada, explicação sem URL, corpo não lido, método HEAD).

@@trecho src/pulseops/checks/checker.py 18-46

- Linhas 18–24: o que verificar. `accepted` já é o objeto de faixas, não o texto.
- Linhas 27–34: o que foi observado. `status_code` é nulo quando não houve
  resposta (timeout, conexão recusada).
- Linhas 37–40: o protocolo `Checker`. O worker depende dele, não de
  `HttpChecker`; um verificador de outro tipo (TCP, por exemplo) só precisaria ter
  esse método.
- Linhas 43–46: recebe o cliente HTTP e o relógio prontos (composição).

@@trecho src/pulseops/checks/checker.py 48-89

- Linhas 49–50: dois relógios. `now()` dá o horário para gravar; `monotonic()` mede
  a duração sem ser afetado por ajustes do relógio do sistema.
- Linhas 53–55: `asyncio.timeout` impõe um prazo **total**. O comentário explica:
  os timeouts do HTTPX valem por fase (conectar, escrever, ler); um alvo que
  responde devagar em cada fase poderia somar mais que o configurado. Ao estourar,
  a tarefa é cancelada e levanta `TimeoutError`.
- Linhas 56–61: `client.stream(...)` faz a requisição e devolve a resposta **sem
  ler o corpo**. `follow_redirects=False` é explícito (o cliente já não segue, mas
  aqui fica documentado).
- Linhas 62–63: guarda só o status. Ao sair do `async with`, a conexão é fechada
  sem baixar o corpo (RF02.4): um alvo que devolve 1 GB não consome banda nem
  memória do PulseOps.
- Linhas 64–66: classifica pelo status e pela duração.
- Linhas 67–77: cada tipo de erro vira uma categoria. A ordem importa: o
  `UnsafeDestinationError` (bloqueio SSRF na conexão) precisa ser tratado antes do
  genérico. A linha 75 é a última barreira: qualquer outra exceção é **erro
  interno**, nunca "o alvo caiu". `type(exc).__name__` registra só o nome da
  exceção, não a mensagem, que poderia conter a URL.
- Linhas 79–86: monta a observação. A duração é medida de novo no fim, então
  inclui também o tempo até a exceção.
- `:g` (linha 69) formata `5.0` como `5`.

@@trecho src/pulseops/checks/checker.py 91-132

- Linhas 91–105: `@staticmethod` porque não usa `self`. Primeiro o status
  (fora da lista é falha, mesmo se rápido), depois a duração (acima do limite é
  lento). A explicação traz o status e o tempo, nunca a URL.
- Linhas 108–123: o HTTPX embrulha exceções de baixo nível. Para saber se foi TLS
  ou DNS, é preciso olhar a **cadeia de causas**: certificado não confiável (linha
  111), outro erro TLS (113), DNS (116, `socket.gaierror`), conexão recusada (118),
  outras falhas de conexão (120), resposta HTTP inválida (121–122).
- Linhas 126–132: percorre `__cause__` (o `raise ... from ...`) ou `__context__`
  (exceção levantada durante o tratamento de outra). A condição
  `current not in chain` evita laço infinito se houver ciclo.

**Falhas possíveis.** A classificação por texto (`"SSL" in str(exc)`, `"refused"`)
depende das mensagens das bibliotecas; uma mudança de texto faria um erro TLS
aparecer como "falha de conexão". Continua sendo falha do alvo, só com a categoria
menos precisa.

## `src/pulseops/notifications/webhook.py`

**Finalidade.** Faz o POST de um evento de alerta para o destino e classifica o
resultado (sucesso, erro temporário, erro permanente).

**Dados.** Entrada: URL do destino (do banco), `event_id` (texto estável) e o
payload (JSON montado na criação do evento). Saída: `SendResult`. **Relações.**
Criado em `worker/__main__.py`; chamado por `Worker._deliver` em
`worker/runner.py`; o resultado é gravado por `services/alerts.py`. **Testes.**
`test_webhook_notifier_sends_event_id_and_classifies_errors`,
`test_webhook_timeout_is_retryable`, `test_blocked_destination_fails_permanently`
(`tests/integration/test_delivery.py`).

@@arquivo src/pulseops/notifications/webhook.py

- Linhas 13–14: o protocolo; os testes usam um notificador falso que só anota
  as chamadas.
- Linhas 33–35: uma função interna que calcula a duração e monta o resultado. Evita
  repetir o cálculo em cada `return`.
- Linha 38: valida a URL de novo **no envio**: a política pode ter mudado desde o
  cadastro (por exemplo, a demonstração foi desligada).
- Linhas 39–48: mesmo padrão do verificador: prazo total, `stream` sem ler o corpo,
  o JSON no corpo do pedido e o `event_id` também num header, para o destino poder
  deduplicar sem abrir o corpo.
- Linha 50: destino bloqueado é **permanente** (`True` no segundo argumento):
  repetir não muda nada.
- Linhas 51–54: timeout e erro de rede são temporários.
- Linhas 56–58: 2xx é sucesso; outro status é erro, permanente ou não conforme
  `is_permanent_status` (4xx, exceto 408 e 429).

**Falhas possíveis.** Uma exceção fora das três tratadas (um bug no próprio
notificador, por exemplo) sobe até `Worker._deliver`. Nesse caso nada é gravado,
a entrega fica `sending` e volta à fila quando a reserva vence; o laço de entregas
registra o erro e continua.
