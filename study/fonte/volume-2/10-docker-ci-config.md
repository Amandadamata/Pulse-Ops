# D10 — Docker, Compose, CI e configuração do projeto

Estes arquivos não têm lógica de negócio, mas decidem como o projeto é construído,
como sobe e o que o CI recusa. Numa entrevista, são os arquivos mais fáceis de
perguntar e os mais esquecidos de estudar.

## `Dockerfile`

**Finalidade.** Uma imagem só para API, worker, migrações e laboratório. O que muda
é o comando de cada serviço no Compose.

**Relações.** Construída pelo `compose.yaml` (`build`) e pelo job `docker` do CI.
**Testes.** O job `docker` constrói a imagem do zero e roda a demonstração nela.

@@arquivo Dockerfile

- Linha 1: ativa a sintaxe moderna do BuildKit, necessária para `--mount=type=secret`.
- Linhas 4–21: o **estágio de construção** (`AS builder`). Linha 5: compila o
  *bytecode* na instalação, copia arquivos em vez de criar *links* e proíbe o uv de
  baixar outro Python. Linha 11: versão exata do uv.
- Linhas 8–10, 14–15, 19–20: o segredo opcional `extra_ca`, para redes com proxy TLS
  corporativo. Um segredo de build é montado só durante aquele `RUN` e **não** fica
  gravado em camada nenhuma da imagem. Sem o arquivo, nada muda.
- Linhas 13–16: copia só o `pyproject.toml` e o `uv.lock` e instala as dependências
  **antes** de copiar o código. Como o Docker guarda cada passo em cache, mudar o
  código não reinstala as dependências; só mudar o *lock* faz isso. `--frozen` usa o
  `uv.lock` exatamente como está; `--no-dev` deixa as ferramentas de teste de fora.
- Linhas 18–21: copia o código e instala o projeto (`--no-editable`: uma cópia, e não
  um *link* para a pasta `src`).
- Linhas 24–38: o **estágio final**, que parte de uma imagem limpa. Os compiladores e
  caches do estágio anterior não vêm junto; só a `.venv` (linha 27).
- Linha 25: um usuário de sistema sem *shell* de login, com uid fixo. Linha 36: o
  processo roda como ele, e não como `root`.
- Linhas 28–31: migrações, laboratório e scripts entram na imagem porque os
  serviços `migrate`, `lab-*` e `demo-runner` usam a mesma imagem.
- Linhas 32–35: `PYTHONUNBUFFERED=1` manda os logs na hora, sem *buffer*;
  `PYTHONPATH=/app` torna `lab` e `scripts` importáveis.
- Linha 38: o comando padrão é a API. `--factory` diz ao uvicorn que
  `create_app` é uma função que **devolve** a aplicação.

## `.dockerignore`

@@arquivo .dockerignore

O que **não** vai para o contexto de build: ambientes, caches, `.git`, documentação,
testes e, principalmente, o `.env` (linha 7). Sem isso, um `COPY` descuidado poderia
colocar a senha do banco dentro da imagem.

## `compose.yaml`

**Finalidade.** O ambiente padrão: banco, migrações, API e worker.

**Relações.** Usado por `docker compose up`, pelo `scripts/demo.sh` (junto com o
`compose.demo.yaml`) e pela instalação limpa descrita no README. **Testes.** O job
`docker` do CI e `docs/evidencias/instalacao-limpa.md`.

@@arquivo compose.yaml

- Linha 2: `name` fixa o prefixo dos contêineres e volumes (`pulseops-...`).
- Linhas 4–17: `x-app` é um **bloco reutilizável** (âncora `&app` do YAML), aplicado
  aos três serviços da aplicação com `<<: *app`.
  - Linhas 9–11: lê o `.env` se ele existir (`required: false`).
  - Linha 13: monta a URL do banco a partir das mesmas variáveis do serviço `db`.
    `${VAR:-padrão}` usa o padrão quando a variável não existe.
  - Linhas 14–17: **endurecimento** do contêiner. Sistema de arquivos só de leitura,
    com `/tmp` em memória; nenhuma *capability* do Linux; e `no-new-privileges`, que
    impede um processo de ganhar privilégios depois de iniciado.
