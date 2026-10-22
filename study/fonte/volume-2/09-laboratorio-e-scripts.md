# D9 — Laboratório de falhas e scripts

O laboratório tem três peças: um **alvo** que obedece a comandos (fica lento, dá
erro, demora demais), um **receptor** de webhooks que pode "cair" e um **roteiro**
que provoca as falhas e confere, passo a passo, o que o PulseOps fez. Tudo roda
dentro da rede do Compose; nada disso é publicado no seu computador.

## `lab/__init__.py`

Uma linha: a docstring que diz para que serve o pacote. Existe para
`uvicorn lab.target:app` encontrar o módulo.

## `lab/target.py`

**Finalidade.** O alvo controlável dos monitores da demonstração.

**Dados.** Recebe o modo por `POST /control/mode`. Responde em `/service` conforme o
modo e conta as requisições. **Relações.** Serviço `lab-target` do
`compose.demo.yaml`; o roteiro `scripts/demo_flow.py` troca o modo. **Testes.** Não
há teste unitário; ele é exercitado pelo roteiro inteiro, que roda no job `docker`
do CI.

@@arquivo lab/target.py

- Linhas 1–12: a docstring descreve os quatro modos e os endpoints.
- Linhas 21–23: `Literal` restringe o modo a quatro textos (um valor diferente dá
  422). 1,5 s fica acima do limite de lentidão da demonstração (800 ms) e abaixo do
  timeout (2 s), então o resultado é `slow`. 30 s fica muito acima do timeout, então
  o resultado é `timeout`.
- Linhas 25–27: o estado fica em `app.state`, na memória do processo. Reiniciar o
  contêiner volta ao modo `healthy`.
- Linhas 34–44: `api_route` aceita `GET` e `HEAD`, os dois métodos que um monitor pode
  usar. `asyncio.sleep` espera sem bloquear o processo, então outras requisições
  continuam sendo atendidas durante a espera.
- Linhas 47–49: o monitor de comparação, que nunca falha.
- Linhas 52–60: os controles. Não há autenticação: só são alcançáveis de dentro da
  rede do Compose, porque o serviço não publica portas.

**Falhas possíveis.** Se o contêiner não subir, o `healthcheck` (que consulta
`/control/state`) falha, e o `demo-runner` não começa.

## `lab/receiver.py`

**Finalidade.** Um receptor de webhooks que se comporta como um receptor real
deveria: **deduplica** pelo id do evento e pode ser posto "fora do ar".

**Dados.** Recebe `POST /webhook` com o cabeçalho `X-PulseOps-Event-Id`. Guarda os
eventos na memória. **Relações.** Serviço `lab-receiver`; destino de alerta criado
pelo roteiro. **Testes.** `tests/unit/test_lab_receiver.py`
(`test_duplicate_event_is_detected`, `test_unavailable_receiver_rejects_then_accepts`,
`test_missing_event_id_is_rejected`).

@@arquivo lab/receiver.py

- Linhas 17–32: a classe `Inbox` guarda os eventos por id. `receive` devolve `False`
  quando o id já foi visto, e conta a duplicata. É o lado do receptor da entrega
  "pelo menos uma vez" (ADR 0007): o PulseOps pode reenviar, e quem recebe ignora o
  repetido.
- Linhas 46–48: indisponível responde 503 e conta a recusa. O PulseOps trata 503
  como erro temporário e tenta de novo.
- Linhas 49–50: sem o id, 400. Um erro 4xx é permanente para o PulseOps, que não
  tentaria de novo; no laboratório isso nunca acontece, porque o PulseOps sempre
  manda o cabeçalho.
- Linhas 51–53: aceita com 200 mesmo quando é duplicado, e diz isso na resposta.
  Responder erro a um duplicado faria o remetente tentar de novo à toa.
- Linhas 62–70: o que o roteiro consulta para conferir as entregas.

## `scripts/demo.sh`

**Finalidade.** O comando único do laboratório: sobe o ambiente, garante a
operadora da demonstração e executa o roteiro.

