# Parte I — Como apresentar o projeto

## Explicação de 30 segundos

> O PulseOps é um monitor de APIs HTTP que eu especifiquei e estudei a fundo. Ele
> verifica URLs periodicamente, separa resposta lenta de falha, só abre incidente
> depois de falhas seguidas e explica cada decisão. Os alertas saem por webhook
> com retentativas, sem atrasar as verificações. É Python com FastAPI, PostgreSQL,
> um worker separado, 251 testes com banco real e um laboratório que provoca as
> falhas e confere o comportamento em 11 passos.

Treine até sair natural, em voz alta. Se perguntarem "você que fez?", responda
como em H34.

## Explicação de 2 minutos

1. **Problema (20 s).** Uma equipe fictícia descobria quedas pelos clientes e
   recebia alertas repetidos ou falsos. O PulseOps responde três perguntas: está
   no ar? está lento? por que o sistema decidiu isso?
2. **Como funciona (40 s).** São dois processos. A API serve o painel e a API JSON.
   O worker reserva no banco os monitores vencidos, faz as requisições fora de
   qualquer transação e grava o resultado aplicando a regra: 3 falhas seguidas
   abrem um incidente, 2 sucessos fecham. Cada mudança grava o motivo em texto.
3. **O que é difícil e como foi resolvido (40 s).**
   - Duplicidade: o banco proíbe dois incidentes abertos e dois checks em
     andamento por monitor, com índices únicos parciais.
   - Alertas: outbox na mesma transação, entrega pelo menos uma vez, com `event_id`
     estável para deduplicar.
   - Segurança: a política SSRF valida o IP na hora da conexão e conecta nesse IP,
     o que fecha o DNS rebinding.
4. **Como provar (20 s).** Testes com PostgreSQL real, CI, um ensaio de carga que
   achou um bug de vazão (B8) e o laboratório `scripts/demo.sh`.

## Roteiro de demonstração de 5 minutos

Prepare antes: ambiente no ar com a demonstração (`scripts/demo.sh` já rodado uma
vez), navegador aberto no painel e um terminal na raiz do projeto.

| Tempo | O que fazer | O que dizer |
|---|---|---|
| 0:00–0:30 | Mostrar o README: diagrama e a seção do laboratório | "Dois processos e um banco. Vou mostrar as falhas acontecendo." |
| 0:30–2:30 | Rodar `scripts/demo.sh` no terminal | Comentar os passos conforme aparecem: verificações saudáveis; timeout; "falha 1 de 3, 2 de 3"; incidente aberto na 3ª; falhas seguintes não abrem outro; recuperação com 2 sucessos |
| 2:30–3:30 | No painel, abrir o incidente criado | Mostrar início versus confirmação, a linha do tempo com os motivos e o alerta com as tentativas |
| 3:30–4:15 | Página de notificações | "O receptor ficou fora do ar: aqui estão as tentativas com 503 e a espera crescente; quando voltou, entregou. As verificações não pararam." |
| 4:15–5:00 | Abrir `src/pulseops/db/models.py` no índice `uq_incidents_one_open_per_monitor` | "Essa linha é o motivo de não haver incidente duplicado, mesmo com bug no código." |

Se algo falhar ao vivo, não esconda: o script diz `FALHOU: <motivo>` e termina com
código 1. Explicar a falha é uma demonstração melhor do que fingir que não
aconteceu. Tenha as capturas de `docs/imagens/` como plano B.

## Descrição para currículo

Use só o que foi entregue e pode ser mostrado:

> **PulseOps** — projeto pessoal de estudo (Python, FastAPI, PostgreSQL,
> SQLAlchemy, Docker). Monitor de APIs HTTP com worker separado, regra de
> incidentes por limiares, alertas por webhook com outbox e retentativas e
> proteção contra SSRF. 251 testes automatizados com PostgreSQL real, CI no GitHub
> Actions e laboratório de falhas reproduzível. Desenvolvido com assistência de IA
> a partir de especificação própria. [link do repositório]

Variações curtas para o LinkedIn ou um formulário: "Monitor de APIs em Python com
FastAPI e PostgreSQL, testes com banco real e laboratório de falhas".

**Não escreva:** "em produção", "usado por N pessoas", "alta disponibilidade",
"escalável", "experiência profissional", ou uma porcentagem de melhoria de
desempenho sem citar que foi num ensaio local.

## O que mostrar primeiro a um recrutador

Recrutadores costumam ter poucos minutos. Na ordem:

1. **O README**, até a imagem do painel: o que é, em uma frase, e que funciona.
2. **A seção do laboratório de falhas** do README: mostra que o comportamento foi
   verificado, não só descrito.
3. **O selo ou a aba Actions** com o CI verde (só se o repositório estiver
   publicado e o CI tiver passado).
4. **O registro de bugs** (`docs/registro-de-bugs.md`): mostra processo, e é
   raro em projetos de portfólio.

Para uma pessoa técnica, acrescente: `docs/decisoes/` (as ADRs) e um teste que
você saiba explicar de cor, como `test_rebinding_is_checked_at_connect_time`.

## Afirmações que exigem evidência ou estudo antes

| Afirmação | Antes de dizer, tenha |
|---|---|
| "O CI está verde" | o link de uma execução verde no GitHub |
| "Funciona com uma instalação do zero" | `docs/evidencias/instalacao-limpa.md` e, de preferência, ter feito você mesma |
| "Cobertura de 95%" | rodado `uv run pytest --cov` e visto o número, e saber o que cobertura não prova (parte G) |
| "Aguenta 200 monitores" | a frase completa: "num ensaio local, 200 monitores a cada 10 s, numa máquina de 4 CPUs" |
| "É seguro contra SSRF" | saber explicar as duas camadas, o DNS rebinding e o que **não** é coberto (firewall de saída) |
| "Não perde alertas" | saber explicar o outbox e por que pode **duplicar** |
| "Usei async" | saber explicar o event loop e por que um código bloqueante trava tudo (H17) |
| "Usei orientação a objetos" | exemplos concretos (H2), sem exagerar |
| Qualquer número | o arquivo de onde ele veio |

Se não souber responder um aprofundamento, diga "não sei, mas é assim que eu
descobriria", e aponte o arquivo ou o teste. É melhor que inventar.