- Linhas 20–34: o PostgreSQL 16. Linha 28: **sem `ports`**, o banco não é acessível
  de fora da rede do Compose. Linhas 29–33: o *healthcheck* com `pg_isready`. O `$$`
  escapa o `$` para o Compose deixar a variável para o *shell* do contêiner.
- Linhas 36–41: `migrate` roda `alembic upgrade head` e termina. Só começa com o
  banco saudável; `restart: "no"` porque ele **deve** terminar.
- Linhas 43–54: a API. Linha 46: publicada **só em `127.0.0.1`**, ou seja, não fica
  visível para outras máquinas da rede. Linha 48: só sobe depois de o `migrate`
  terminar com sucesso. Linhas 49–53: o *healthcheck* chama `/health/ready` com o
  Python da imagem (não há `curl` na imagem *slim*).
- Linhas 56–61: o worker, com o comando `python -m pulseops.worker`. Também espera o
  `migrate`, mas não a API.
- Linhas 63–64: o volume nomeado `pgdata` guarda os dados entre reinícios.
  `docker compose down` mantém o volume; `down -v` o apaga.
- Linhas 66–68: o segredo do build aponta para um arquivo vazio do repositório
  (`docker/no-extra-ca.pem`), a menos que `PULSEOPS_EXTRA_CA_FILE` diga outro.

## `compose.demo.yaml`

**Finalidade.** O que muda no modo demonstração: variáveis da API e do worker, e os
três serviços do laboratório no perfil `demo`.

@@arquivo compose.demo.yaml

- Linhas 1–10: o comentário explica o arquivo e lembra que ele só faz sentido junto
  com o `compose.yaml`. O Compose **mescla** os dois: `api` e `worker` ganham as
  variáveis do bloco `x-demo-env`.
- Linhas 12–17: o modo demonstração e a lista **nominal** de destinos liberados (só
  `lab-target:8081` e `lab-receiver:8082`; nenhum outro endereço privado). As
  retentativas de webhook ficam curtas (1 s de base, até 5 s) e com até 20 tentativas,
  para a demonstração não esperar minutos.
- Linhas 19–26: os serviços do laboratório herdam o mesmo endurecimento e só existem
  com `--profile demo`.
- Linhas 35–51: alvo e receptor, cada um com um *healthcheck* nos próprios controles.
- Linhas 55–68: o `demo-runner` roda o roteiro e termina. Espera a API, o alvo e o
  receptor estarem saudáveis. A senha chega pela variável que o `demo.sh` exporta.

## `.env.example`

**Finalidade.** O modelo do `.env`: as variáveis que uma pessoa costuma ajustar, com
valores que **não** são segredos reais.

@@arquivo .env.example

- Linha 3: `troque-esta-senha` é um aviso, não uma senha.
- Linha 9: `PULSEOPS_COOKIE_SECURE=false` porque o ambiente local é HTTP. Atrás de
  HTTPS, deve ser `true`, para o cookie de sessão nunca trafegar sem criptografia.
- Linhas 17–21: os padrões do worker, iguais aos de `src/pulseops/config.py`.
- A lista completa, com a descrição de cada variável, está em `docs/operacao.md`.

## `.gitignore`

@@arquivo .gitignore

- Linha 9: o `.env`, que guarda a senha real do banco.
- Linha 13: `docker/local-ca.pem`, o certificado de uma rede específica, que não deve
  ir para o repositório.
- Linha 14: `.demo/`, onde fica a senha da operadora da demonstração.
- Linhas 12 e 15: o resultado do build deste guia e as dependências de Node usadas
  para gerar o PDF.

## `pyproject.toml`

**Finalidade.** A identidade do projeto e a configuração de todas as ferramentas.

@@arquivo pyproject.toml

- Linhas 1–7: nome, versão, licença e a versão de Python aceita: `>=3.12,<3.13`, só a
  3.12, que é a testada.
- Linhas 8–20: as dependências de execução, com versão **mínima**. As versões exatas
  instaladas ficam no `uv.lock`, que é o que o build e o CI usam (`--frozen`).
- Linhas 22–23: cria o comando `pulseops` apontando para `pulseops.cli:main`.
- Linhas 25–33: as ferramentas de desenvolvimento, fora da imagem.
- Linhas 35–37: o *backend* de build do uv, que empacota `src/pulseops`.
- Linhas 39–45: o Ruff. Linha 44: as famílias de regras. `S` são as regras de
  segurança do Bandit; `ASYNC` pega erros comuns em código assíncrono; `DTZ` recusa
  datas sem fuso; `B` pega armadilhas como argumentos padrão mutáveis. Linha 45:
  desliga os avisos sobre acentos e aspas tipográficas, normais em textos em
  português.