**Relações.** Usa `compose.yaml` e `compose.demo.yaml`; é o passo principal do job
`docker` do CI. **Testes.** O próprio CI.

@@arquivo scripts/demo.sh

- Linha 7: `set -euo pipefail`: para no primeiro erro (`-e`), trata variável não
  definida como erro (`-u`) e considera falha de qualquer comando num *pipe*
  (`pipefail`).
- Linha 9: muda para a raiz do projeto, qualquer que seja a pasta de onde o script
  foi chamado.
- Linha 10: o comando do Compose num *array* do Bash, para não repetir os arquivos e
  o perfil. `"${COMPOSE[@]}"` expande cada item como um argumento separado.
- Linhas 12–15: `--down` derruba os contêineres sem `-v`, então o volume do banco é
  mantido.
- Linhas 17–23: a senha da operadora é gerada **uma vez**, com 18 bytes aleatórios,
  e guardada em `.demo/admin-password`, que está no `.gitignore`. `chmod 600`: só o
  dono lê. Rodar de novo reaproveita a mesma senha.
- Linha 29: `--wait` espera todos os *healthchecks* passarem antes de seguir.
- Linhas 31–33: a senha vai pela entrada padrão (`--password-stdin`), não como
  argumento, porque argumentos aparecem na lista de processos. `--exists-ok` torna o
  passo repetível.
- Linha 36: roda o roteiro num contêiner de vida curta (`--rm`).

## `scripts/demo_flow.py`

**Finalidade.** O roteiro de 11 passos. Cada passo provoca algo e **confere** o
resultado pela API, com prazo. Se uma conferência falhar, imprime `FALHOU:` e sai
com código 1.

**Dados.** Variáveis `PULSEOPS_DEMO_*` (endereços, usuário e senha). Produz a saída no
terminal e o código de saída. **Relações.** Executado pelo serviço `demo-runner`
(`compose.demo.yaml`). Usa a API JSON e os controles do laboratório. **Testes.** Não
há teste automatizado *do roteiro*; ele **é** um teste de ponta a ponta, executado no
CI. O mypy confere os tipos (`files` inclui `scripts`).

@@trecho scripts/demo_flow.py 20-55

- Linha 22: uma expressão regular extrai o token CSRF do HTML. É frágil se o HTML
  mudar, mas o roteiro falha com uma mensagem clara nesse caso (linhas 88–89).
- Linhas 24–42: os dois monitores. O principal verifica a cada 3 s, com timeout de
  2 s e limite de 800 ms. O estável repete a configuração (`**MAIN`) e troca nome,
  URL e intervalo.
- Linhas 51–55: três clientes HTTP **síncronos** (`httpx.Client`). Um roteiro
  sequencial não ganha nada com `async`.

@@trecho scripts/demo_flow.py 67-112

- Linhas 67–70: `expect` é o `assert` do roteiro: falha com mensagem ou imprime
  `ok:`.
- Linhas 72–81: `wait_for` chama a função `probe` a cada 0,5 s até ela devolver algo
  verdadeiro ou o prazo acabar. `time.monotonic()` é um relógio que nunca volta
  atrás, mesmo que o horário do sistema seja ajustado. `TypeVar` faz o tipo de saída
  ser o mesmo que a função devolve.
- Linhas 85–99: login como um navegador faria: abre `/login` (o cliente guarda o
  cookie de CSRF do login), envia o formulário com o token e espera o 303. Depois lê
  o token CSRF da sessão no painel.
- Linhas 106–112: toda chamada que altera dados leva o cabeçalho `X-CSRF-Token`.

@@trecho scripts/demo_flow.py 118-134

- O roteiro é **idempotente**: pode rodar várias vezes sem duplicar nada. Procura
  pelo nome; se existe, atualiza (`PUT`). Linhas 126–131: pausar e retomar zera a
  contagem e fecha um incidente que tenha ficado aberto de uma execução anterior,
  para o roteiro começar do zero.

@@trecho scripts/demo_flow.py 179-223

