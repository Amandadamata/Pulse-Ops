# Parte B — Execução passo a passo

Esta parte leva do zero até o painel funcionando. Para cada comando há três
coisas: o que cada pedaço significa, o que deve aparecer e como confirmar que deu
certo.

> **Onde isto foi testado.** Os comandos foram executados em Linux (container
> x86_64 com Docker 29). Em macOS devem funcionar igual. Em Windows, use o WSL2
> (Ubuntu) com o Docker Desktop: os scripts `.sh` precisam de um shell bash.
> Windows sem WSL **não foi testado**.

## Terminal e diretórios

O **terminal** é um programa onde você digita comandos em texto. Ele sempre está
"dentro" de uma pasta, o **diretório atual**.

| Comando | O que faz |
|---|---|
| `pwd` | mostra o diretório atual (*print working directory*) |
| `ls` | lista os arquivos do diretório atual; `ls -a` inclui os ocultos, que começam com ponto, como `.env` |
| `cd pulseops` | entra na pasta `pulseops`; `cd ..` volta uma pasta |
| `cat arquivo` | mostra o conteúdo de um arquivo |

Caminhos começando com `/` são **absolutos** (a partir da raiz do disco). Os outros
são **relativos** ao diretório atual. `./scripts/demo.sh` e `scripts/demo.sh` são o
mesmo arquivo quando você está na raiz do projeto.

## Instalação das ferramentas

1. **Git**, para baixar o código: `git --version` deve mostrar algo como
   `git version 2.4x`.
2. **Docker** com Compose v2: `docker --version` e `docker compose version`.
   O segundo comando precisa responder `Docker Compose version v2...` (com espaço,
   não `docker-compose` com hífen, que é a versão antiga).
3. Para rodar os testes fora do Docker: **uv**
   (`curl -LsSf https://astral.sh/uv/install.sh | sh`) e conferir com
   `uv --version`.

## Baixar o código

```bash
git clone <url-do-repositorio> pulseops
cd pulseops
```

- `git clone` copia o repositório inteiro, com o histórico, para uma pasta nova.
- `<url-do-repositorio>` é o endereço que aparece no botão "Code" do GitHub.
- `pulseops` no fim é o nome da pasta criada.
- **Confirmação:** `ls` mostra `README.md`, `compose.yaml`, `src`, `tests`...

## Ambientes e dependências

O código Python depende de bibliotecas de terceiros (FastAPI, SQLAlchemy...). As
versões exatas ficam em dois arquivos:

- `pyproject.toml`: a lista do que o projeto precisa, com versões mínimas.
- `uv.lock`: a versão **exata** de cada pacote, inclusive das dependências das
  dependências. Com ele, a instalação de hoje e a de daqui a um ano resultam no
  mesmo conjunto.

Um **ambiente virtual** (`.venv/`) é uma pasta com um Python e as bibliotecas do
projeto, separada do Python do sistema. Assim, projetos diferentes não brigam por
versões.

```bash
uv sync
```

- `uv` é o gerenciador de pacotes escolhido (ADR 0001).
- `sync` cria o `.venv/` se não existir e instala exatamente o que está no
  `uv.lock`, incluindo as ferramentas de desenvolvimento (pytest, ruff, mypy).
- **Confirmação:** `uv run python -c "import pulseops; print(pulseops.__version__)"`
  imprime `0.1.0`.

`uv run <comando>` executa o comando **dentro** do ambiente virtual, sem precisar
"ativá-lo".

Para rodar o PulseOps com Docker, nada disso é necessário: a imagem instala as
dependências sozinha. O `uv` só é preciso para testes e desenvolvimento.

## Variáveis de ambiente

Uma **variável de ambiente** é um par nome=valor que o sistema entrega a um
programa quando ele começa. O PulseOps lê todas as que começam com `PULSEOPS_`
(arquivo `src/pulseops/config.py`). Isso permite mudar a configuração sem mudar
o código, e deixa senhas fora do Git.

```bash
cp .env.example .env
```

- `cp` copia `.env.example` (modelo, que vai para o Git) para `.env` (seu, que **não**
  vai: está no `.gitignore`).