- Linhas 47–53: exceções por pasta. Nos testes, `assert` (S101) e senhas fixas de
  teste (S105, S106) são esperados. No gerador do guia, chamar programas externos
  (S603, S607) é o objetivo. **Ponto de atenção:** as exceções `S104` para `lab/` e
  `S101` para `scripts/` estão sobrando. Rodando o Ruff só com essas regras e sem as
  exceções (`ruff check --isolated --select S104,S101 lab scripts`), nada é apontado.
  São inofensivas, mas podem ser removidas.
- Linhas 55–59: o mypy no modo `strict` (todas as funções com tipos, nada de `Any`
  implícito), com o *plugin* do Pydantic, sobre o código, o laboratório e os scripts.
  Os testes ficam de fora.
- Linhas 61–66: o pytest. `asyncio_mode = "auto"` trata toda função `async def
  test_...` como teste assíncrono. As linhas 64–65 fazem todos os testes usarem o
  **mesmo** *event loop*, necessário porque o engine do banco é criado uma vez por
  sessão de testes. `--strict-markers` recusa marcadores digitados errado.
- Linhas 68–77: a cobertura mede ramos (`branch = true`, cada `if` nos dois sentidos).
  O comentário das linhas 71–72 explica `concurrency`: sem ela, linhas executadas
  dentro de *greenlets* do SQLAlchemy apareceriam como não cobertas.

## `.github/workflows/ci.yml`

**Finalidade.** A integração contínua: em cada *push* na `main` e em cada *pull
request*, roda a qualidade e a demonstração. Não implanta nada.

**Testes.** É ele quem executa os testes. Se o CI está verde, só se pode afirmar com o
link de uma execução (volume 1, parte I).

@@arquivo .github/workflows/ci.yml

- Linhas 10–11: o *token* do workflow só pode **ler** o repositório. Mesmo que um
  passo fosse comprometido, não poderia publicar nada.
- Linhas 13–15: um *push* novo no mesmo ramo cancela a execução anterior, que já
  ficou velha.
- Linhas 18–34: o job `qualidade` tem um PostgreSQL como serviço, na porta 5433, a
  mesma do banco de testes local. O `conftest.py` recria o banco `pulseops_test` a
  partir dessa conexão.
- Linhas 37–41: o uv numa versão exata e a instalação a partir do `uv.lock`.
- Linhas 42–47: Ruff (regras e formatação) e mypy. Qualquer aviso falha o job.
- Linhas 48–54: as migrações num banco limpo: sobe tudo, **desce até o zero** e sobe
  de novo. Assim se confirma que o `downgrade` funciona e que a migração pode ser
  reaplicada.
- Linhas 55–56: os testes com cobertura mínima de 90% no total.
- Linhas 57–60: metas mais altas, 95%, para domínio e segurança.
- Linhas 61–62: o `conferir_referencias.py` (D9).
- Linhas 63–66: o `pip-audit` confere as versões travadas no `uv.lock` contra a base
  de vulnerabilidades conhecidas. **Ponto de atenção:** o CI fixa a versão 2.9.0 do
  `pip-audit` (linha 66), enquanto o grupo `dev` do `pyproject.toml` pede `>=2.10.1`.
  As duas funcionam, mas é uma inconsistência que vale alinhar.
- Linhas 68–81: o job `docker` roda `scripts/demo.sh`, que constrói a imagem e
  executa os 11 passos. Se falhar, mostra os últimos logs (`if: failure()`); em
  qualquer caso, derruba o ambiente (`if: always()`).

## Arquivos de dados do repositório

- `docker/no-extra-ca.pem`: um arquivo **vazio**, o padrão do segredo de build.
- `uv.lock`: gerado pelo uv (`uv lock`); não se edita à mão. Trava as versões exatas
  de todas as dependências, inclusive as indiretas, com os *hashes*.
- `alembic.ini` e os arquivos de `migrations/`: explicados em D3.
- `LICENSE`: o texto da licença MIT, sem nada a explicar.