- Passo 1 (linhas 180–186): `/health/ready`, login e sinal de vida do worker.
- Passo 2 (188–200): prepara tudo e confere que existe **exatamente um** monitor de
  cada nome. Linha 200: `baseline` é o id do último check; os passos seguintes só
  olham checks mais novos que a marca, para não confundir com execuções anteriores.
- Passo 3 (202–223): dois checks saudáveis; depois, modo lento e a conferência de
  que lentidão **degrada sem abrir incidente** (ADR 0004).

@@trecho scripts/demo_flow.py 225-268

- Passo 4: um timeout isolado não abre incidente.
- Passo 5: modo erro (500). Espera o incidente abrir e confere o motivo
  ("Incidente confirmado após 3 falhas consecutivas") e o começo da linha do tempo
  (`first_failure` e depois `opened`). Depois confere que o alerta chegou ao receptor
  pelo id estável `incident:<id>:opened`.
- Passo 6: mais duas falhas e ainda **um só** incidente aberto, com o mesmo id.

@@trecho scripts/demo_flow.py 270-292

- Passo 7: alvo restaurado e um sucesso. **Ponto de atenção:** a linha 279 é um `if`,
  não um `expect`. Se a consulta acontecer depois do segundo sucesso, o incidente já
  terá sido encerrado e o passo só não imprime a frase. Isso evita uma falha falsa
  por causa do tempo, mas significa que o passo 7, sozinho, não **prova** que um
  sucesso não encerra. Quem prova é o passo 8 (encerra com 2) e os testes de
  `test_health.py`.
- Passo 8: incidente resolvido, monitor `healthy` e alerta `resolved` entregue.

@@trecho scripts/demo_flow.py 294-352

- Passo 9: receptor fora do ar e um novo incidente. Linhas 301–306: procura a
  entrega do alerta que já teve ao menos uma tentativa. Linhas 309–313: a entrega
  está `pending` (vai tentar de novo), o erro registrado contém 503 e o receptor
  contou a recusa.
- Passo 10: com o alerta parado, o monitoramento **continua**: mais dois checks são
  gravados (RF06.3).
- Passo 11: receptor de volta. A retentativa entrega (status `delivered`, pelo menos
  2 tentativas). Linhas 340–350: o roteiro reenvia o **mesmo** evento ao receptor e
  confere que ele foi reconhecido como duplicado. Repare que quem reenvia é o
  roteiro, não o PulseOps: o passo mostra a deduplicação do lado do receptor.

@@trecho scripts/demo_flow.py 355-374

- Linhas 356–359: sem senha, sai com código 2 (erro de uso), diferente do 1 (passo
  falhou).
- Linhas 365–369: `StepFailedError` e erros de HTTP viram `FALHOU: ...` e código 1.
  Qualquer outra exceção aparece com *traceback*, o que é o desejado para um bug do
  próprio roteiro.

## `scripts/ensaio_carga.py`

**Finalidade.** O ensaio de carga local: cria N monitores, deixa o worker rodar por
um tempo fixo enquanto clientes consultam a API, e mede o que aconteceu. Foi com
ele que o bug B8 apareceu.

**Dados.** Argumentos `--monitors` (200), `--interval` (10 s), `--duration`
(120 s) e `--api-clients` (4). Produz um relatório em Markdown na saída padrão.
**Relações.** Chamado por `scripts/ensaio_carga.sh` dentro do `demo-runner`. Os
resultados estão em `docs/evidencias/ensaio-de-carga.md` e
`docs/evidencias/ensaio-de-carga-antes-B8.md`. **Testes.** Não há; é uma ferramenta
de medição.

@@trecho scripts/ensaio_carga.py 32-36

- O percentil *nearest-rank*, o mesmo critério do p95 do produto (volume 1, parte F).
  `-(-a // b)` é um truque para arredondar a divisão **para cima** só com divisão
  inteira.

@@trecho scripts/ensaio_carga.py 112-151

- Linhas 115–121: login e token CSRF num cabeçalho padrão do cliente, usado em todas
  as chamadas.