- Abra o `.env` num editor e troque `POSTGRES_PASSWORD=troque-esta-senha` por uma
  senha sua.
- O Docker Compose lê o `.env` automaticamente e repassa os valores.

As variáveis mais úteis estão em `docs/operacao.md`. Exemplo: com
`PULSEOPS_DISPLAY_TIMEZONE=America/Sao_Paulo`, o painel mostra horários de
Brasília; o banco continua guardando tudo em UTC.

## Docker e Compose

- Uma **imagem** é um pacote com sistema operacional mínimo, Python, bibliotecas e
  o código. O `Dockerfile` é a receita da imagem.
- Um **container** é uma imagem em execução, isolada do resto da máquina.
- O **Docker Compose** sobe vários containers juntos a partir do `compose.yaml`.
  No PulseOps são quatro serviços: `db` (PostgreSQL), `migrate` (cria as tabelas e
  sai), `api` (painel e API) e `worker` (checks e alertas).
- Um **volume** (`pgdata`) é um disco que sobrevive aos containers: apagar o
  container do banco não apaga os dados.

```bash
docker compose up -d --build --wait
```

| Pedaço | Significado |
|---|---|
| `docker compose` | usa o Compose com o `compose.yaml` da pasta atual |
| `up` | cria e inicia os serviços |
| `-d` | *detached*: roda em segundo plano e devolve o terminal |
| `--build` | (re)constrói a imagem a partir do `Dockerfile` antes de subir |
| `--wait` | espera os serviços ficarem saudáveis (healthchecks) antes de terminar |

**Resultado esperado:** no fim, linhas como `Container pulseops-api-1 Healthy`. A
primeira vez demora alguns minutos (download das imagens base e das bibliotecas).

**Confirmação:**

```bash
docker compose ps -a
```

`db` e `api` aparecem `running (healthy)`, `worker` aparece `running` e `migrate`
aparece `exited (0)`. O 0 é o código de saída: terminou sem erro, como esperado.

## Banco e migrações

O banco começa vazio. Uma **migração** é um script que cria ou altera tabelas.
O PulseOps usa o **Alembic**, e a única migração está em
`migrations/versions/0001_esquema_inicial.py`. O serviço `migrate` executa
`alembic upgrade head` ("aplique todas as migrações até a mais recente") toda vez
que o ambiente sobe; se já estiverem aplicadas, ele não faz nada.

Para ver as tabelas criadas:

```bash
docker compose exec db psql -U pulseops -d pulseops -c '\dt'
```

- `exec db` roda um comando **dentro** do container `db` que já está no ar.
- `psql` é o cliente de linha de comando do PostgreSQL; `-U` é o usuário e `-d`, o banco.
- `\dt` lista as tabelas. Devem aparecer 13 tabelas do PulseOps (`monitors`,
  `checks`, `incidents`...) e a `alembic_version`, onde o Alembic anota qual
  migração foi aplicada.

## Criar a operadora

```bash
docker compose run --rm api pulseops create-admin --username amanda
```

- `run` cria um container **temporário** a partir do serviço `api` só para rodar
  um comando. `--rm` o apaga no fim.
- `pulseops create-admin` é o comando definido em `src/pulseops/cli.py`.
- O comando pergunta a senha duas vezes, sem mostrar o que você digita. Mínimo de
  12 caracteres.
- **Resultado esperado:** `operador 'amanda' criado`.

## Iniciar, usar e parar

1. Abra <http://127.0.0.1:8000>. Você será levada para `/login`.
2. Entre com o usuário criado. O painel mostra "Nenhum monitor cadastrado".
3. Clique em **Novo monitor**, informe nome e URL pública (por exemplo,
   `https://example.com/`) e salve. Fora do modo demonstração, o intervalo mínimo
   é 30 s.
4. Em poucos segundos, a página do monitor mostra o primeiro check.

`127.0.0.1` é o "localhost", a própria máquina. O Compose publica a porta 8000
**só** nesse endereço, então outras máquinas da rede não acessam o painel.

```bash
docker compose stop      # para os containers (mantém tudo)
docker compose start     # volta a subir
docker compose down      # remove os containers e a rede; o volume fica
docker compose down -v   # remove também o volume: APAGA o banco
```

