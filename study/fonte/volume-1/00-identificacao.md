# Identificação e como usar este guia {.unnumbered}

| Item | Valor |
|---|---|
| Material | *PulseOps por dentro: guia de código, decisões e preparação para entrevistas* |
| Versão do material | {{VERSAO}} |
| Data de geração | {{DATA}} |
| Commit do código explicado | `{{COMMIT}}` |
| Volumes | Volume 1 (este): partes A, B, C, E, F, G, H, I e J, e o gabarito da parte J. Volume 2: parte D, código explicado linha a linha |
| Autora do projeto | Amanda da Mata |

**Sobre o commit.** Os trechos de código deste guia foram copiados por um script
(`study/build.py`) dos arquivos do repositório no commit `{{COMMIT_CURTO}}`. O
próprio PDF e a fonte dele (`study/`) foram commitados **depois**, em commits que
só acrescentam documentação; por isso o hash acima é o do código explicado, não o
do commit que contém o PDF. O script se recusa a gerar o material se algum arquivo
de código tiver mudado desde esse commit.

**Como o projeto foi feito.** O PulseOps foi implementado com o Claude Code
(assistente de IA) a partir de uma especificação escrita por Amanda. Este guia
existe para que Amanda estude o código, entenda cada decisão e consiga explicá-la
com as próprias palavras. Ele não afirma que ela já domina esses assuntos: a
parte H indica, em cada pergunta de entrevista, o limite do que dá para afirmar.

## Pré-requisitos {.unnumbered}

- Saber abrir um terminal e digitar comandos (a parte B explica cada um).
- Ter lido ao menos uma introdução de Python: variáveis, `if`, `for`, funções.
  A parte E retoma esses conceitos no código do PulseOps.
- Docker instalado, para executar o projeto. Para os testes, também o
  [uv](https://docs.astral.sh/uv/).
- Não é preciso saber FastAPI, SQL ou Docker antes: o guia explica o que cada
  coisa faz no momento em que aparece.

## Caminho de estudo recomendado {.unnumbered}

1. **Primeira semana: o produto.** Leia a parte A, execute a parte B até ver o
   painel funcionando e rode `scripts/demo.sh`. Observe o painel enquanto o
   roteiro roda.
2. **Segunda semana: a regra central.** Leia a parte C e, no volume 2, o arquivo
   `domain/health.py` e o teste `tests/unit/test_health.py`. Faça os exercícios
   J1 a J11 da parte J.
3. **Terceira semana: um check do começo ao fim.** No volume 2, siga
   `worker/runner.py` → `services/processing.py` → `checks/checker.py` →
   `security/transport.py`. Leia a parte F (banco) junto.
4. **Quarta semana: alertas, API e painel.** `services/alerts.py`,
   `notifications/webhook.py`, `web/`. Leia a parte G.
5. **Quinta semana: entrevistas.** Parte H em voz alta, parte I, e os exercícios
   restantes da parte J sem olhar o gabarito.

Em cada etapa, mude algo pequeno, rode os testes e veja o que quebra. Ler sem
executar rende pouco.

## Convenções {.unnumbered}

- Nomes de código (variáveis, funções, arquivos, endpoints) aparecem `assim` e em
  inglês, como no repositório. O texto é em português.
- "Linha 42" sempre se refere à numeração do arquivo no commit acima.
- Os blocos "SQL enviado ao PostgreSQL" foram capturados durante a execução dos
  testes (`study/captura_sql.py`), não escritos à mão.
- **Usado no PulseOps** marca recursos que aparecem no código. **Só para
  comparação** marca conceitos citados para contraste, que o projeto não usa.