- Linhas 124–125: aquecimento de um intervalo. Na primeira rodada, todos os
  monitores vencem juntos; medir essa rajada distorceria o atraso.
- Linhas 126–135: a janela medida. Clientes consultam a API em paralelo
  (`sample_api`, linhas 82–95) até o evento `stop`.
- Linha 136: espera mais um intervalo, para os checks iniciados dentro da janela
  terminarem de gravar.
- Linhas 138–148: coleta os checks da janela e as lacunas dos primeiros 50
  monitores. **Ponto de atenção:** `collect` (linhas 98–109) pede no máximo 200
  checks por monitor e não segue o cursor. Com os valores padrão são 12 checks por
  monitor, longe do limite; uma janela com mais de 200 checks por monitor seria
  contada a menos.
- Linhas 150–151: arquiva os monitores do ensaio, para não ficarem verificando
  depois.

@@trecho scripts/ensaio_carga.py 153-192

- Linha 154: checks esperados = monitores × janela ÷ intervalo.
- Linhas 156–162: o atraso de cada check é `started_at - scheduled_at`, em ms.
- O restante imprime as medidas: mediana, p95 e máximo.

## `scripts/ensaio_carga.sh`

**Finalidade.** Embrulha o ensaio: registra a máquina, roda o Python e grava o
relatório em `docs/evidencias/ensaio-de-carga.md`.

@@arquivo scripts/ensaio_carga.sh

- Linhas 14–30: o cabeçalho do relatório: data, commit, sistema, CPUs, memória,
  versão do Docker e a concorrência real do worker (lida de dentro do contêiner).
- Linhas 33–35: em segundo plano (`( ... ) &`), espera 70 s e tira **uma** amostra de
  CPU e memória dos contêineres. Com os valores padrão (10 s de aquecimento e 120 s de
  janela), isso cai no meio da janela. Com outros valores, pode cair fora dela; o
  relatório diz que é uma amostra única.
- Linha 37: `tee -a` mostra a saída e acrescenta ao relatório ao mesmo tempo.
- Linhas 48–52: o aviso de leitura: os números valem para esta máquina e esta
  configuração.

## `scripts/conferir_referencias.py`

**Finalidade.** Confere que os arquivos e testes citados na documentação existem.
É a regra R5 (confirmar antes de citar) transformada em programa.

**Dados.** Lê `README.md`, `CLAUDE.md` e todo `docs/**/*.md`, menos a especificação
original. Imprime os problemas e sai com 1 se houver algum. **Relações.** Passo
"Referências da documentação" do CI. **Testes.** Não há teste próprio; o CI o executa
sobre a documentação real.

@@arquivo scripts/conferir_referencias.py

- Linha 13: pega todo texto entre crases sem espaços.
- Linha 14: só confere textos que começam com uma pasta do projeto.
- Linhas 27–36: um caminho citado precisa existir. Caminhos com `*` ou `{` são
  padrões, não arquivos, e são pulados.
- Linhas 37–40: as formas curtas `::test_x` e `test_x` herdam o último arquivo `.py`
  citado na mesma linha.
- Linhas 43–48: o teste precisa existir no arquivo, procurado por `def nome`.
- **Limites:** não confere números de linha, nem afirmações em texto corrido, nem as
  fontes deste guia (que ficam em `study/`; o `study/build.py` faz a conferência dos
  trechos por conta própria).

## `scripts/capturar_telas.mjs`

**Finalidade.** Tira as capturas de tela de `docs/imagens/` com o Playwright, num
navegador Chromium sem janela. Opcional; não faz parte dos testes.

@@arquivo scripts/capturar_telas.mjs

- Linhas 7–10: a URL vem da variável `PULSEOPS_URL` ou usa a local; a senha vem de
  `.demo/admin-password`, nunca do código.
- Linhas 13–27: abre um contexto em português, captura o login, entra e captura cada
  página da lista com `fullPage: true` (a página inteira, não só a parte visível).
- Linhas 29–30: um tamanho de computador (1280 × 800) e um de celular (390 × 844),
  este só para as duas primeiras páginas.