## Como conferir se está funcionando

| O que conferir | Comando | Resultado esperado |
|---|---|---|
| API viva | `curl -s http://127.0.0.1:8000/health/live` | `{"status":"ok"}` |
| API com banco | `curl -s http://127.0.0.1:8000/health/ready` | `"status":"ok"` e `"database":"ok"` |
| Worker vivo | painel inicial | nenhum aviso "Worker sem sinal" |
| Checks acontecendo | página do monitor | "Histórico de checks" crescendo a cada intervalo |
| Logs do worker | `docker compose logs -f worker` | linhas JSON com `"msg": "check gravado"` |

`curl` é um cliente HTTP de linha de comando; `-s` (*silent*) esconde a barra de
progresso. `logs -f` (*follow*) continua mostrando linhas novas até você apertar
`Ctrl+C`.

## O laboratório de falhas

```bash
scripts/demo.sh
```

Sobe o ambiente com `compose.yaml` **e** `compose.demo.yaml`, ativando o perfil
`demo` (alvo e receptor controláveis, intervalos curtos), cria a operadora `demo`
e executa os 11 passos descritos no README. A senha da operadora `demo` fica em
`.demo/admin-password`. Para derrubar: `scripts/demo.sh --down`.

**Confirmação:** a última linha é
`Demonstração concluída: os 11 passos foram verificados.` e `echo $?` logo depois
mostra `0`. Se um passo falhar, aparece `FALHOU: <motivo>` e o código é 1.

## Rodar os testes

```bash
docker run -d --name pulseops-testdb -e POSTGRES_USER=pulseops \
  -e POSTGRES_PASSWORD=pulseops -p 127.0.0.1:5433:5432 postgres:16-alpine
uv run pytest
```

- O primeiro comando cria um PostgreSQL só para testes na porta 5433 (a barra
  invertida `\` no fim da linha continua o comando na linha seguinte).
- `-e` define variáveis de ambiente do container; `-p 127.0.0.1:5433:5432` liga
  a porta 5433 da sua máquina à 5432 do container.
- `uv run pytest` encontra e executa todos os testes em `tests/`.
- **Resultado esperado:** `251 passed` (o número exato do commit explicado), em
  menos de um minuto.

Os testes apagam e recriam o banco `pulseops_test` a cada execução. Nunca aponte
`PULSEOPS_TEST_DATABASE_URL` para um banco com dados que importam.

## Erros comuns e diagnóstico

| Sintoma | Causa provável | Como diagnosticar e resolver |
|---|---|---|
| `port is already allocated` ao subir | Outro programa usa a porta 8000 | Defina `PULSEOPS_PORT=8001` no `.env` e acesse `:8001` |
| `Cannot connect to the Docker daemon` | Docker parado | Abra o Docker Desktop ou `sudo systemctl start docker` |
| `toomanyrequests` ao baixar imagens | Limite de downloads do Docker Hub | Espere alguns minutos ou faça login com `docker login` |
| Erro de certificado no build | Rede com proxy TLS corporativo | `PULSEOPS_EXTRA_CA_FILE=/caminho/ca.pem` antes do `docker compose up` |
| `migrate` com `exited (1)` | Banco inacessível ou senha errada | `docker compose logs migrate`; confira `POSTGRES_PASSWORD`. Se você trocou a senha **depois** de criar o volume, o banco antigo continua com a senha antiga: use a antiga ou apague o volume (`down -v`, perde os dados) |
| Monitor recusado: "endereço privado" | Política SSRF, de propósito | Monitores só alcançam endereços públicos. Para testes locais, use o laboratório |
| Checks com "falha de DNS" | O container não resolve nomes | `docker compose exec worker python -c "import socket; print(socket.getaddrinfo('example.com', 443))"` |
| Todos os monitores "desatualizados" | Worker parado | `docker compose ps worker` e `docker compose logs worker` |
| `pytest` com `connection refused` na porta 5433 | Banco de testes não está rodando | `docker start pulseops-testdb` |

Quando algo não funcionar, a ordem de investigação é: `docker compose ps -a` (o que
está rodando?), `docker compose logs <serviço>` (o que ele disse?) e
`curl .../health/ready` (a API alcança o banco?).
