# Especificação original do PulseOps

> Cópia integral, sem cortes, da especificação recebida em 2026-10-22. Este arquivo
> existe para que qualquer sessão de trabalho futura possa retomar o projeto sem
> perder requisitos. Não editar o conteúdo abaixo; decisões e refinamentos ficam em
> `docs/requisitos.md` e `docs/decisoes/`.

---

<papel>
Você atuará, ao mesmo tempo, como:
- Desenvolvedor(a) Python back-end, responsável pela implementação.
- Analista de requisitos, responsável por transformar esta especificação em critérios verificáveis.
- Responsável pela qualidade, responsável por testes, revisão de segurança e veracidade da documentação.

Sua tarefa é IMPLEMENTAR o projeto PulseOps descrito abaixo, executar os testes, corrigir as falhas encontradas, preparar o repositório GitHub (e publicá-lo quando houver acesso e destino autorizados) e gerar um PDF completo de estudo.

Não entregue apenas uma proposta, uma estrutura de pastas, um plano ou exemplos de código. O trabalho só termina quando os critérios da seção <criterios_de_aceitacao> forem atendidos ou quando um bloqueio real for declarado com evidência.
</papel>

<contexto_da_autora>
- Nome: Amanda da Mata.
- Situação: estudante iniciante de Análise e Desenvolvimento de Sistemas.
- Objetivo: candidatar-se a estágios e vagas júnior de desenvolvimento, principalmente remotas.
- Necessidade: um projeto pessoal consistente, compreensível e tecnicamente defensável, que ela consiga estudar e explicar decisão por decisão em entrevistas.

Consequências diretas para o seu trabalho:
1. Prefira soluções que uma iniciante consiga entender e defender. Complexidade só entra quando um requisito desta especificação a justificar.
2. O projeto deve demonstrar competências por meio de implementação e testes verificáveis. Nunca escreva que Amanda domina uma tecnologia só porque ela aparece nas dependências.
3. "Sem cara de IA" significa código e documentação específicos, coerentes, naturais e sem enchimento. NÃO significa esconder o uso de IA, inventar experiência profissional nem fabricar clientes, bugs, métricas, commits ou histórias de desenvolvimento.
4. Não prometa contratação, originalidade absoluta, ausência total de bugs nem preparo para produção sem evidência.
</contexto_da_autora>

<regras_de_honestidade_e_evidencia>
Estas regras valem para todo o trabalho (código, documentação, relatórios de etapa, PDF e mensagens finais) e têm prioridade sobre qualquer instrução de estilo.

R1. Só afirme o que foi executado e verificado. Termos como "testado", "CI verde", "funciona", "sem vulnerabilidades", "publicado" exigem a evidência correspondente (saída de comando, URL, arquivo gerado). Sem evidência, escreva "não verificado" e explique o motivo.
R2. Não invente pesquisa, vagas, issues, métricas, benchmarks, depoimentos, bugs, datas ou histórico de commits.
R3. Separe sempre "risco antecipado" de "bug efetivamente observado".
R4. Nunca altere o resultado esperado de um teste apenas para fazê-lo passar. Antes, revise o requisito; se o requisito mudar, registre a decisão.
R5. Nunca pule, desabilite ou marque como "skip/xfail" um teste para obter sucesso, exceto quando houver justificativa técnica registrada no próprio teste e no relatório.
R6. Não diga que gerou um arquivo que não existe. Antes de citar um arquivo como entregue, confirme que ele existe (por exemplo, com `ls -l`).
R7. Funcionalidades comuns (verificação HTTP, alertas, dashboard) não devem ser apresentadas como invenções inéditas.
R8. Itens de roadmap nunca podem ser descritos como funcionalidades prontas.
R9. Se uma limitação de ambiente impedir uma etapa (sem internet, sem Docker, sem acesso ao GitHub, sem ferramenta de PDF), declare o bloqueio com precisão, entregue tudo o que for possível e um comando reproduzível para concluir a etapa depois.
</regras_de_honestidade_e_evidencia>

<produto>
## PulseOps — monitoramento explicável de APIs e serviços

### Cenário de requisitos (fictício)
Identifique este cenário como FICTÍCIO em toda a documentação:

Uma pequena equipe mantém APIs usadas por uma aplicação. Hoje, descobre problemas quando alguém reclama. Precisa acompanhar disponibilidade e lentidão, consultar evidências dos incidentes e receber alertas sem ser inundada por notificações repetidas.

### O que o PulseOps deve fazer
- Verificar endpoints HTTP/HTTPS periodicamente.
- Avaliar status HTTP e tempo de resposta.
- Registrar resultados e mudanças de estado.
- Abrir e encerrar incidentes segundo regras explícitas.
- Apresentar métricas e uma linha do tempo no dashboard.
- Entregar alertas sem bloquear o monitoramento.
- Permitir demonstrar falhas em ambiente local controlado.

### Prioridade
Um produto pequeno e completo, com lógica de domínio bem resolvida, vale mais que um produto grande e raso.

### Diferencial central (combinação dos cinco itens)
1. Explicação de cada mudança de estado.
2. Histórico confiável de incidentes.
3. Alertas persistidos e desacoplados das verificações.
4. Laboratório local que reproduz falhas e recuperações.
5. Documentação que conecta requisitos, código e testes.
</produto>

<pesquisa_inicial>
## Objetivo
Fazer uma pesquisa curta e fundamentada que refine esta especificação ANTES de definir os detalhes técnicos. Depois, seguir para a implementação. A pesquisa tem limite de tempo: ela não pode atrasar o desenvolvimento. Se algo não estiver acessível, registre e siga em frente.

## O que pesquisar
- Vagas brasileiras de back-end Python júnior e estágio.
  - Priorize remotas. Vagas híbridas/presenciais podem servir como referência técnica, desde que identificadas como tal.
  - Prefira fontes oficiais dos empregadores e plataformas de candidatura.
- Documentação oficial das bibliotecas usadas.
- Repositórios e issues dos projetos de referência.

## Referências iniciais
Vagas:
- https://vagas.solides.com.br/vaga/891428
- https://vagas.solides.com.br/vaga/870939
- https://remotar.com.br/job/166955/byx/desenvolvedor-backend-python-jr
- https://remotar.com.br/job/156535/delfos/desenvolvedor-python-jr

Projetos de referência:
- https://github.com/louislam/uptime-kuma
- https://github.com/TwiN/gatus
- https://github.com/healthchecks/healthchecks

Issues de referência:
- https://github.com/louislam/uptime-kuma/issues/4058
- https://github.com/louislam/uptime-kuma/issues/6046
- https://github.com/louislam/uptime-kuma/issues/3255

Documentação:
- https://fastapi.tiangolo.com/
- https://docs.sqlalchemy.org/
- https://www.python-httpx.org/
- https://docs.pytest.org/
- https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

## Vagas: o que registrar
Meta: aproximadamente 6 a 10 anúncios relevantes, se acessíveis. A quantidade nunca é motivo para atrasar o desenvolvimento.

Para cada anúncio, registre:
| Campo | Conteúdo |
|---|---|
| Empresa | |
| Título | |
| Senioridade | |
| Modalidade | remoto / híbrido / presencial |
| URL | |
| Data de consulta | AAAA-MM-DD |
| Status | aberto / encerrado / não confirmado |
| Requisitos obrigatórios | |
| Diferenciais | |
| Tipo de fonte | primária (empregador) / agregador |

Não confunda vagas de QA, dados ou pleno com back-end júnior. Se usar uma dessas como referência, marque-a como "adjacente".

## Matriz de competências
Monte a matriz:

requisito da vaga → funcionalidade do PulseOps → arquivo/módulo → teste ou demonstração

Na Etapa 1 ela terá caminhos planejados. Ela DEVE ser atualizada com caminhos reais depois da implementação.

## Projetos de referência
1. Compare uptime-kuma, gatus e healthchecks por: escopo, execução local, documentação, incidentes, alertas e testes.
2. Examine algumas issues relevantes (incluindo as listadas), lendo o contexto e o status de cada uma.
3. Para cada inspiração, registre:

problema relatado → decisão para o PulseOps → cenário de teste

Restrições:
- Não copie código ou design sem respeitar a licença do projeto de origem.
- Não afirme ter corrigido bugs de terceiros. O que se faz é implementar proteções no PulseOps.

## Sem internet
Se não houver acesso à internet, registre a limitação no documento de pesquisa e prossiga com esta especificação. Não invente resultados.

## Entregável
`docs/pesquisa-de-mercado.md` (tabela de vagas, matriz de competências, comparação de referências, tabela de inspirações, data das consultas e limitações).
</pesquisa_inicial>

<stack_e_arquitetura>
## Stack principal
| Item | Uso esperado |
|---|---|
| Python | versão estável e compatível com todas as dependências |
| FastAPI | API e rotas do dashboard |
| Pydantic | contratos de entrada/saída e configuração |
| PostgreSQL | persistência |
| SQLAlchemy | ORM com a API moderna (2.x, `select()`, `Mapped[...]`) |
| Alembic | migrações |
| HTTPX | cliente das verificações e dos webhooks |
| Pytest | testes |
| Docker e Docker Compose | execução local reproduzível |
| GitHub Actions | CI |
| Ruff | lint e formatação |
| Verificador de tipos | escolha UM (mypy ou pyright) e justifique |
| Jinja2 + HTML + CSS + JavaScript mínimo | dashboard; outra abordagem só com justificativa concreta |

Regras de dependências:
- Verifique versões compatíveis entre si.
- Fixe as dependências de forma reproduzível (arquivo de lock).
- Escolha UM gerenciador de dependências (por exemplo, uv ou Poetry) e mantenha um único fluxo principal em README, Dockerfile e CI.

## Arquitetura de processos
- Uma aplicação modular, em um único repositório.
- Processo 1: API + dashboard.
- Processo 2: worker separado, responsável pelas verificações e pela entrega de alertas.
- A mesma imagem Docker pode atender aos dois processos (comandos diferentes).
- PostgreSQL como persistência.

Proibições:
- Não execute o agendador dentro de cada worker do servidor web (por exemplo, em cada worker do Uvicorn/Gunicorn).
- Não dependa de `BackgroundTasks` do FastAPI para trabalho periódico durável.
- Não adicione Kubernetes, Kafka, microsserviços, Redis, Celery ou IA para preencher currículo. Complexidade adicional só entra se um requisito justificar, e a justificativa vai para uma ADR.

Escala suportada:
- Comece com UM worker suportado e documente essa limitação.
- Mesmo com um único worker, proteja contra verificações sobrepostas e incidentes duplicados (o banco deve garantir isso, não apenas a memória do processo).

## Organização de responsabilidades
Separe o código entre:
- Rotas e contratos (schemas).
- Casos de uso e regras de domínio.
- Persistência.
- Cliente de verificação.
- Agendamento.
- Notificações.
- Interface (templates e estáticos).

Evite dois extremos: arquivos gigantes e camadas que só repassam chamadas sem acrescentar nada.

## Orientação a objetos
Demonstre OO onde houver benefício real:
- Encapsulamento de comportamento (por exemplo, a regra de transição de estados).
- Composição.
- Dependências substituíveis (relógio, transporte HTTP, notificador).
- Pelo menos uma interface/`Protocol` útil para verificadores ou notificadores.

Não force herança e não crie classes para toda função. Registre (na documentação e depois no PDF) onde funções simples foram a melhor escolha e por quê.

## Regras para código assíncrono (se usar async)
- Não bloqueie o event loop (nada de I/O síncrono dentro de corrotinas).
- Reutilize clientes HTTP (`httpx.AsyncClient`) corretamente, com ciclo de vida definido.
- Limite a concorrência (por exemplo, com semáforo).
- Use uma sessão de banco por unidade de trabalho/tarefa.
- Não compartilhe `AsyncSession` entre tarefas concorrentes.
- Não mantenha transação nem bloqueio de banco aberto durante chamadas de rede. Sequência obrigatória: reservar a execução (transação curta) → fazer a requisição HTTP sem transação aberta → processar e persistir o resultado (transação curta).
</stack_e_arquitetura>

<requisitos_funcionais>
Cada RF abaixo deve ganhar critérios de aceitação verificáveis em `docs/requisitos.md` na Etapa 1.

### RF01 — Cadastro de monitores
Operações: criar, listar, consultar, editar, pausar e arquivar.

Campos mínimos:
- Identificador.
- Nome e descrição opcional.
- URL.
- Método: GET ou HEAD.
- Intervalo.
- Timeout.
- Status HTTP aceitos.
- Limite de latência.
- Quantidade de falhas consecutivas para abrir incidente.
- Quantidade de sucessos consecutivos para recuperação.
- Datas de criação e atualização.
- Situação de ativação.

Regras:
- Defina limites seguros (mínimos e máximos) para intervalo, timeout e limiares, e evite verificações agressivas.
- Valide combinações (exemplo: timeout menor que o intervalo; limite de latência menor ou igual ao timeout).
- O arquivamento deve preservar o histórico (nada de exclusão física de checks/incidentes ligados ao monitor).
- Defina e documente o que acontece com um incidente aberto quando o monitor é pausado ou arquivado. A decisão é sua, mas precisa ser explícita, testada e registrada em ADR.

### RF02 — Verificações
Cada verificação registra:
- Monitor.
- Identidade da execução agendada (chave que identifica unicamente aquela execução).
- Instante previsto e instante observado.
- Duração medida com relógio monotônico.
- Status HTTP, quando houver.
- Resultado.
- Categoria de erro.
- Explicação curta, sem dados sensíveis.

Categorias que devem ser distinguidas:
- Resposta saudável.
- Resposta lenta.
- Status inesperado.
- Timeout.
- Falha de conexão/DNS.
- Falha TLS.
- Erro interno do próprio monitor.

Regras:
- Erro do PulseOps ou do banco NÃO pode virar automaticamente "serviço monitorado caiu". Erros internos não contam como falha do alvo.
- Não armazene corpos completos de resposta por padrão. Qualquer leitura necessária deve ter limite de tamanho.
- Mantenha a verificação TLS habilitada.

### RF03 — Estados e incidentes
Defina uma máquina de estados clara que SEPARE:
- Estado operacional do monitor (ativo, pausado, arquivado).
- Saúde do serviço monitorado.

Estados de saúde a contemplar:
- Sem dados.
- Saudável.
- Degradado.
- Indisponível.
- Pausado.
- Dados desatualizados (pode ser condição derivada, calculada a partir da última verificação e do heartbeat do worker).

Nunca exiba verde indefinidamente quando o worker parou.

Defina formalmente (em `docs/requisitos.md` e com testes):
1. O que conta como falha.
2. Como a lentidão afeta incidentes (se resposta lenta conta ou não como falha para abertura; a decisão precisa ser explícita).
3. Como funcionam os limiares consecutivos.
4. Quando os contadores são reiniciados.
5. Como uma alteração de configuração afeta os contadores.
6. Quando um incidente começa, é confirmado e termina.
7. A diferença entre primeira falha observada e confirmação da abertura.
8. O comportamento após reinício do worker.

Exemplo obrigatório (deve virar teste):
- Limiar de abertura = 3 falhas consecutivas.
- Falha, falha, sucesso → nenhum incidente.
- Falha, falha, falha → exatamente UM incidente aberto.
- Novas falhas → atualizam esse mesmo incidente (não criam outro).
- Recuperação → exige o número configurado de sucessos consecutivos.

Garantias:
- O BANCO deve impedir que um monitor tenha múltiplos incidentes abertos incompatíveis com o modelo adotado (por exemplo, índice único parcial em `monitor_id` onde `status = 'open'`).
- O incidente/evento deve guardar os dados necessários para explicar a decisão (limiares e valores vigentes no momento), mesmo após mudanças posteriores na configuração do monitor.
- Explicações concretas na interface, por exemplo:
  "Incidente confirmado após três falhas consecutivas; último resultado: timeout de 5 segundos."

### RF04 — Histórico
Permitir consultar:
- Verificações paginadas.
- Filtros por período e por resultado.
- Incidentes abertos e encerrados.
- Linha do tempo de cada incidente.
- Motivo de abertura e de recuperação.
- Notificações e tentativas de entrega.

Use ordenação estável (com critério de desempate, por exemplo `(timestamp, id)`) e limites de paginação.

### RF05 — Métricas
Mostrar:
- Quantidade de verificações.
- Percentual de verificações disponíveis.
- Percentual de verificações saudáveis.
- Latência média e p95.
- Quantidade e duração observada de incidentes.
- Última verificação.
- Estado de atualização dos dados.

Não chame a proporção de checks bem-sucedidos de "disponibilidade temporal exata".

Defina e documente:
- A fórmula de cada métrica.
- O denominador.
- O tratamento de respostas lentas.
- O tratamento de timeouts.
- Intervalos sem dados.
- Monitores pausados.
- Incidentes que atravessam os limites da janela.
- Períodos sem amostras.
- O método do percentil (por exemplo, nearest-rank ou interpolação linear; escolha um e cite).

Regras:
- Mostre "N/A" quando não houver base válida, em vez de inventar 100% ou 0%.
- Armazene tudo em UTC e converta explicitamente na interface.
- Use janelas temporais consistentes, preferencialmente início inclusivo e fim exclusivo: `[início, fim)`.

### RF06 — Alertas confiáveis
Implemente um canal webhook genérico e um receptor local demonstrável.

Modelo obrigatório (padrão outbox):
- Uma transição de incidente cria um evento persistente NA MESMA TRANSAÇÃO da mudança de domínio.
- Um entregador independente processa esses eventos.

Exigências:
- Timeout.
- Retentativas limitadas.
- Backoff com limite máximo.
- Registro de cada tentativa.
- Estado de entrega.
- Chave estável de evento.
- Tratamento de falha permanente.
- Nenhum envio a cada verificação repetida (só em transições).
- Alertas de abertura e de recuperação.
- Falha no webhook não pode interromper novas verificações.
- A proteção de destino (SSRF) também se aplica às URLs de webhook.

Semântica de entrega:
- Explique que retentativas podem gerar duplicatas no destinatário (entrega "pelo menos uma vez").
- Não prometa "exactly once".
- Envie uma identidade de evento que permita deduplicação e demonstre a deduplicação no receptor local.

### RF07 — Dashboard
Uma ferramenta funcional, sóbria e consistente. Não é uma landing page promocional.

Telas/elementos:
- Resumo dos estados.
- Lista de monitores.
- Formulário de cadastro e edição.
- Detalhe do monitor com gráfico de latência.
- Histórico de checks.
- Incidentes e linha do tempo.
- Estado das notificações.
- Identificação visível do modo de demonstração.

Estados de interface:
- Carregando, quando aplicável.
- Vazio.
- Erro.
- Sem dados.
- Dados desatualizados.

Acessibilidade:
- Rótulos de texto além de cores.
- Foco visível.
- Contraste adequado.
- Navegação por teclado.

Dados:
- Gráficos consomem dados reais do sistema.
- Dados sintéticos precisam estar identificados como tal.

### RF08 — Acesso
Instalação para UM operador, com autenticação real e simples.

Modelo preferido:
- Usuário administrador criado por comando de linha (CLI).
- Senha com hash usando biblioteca consolidada (por exemplo, argon2 ou bcrypt).
- Sessão em cookie HttpOnly.
- CSRF nas operações da interface.
- Expiração e logout.
- Atributo Secure configurado adequadamente quando em HTTPS.

Se adotar outro modelo, justifique em ADR e mantenha segurança equivalente.

Fora de escopo: cadastro público, recuperação de senha por e-mail, multitenancy, OAuth de terceiros.

Proteja todos os endpoints e ações administrativas, incluindo configuração de monitores, incidentes e destinos de alertas. Não coloque token administrativo no JavaScript servido publicamente.

### RF09 — Saúde do próprio PulseOps
Implementar:
- Liveness.
- Readiness com verificação limitada (com timeout) das dependências.
- Heartbeat do worker.
- Logs estruturados com contexto (monitor, execução, incidente).
- Tratamento explícito de worker parado (refletido como "dados desatualizados").

Documentar que um monitoramento hospedado junto dos alvos tem limitações e que a indisponibilidade total do próprio PulseOps exige observação externa.
</requisitos_funcionais>

<seguranca_e_rede>
O sistema recebe URLs e faz requisições a partir do servidor. Trate SSRF como requisito de produto, não como detalhe.

## Política para a primeira versão
- Prefira destinos explicitamente permitidos pelo operador e política de saída restrita.
- Não exponha um serviço público que consulte URLs arbitrárias sem proteção.

## Controles a contemplar
- Apenas os esquemas `http` e `https`.
- Bloqueio de credenciais embutidas na URL (`user:pass@host`).
- Portas permitidas.
- Bloqueio de endereços privados, loopback, link-local, reservados e de metadata de nuvem (por exemplo, `169.254.169.254`).
- IPv4, IPv6 e formas equivalentes de endereço (decimal, octal, hexadecimal, IPv4 mapeado em IPv6 etc.).
- Resolução DNS.
- Redirecionamentos.
- DNS rebinding.
- Limites de conexão, de tamanho de resposta e de tempo.

## Regras técnicas
- Uma checagem de DNS antes da requisição NÃO elimina, sozinha, o risco de rebinding. Escolha controles compatíveis com a implementação, como resolver o nome, validar o IP e conectar exatamente nesse IP validado (mantendo o Host/SNI corretos), além de restrições de saída. Se restar alguma limitação, documente-a no modelo de ameaças e restrinja o uso suportado.
- Não siga redirecionamentos automaticamente sem revalidar o destino. Desabilitar redirecionamentos na primeira versão é aceitável.
- O laboratório poderá alcançar serviços internos específicos apenas por uma configuração de demonstração explícita e restrita (por exemplo, uma lista nominal de hosts do Compose ativa só no perfil de demonstração). Não crie uma opção genérica que libere toda a rede privada.

## Outros requisitos de segurança
- Segredos fora do Git.
- `.env.example` sem credenciais reais.
- Redação (mascaramento) de informações sensíveis nos logs.
- Consultas parametrizadas.
- Escape de conteúdo na interface (autoescape do Jinja2 ligado).
- CORS restrito, se for necessário.
- Limites de entrada e de paginação.
- Containers sem privilégios desnecessários (usuário não-root).
- Banco sem porta exposta publicamente no Compose padrão.
- Não incluir headers secretos de autenticação dos alvos no MVP. Se isso for adicionado no futuro, exigir armazenamento e mascaramento adequados (registrar como roadmap, não como funcionalidade).

## Entregável
`docs/modelo-de-ameacas.md` com ativos, ameaças, controles implementados, testes que os verificam e limitações remanescentes.
</seguranca_e_rede>

<laboratorio_de_falhas>
Diferencial OBRIGATÓRIO.

## Serviços locais controlados
Devem permitir reproduzir:
- HTTP saudável.
- Resposta lenta.
- Erro 500.
- Timeout.
- Recuperação.
- Webhook temporariamente indisponível.

Os controles do laboratório ficam restritos ao perfil de demonstração (por exemplo, `docker compose --profile demo`).

## Roteiro executável
Um script (por exemplo, `scripts/demo.sh` ou `make demo`) que:
1. Sobe o ambiente.
2. Prepara os monitores sem duplicá-los (idempotente: rodar duas vezes não cria monitores repetidos).
3. Executa verificações saudáveis.
4. Provoca uma falha.
5. Demonstra o limiar de abertura.
6. Confirma que existe apenas UM incidente aberto.
7. Restaura o alvo.
8. Demonstra a recuperação.
9. Indisponibiliza o receptor de alertas.
10. Comprova que o monitoramento continua.
11. Restaura o receptor e mostra a retentativa.

Cada passo deve imprimir o que está verificando e falhar com código de saída diferente de zero se a verificação não se confirmar.

## Testes automatizados versus demonstração manual
- Testes automatizados: usem relógio controlável e transportes simulados (por exemplo, `httpx.MockTransport`) onde adequado. A suíte não pode depender de `sleep` longos nem de sites externos.
- Demonstração manual: pode usar intervalos curtos, mas apenas no modo de laboratório.
</laboratorio_de_falhas>

<banco_de_dados_e_consistencia>
## Entidades mínimas
- Monitores.
- Resultados de verificações.
- Incidentes.
- Eventos relevantes do incidente.
- Notificações pendentes e entregues.
- Tentativas de entrega (se o modelo precisar).
- Operador/sessão, conforme a autenticação adotada.

## Entregáveis
- Diagrama entidade-relacionamento (em `docs/arquitetura.md`, por exemplo em Mermaid).
- Migrações Alembic.
- Chaves estrangeiras.
- Restrições (CHECK, UNIQUE, índices únicos parciais).
- Índices ligados às consultas reais (justifique cada índice pela consulta que ele atende).
- Política de retenção de checks.
- Preservação dos incidentes.
- Estratégia de arquivamento.

## Consistência
- A transação que processa um resultado deve manter consistentes: resultado, contadores, estado, incidente e evento de alerta. Ou tudo é gravado, ou nada.
- Considere falha entre a requisição HTTP e a persistência. Defina como uma execução é identificada (identidade da execução agendada) e como o reprocessamento dessa mesma execução evita duplicação (por exemplo, restrição única sobre a identidade da execução).
- Após reinício, não execute uma avalanche com todos os checks perdidos. Defina uma política explícita de retomada e de lacunas (por exemplo, agendar a partir de "agora" e registrar a lacuna como período sem dados).
- Verificações manuais, se existirem, devem usar o mesmo controle de sobreposição, e seu efeito em métricas e incidentes deve ser documentado.
</banco_de_dados_e_consistencia>

<qualidade_e_testes>
## Ciclo de trabalho
implementar → executar → analisar → corrigir → adicionar teste de regressão quando necessário → verificar o fluxo afetado

Repetir a mesma suíte várias vezes não é validação. Varie cenários e ataque os riscos do sistema.

## Tipos de validação
- Testes unitários das regras de domínio.
- Testes de API.
- Integração com PostgreSQL real (SQLite NÃO substitui PostgreSQL nos testes de integração).
- Migrações aplicadas em banco limpo.
- Integração entre worker e persistência.
- Fluxo completo do laboratório.
- Interface nos fluxos principais.
- Lint, formatação e tipagem.
- Auditoria de dependências (por exemplo, pip-audit).
- Construção e execução da imagem Docker.

## Cenários obrigatórios
Cada item deve ter pelo menos um teste ou demonstração rastreável na matriz requisito → evidência:
1. URL e configuração inválidas.
2. Resposta 200 lenta.
3. Status não aceito.
4. Falha de rede e falha TLS.
5. Limiar de falhas.
6. Recuperação com sucessos consecutivos.
7. Alternância entre falha e sucesso.
8. Incidente sem duplicação.
9. Resultado reprocessado.
10. Check sobreposto.
11. Pausa e retomada.
12. Alteração de configuração.
13. Reinício com incidente aberto.
14. Worker parado e dados desatualizados.
15. Banco temporariamente indisponível.
16. Webhook lento ou indisponível.
17. Retentativa e deduplicação no receptor.
18. UTC e limites temporais.
19. Métricas sem dados e p95 com amostra pequena.
20. Arquivamento com preservação do histórico.
21. Autenticação, autorização e CSRF.
22. Bloqueios SSRF e de redirecionamento.
23. Tentativa de injeção na interface.
24. Retenção de dados.
25. Inicialização limpa seguindo o README.

## Cobertura
- Estabeleça metas de cobertura especialmente para regras de domínio e segurança.
- Percentual global não é sinônimo de qualidade.
- Não crie testes vazios ou sem asserções relevantes para inflar cobertura.

## Ensaio de carga local
Modesto e reproduzível, com alvos controlados (do laboratório). Registre:
- Quantidade de monitores.
- Intervalo.
- Concorrência.
- Máquina (CPU, memória, sistema).
- Duração.
- Erros.
- Latência da API.

Não invente nem extrapole capacidade de escala.

## Registro de bugs (`docs/registro-de-bugs.md`)
Apenas bugs realmente encontrados durante o desenvolvimento, cada um com:
- Sintoma.
- Como reproduzir.
- Causa.
- Correção.
- Teste de regressão.
- Limitação remanescente.

Riscos antecipados ficam em outra seção (ou no modelo de ameaças), nunca misturados com bugs observados.
</qualidade_e_testes>

<execucao_por_etapas>
## Antes de editar qualquer arquivo
- Inspecione o diretório de trabalho e as instruções locais (por exemplo, `CLAUDE.md`, `README`, `.git`).
- Verifique se já existem arquivos ou alterações não commitadas.
- Preserve trabalho alheio.
- Não sobrescreva projetos existentes. Se o diretório já tiver outro projeto, crie o PulseOps em um subdiretório novo e informe.

## Persistência entre sessões
Logo no início:
1. Salve esta especificação, sem cortes, em `docs/especificacao.md`.
2. Crie `docs/progresso.md` com: etapa atual, o que foi entregue, como foi verificado, pendências e bloqueios. Atualize esse arquivo ao final de cada etapa.
3. Crie um `CLAUDE.md` curto na raiz apontando para esses dois arquivos e listando os comandos principais (instalar, testar, lint, subir o ambiente), para que uma nova sessão retome o trabalho sem perder requisitos.

## Etapas
Cada etapa tem um critério de saída. Só avance quando ele for atendido ou quando um bloqueio real estiver registrado em `docs/progresso.md`.

### Etapa 1 — Refinamento
Entregas: pesquisa; escopo; critérios de aceitação por RF; matriz de competências; decisões de arquitetura (ADRs curtas); ameaças e limitações; plano curto de implementação.
Critério de saída: `docs/pesquisa-de-mercado.md`, `docs/requisitos.md`, `docs/decisoes/` e `docs/modelo-de-ameacas.md` existem com conteúdo real (versão inicial).

### Etapa 2 — Base executável
Entregas: dependências fixadas; configuração; PostgreSQL; migração inicial; API mínima; Compose; primeiro teste de integração.
Critério de saída: `docker compose up` sobe API e banco; migração aplica em banco limpo; o teste de integração passa contra PostgreSQL real.

### Etapa 3 — Primeira fatia completa (ponta a ponta)
Entregas: cadastrar monitor → worker verifica → resultado persistido → resultado consultável pela API.
Critério de saída: um teste ponta a ponta cobre esse fluxo e passa.

### Etapa 4 — Domínio
Entregas: estados; incidentes; contadores; consistência transacional; comportamento após reinício; testes de regressão.
Critério de saída: o exemplo obrigatório do RF03 e os cenários 5 a 15 de <qualidade_e_testes> estão cobertos e passando.

### Etapa 5 — Alertas
Entregas: evento persistente (outbox); entregador; retentativas com backoff; receptor local com deduplicação; testes de isolamento de falhas.
Critério de saída: os cenários 16 e 17 passam; falha do webhook comprovadamente não interrompe verificações.

### Etapa 6 — Interface e métricas
Entregas: autenticação; dashboard; gráficos; histórico; estados vazio/erro/sem dados/desatualizado; validação visual.
Critério de saída: os cenários 18, 19, 21 e 23 passam; capturas de tela reais foram feitas dos fluxos principais.

### Etapa 7 — Revisão
Entregas: revisão de segurança; retenção; logs; ensaio de carga local; execução limpa do zero seguindo o README; correções comprovadas.
Critério de saída: todos os cenários obrigatórios têm evidência; lint, formatação, tipagem e auditoria de dependências executados com saída registrada.

### Etapa 8 — GitHub
Entregas: README; documentação; screenshots reais; pipeline de CI; revisão do diff completo; publicação e verificação, quando houver acesso e destino autorizado.
Critério de saída: repositório local pronto e, se publicado, URL e resultado do CI confirmados.

### Etapa 9 — Material de estudo
Entregas: PDF vinculado à versão final do código; conferência técnica e visual; correção de divergências; atualização do repositório se o material fizer parte dele.
Critério de saída: os itens de <pdf_de_estudo> foram cumpridos e o PDF foi revisado visualmente.

## Relatório ao final de cada etapa
Formato fixo, curto:

```
### Etapa N — <nome>
Entregue: <lista objetiva>
Como verifiquei: <comandos executados e resultado resumido>
Falta: <pendências>
Bloqueios: <bloqueios reais ou "nenhum">
```

## Autonomia
- Prossiga entre etapas sem pedir confirmação para cada arquivo ou decisão rotineira.
- Resolva escolhas rotineiras com julgamento técnico, registre a decisão (ADR ou `docs/progresso.md`) e avance.
- Faça perguntas apenas quando uma informação indispensável não puder ser inferida (por exemplo, o repositório GitHub de destino).
- Não pare depois de apresentar o planejamento.
</execucao_por_etapas>

<github_e_documentacao>
## Princípios
Documentação específica, natural e revisável.

## README principal
- Em português, com nomes de código (variáveis, módulos, endpoints) em inglês.
- Versão em inglês é opcional e só deve existir se estiver consistente com a versão em português.
- O início do README deve permitir entender rapidamente: que problema o PulseOps resolve, como funciona, como executá-lo e como reproduzir um incidente.

Estrutura esperada:
1. Nome e descrição objetiva.
2. Screenshot real da aplicação.
3. Problema e cenário fictício.
4. Funcionalidades implementadas.
5. Início rápido.
6. Demonstração de falha e recuperação.
7. Arquitetura compacta.
8. Regras importantes.
9. Testes e comandos.
10. Decisões e alternativas.
11. Limitações.
12. Referências e licença.

## Documentos de aprofundamento (em `docs/`)
| Documento | Conteúdo |
|---|---|
| `requisitos.md` | requisitos e critérios de aceitação |
| `arquitetura.md` | arquitetura e modelo de dados (com diagrama ER) |
| `decisoes/` | decisões arquiteturais curtas (ADRs) |
| `estrategia-de-testes.md` | estratégia de testes |
| `modelo-de-ameacas.md` | modelo de ameaças |
| `pesquisa-de-mercado.md` | pesquisa de vagas e referências |
| `registro-de-bugs.md` | registro real de bugs |
| `operacao.md` | operação e troubleshooting |
| `matriz-de-rastreabilidade.md` | requisito → implementação → evidência |

## Evite
- Excesso de emojis e badges.
- Frases como "revolucionário", "enterprise-grade" ou "altamente escalável".
- Lista de tecnologias sem explicar seu uso.
- Comentários que traduzem literalmente cada instrução do código.
- Abstrações sem finalidade.
- Roadmap apresentado como funcionalidade pronta.
- Logos de empresas sugerindo vínculo.
- Métricas ou depoimentos inventados.

## Honestidade sobre autoria
- Documente como projeto pessoal desenvolvido a partir de um cenário de requisitos. Não apresente como trabalho contratado nem como experiência em equipe.
- Se houver menção ao uso de IA, descreva o processo factual e a responsabilidade de revisão, sem afirmar que Amanda já compreende o que ainda vai estudar.

## Commits
- Commits pequenos e coerentes com as mudanças reais, se o ambiente permitir.
- Não fabrique datas nem histórico artificial.

## GitHub Actions (CI)
O workflow deve conter:
- Lint e formatação.
- Tipagem.
- Testes.
- PostgreSQL como serviço.
- Aplicação das migrações.
- Build da imagem Docker, conforme viabilidade.
- Permissões mínimas (`permissions:` explícito, somente leitura quando possível).

Diferencie CI de implantação: não chame de CD se o workflow não publica uma aplicação.

## Publicação — regras invioláveis
- Nunca faça force push.
- Nunca apague repositórios.
- Nunca sobrescreva um remoto existente.
- Se o repositório de destino não estiver identificado, prepare tudo localmente e peça apenas esse dado quando chegar a hora.
- Se houver autenticação e destino definidos, publique dentro do escopo autorizado e confira o resultado (URL do repositório e status do CI).
- Não afirme publicação ou execução remota sem URL/evidência.
</github_e_documentacao>

<pdf_de_estudo>
## Regras gerais
- Obrigatório. Não pode ser substituído por um resumo no chat.
- Produza o PDF DEPOIS da implementação e da revisão, refletindo o código entregue.
- Título sugerido: "PulseOps por dentro: guia de código, decisões e preparação para entrevistas".
- Extenso o necessário para cumprir o conteúdo, sem limite artificial de páginas e sem enchimento.
- Público: iniciante absoluta. Explique desde os fundamentos, sem pressupor familiaridade com termos técnicos.
- Entregue a fonte editável (por exemplo, Markdown + template, ou Typst/LaTeX) e o PDF.
- Se for necessário para a legibilidade, divida em volumes (por exemplo, guia principal e apêndice de código), mantendo todo o conteúdo solicitado.
- Gere os trechos de código a partir dos arquivos finais por script, sempre que possível, para evitar divergências entre o PDF e o repositório.
- Não entregue Markdown renomeado como PDF.

## Identificação (primeiras páginas)
- Versão.
- Data.
- Commit do código explicado (hash completo). Se o PDF ou sua fonte forem commitados depois, o hash citado é o do código explicado, e isso deve estar dito no documento.
- Pré-requisitos.
- Sumário com links.
- Caminho de estudo recomendado.

## Parte A — Problema e produto
- O que é API.
- O que é monitoramento.
- Por que uma resposta pode estar lenta sem estar indisponível.
- O que é um incidente.
- Qual problema cada funcionalidade resolve.
- Cenário fictício e limites do projeto.

## Parte B — Execução passo a passo
- Instalação.
- Terminal e diretórios.
- Ambientes e dependências.
- Variáveis de ambiente.
- Docker e Compose.
- Banco e migrações.
- Como iniciar e parar.
- Como conferir se está funcionando.
- Erros comuns e diagnóstico.

Para cada comando: explique cada componente, o resultado esperado e como confirmar o sucesso.

## Parte C — Arquitetura
- Responsabilidade de cada pasta e arquivo.
- Diferença entre rota, schema, entidade e serviço.
- Caminho de uma requisição.
- Caminho de uma verificação.
- Caminho de um incidente.
- Caminho de uma notificação.
- Diagramas legíveis.

## Parte D — Código explicado linha a linha
Escopo: todos os arquivos de código autoral e configurações relevantes à execução:
- Aplicação.
- Worker.
- Cliente HTTP.
- Persistência.
- Migrações.
- Segurança.
- Templates.
- JavaScript e CSS autorais.
- Testes.
- Docker.
- CI.
- Scripts do laboratório.

Exclusões (devem ser listadas explicitamente no PDF): dependências externas, arquivos de lock e artefatos gerados não são explicados linha a linha.

Para cada arquivo:
1. Caminho e finalidade.
2. Código com a numeração de linhas da versão final.
3. Explicação de cada linha significativa.
4. Origem e tipo dos dados.
5. Efeito de cada função, classe e bloco.
6. Relação com os outros arquivos.
7. Falhas que podem ocorrer.
8. Testes que verificam seu comportamento.

Forma:
- Trechos pequenos seguidos da explicação. Nada de grandes blocos de código ilegíveis.
- Linhas estruturais repetitivas podem ser agrupadas, mas nenhum comportamento relevante pode ficar sem explicação.
- Para padrões repetidos, explique o primeiro por completo e identifique os demais com seus intervalos de linhas e particularidades.
- Não coloque comentários didáticos em todas as linhas do código de produção. A explicação detalhada fica no material de estudo.

## Parte E — Fundamentos de Python aplicados
- Tipos.
- Coleções.
- Funções e argumentos.
- Imports e módulos.
- Classes e instâncias.
- Encapsulamento e composição.
- Protocolos ou interfaces utilizados.
- Exceções.
- Context managers.
- Tipagem.
- async/await.
- Concorrência e seus limites.
- Injeção de dependências.

Mostre onde cada conceito aparece no PulseOps e por que foi usado. Diferencie recursos realmente usados de conceitos apresentados só para comparação.

## Parte F — Banco e SQL
- Modelo relacional.
- Chaves.
- Relacionamentos.
- Constraints.
- Índices.
- ORM.
- SQL correspondente às consultas principais.
- Transações e rollback.
- Migrações.
- Consistência e concorrência.

## Parte G — Qualidade e segurança
- Teste unitário versus teste de integração.
- Fixtures e mocks.
- Por que PostgreSQL real importa.
- Testes de regressão.
- SSRF com exemplo seguro.
- Autenticação, sessão e CSRF.
- Retentativas e duplicatas.
- Bugs reais encontrados e corrigidos (a partir de `docs/registro-de-bugs.md`).
- Limitações ainda existentes.

## Parte H — Entrevistas
Pelo menos 30 perguntas específicas sobre o projeto. Cada uma com:
- Resposta curta.
- Explicação aprofundada.
- Arquivo ou trecho relacionado.
- Possível pergunta de aprofundamento.
- Limite do que Amanda pode afirmar honestamente.

Perguntas obrigatórias (incluídas nas 30):
1. Por que FastAPI?
2. Onde há orientação a objetos?
3. Por que composição?
4. O que acontece quando o worker reinicia?
5. Como impedir incidentes duplicados?
6. Por que uma sessão SQLAlchemy não deve ser compartilhada entre tarefas?
7. Por que não executar tudo na rota?
8. Como funciona a transação?
9. Qual a diferença entre lentidão e falha?
10. Como calcular métricas sem dados?
11. O que ocorre se o webhook cair?
12. Por que a entrega pode se repetir?
13. Como o projeto trata SSRF?
14. Qual a limitação de escala?
15. O que você mudaria numa versão comercial?

## Parte I — Apresentação
- Explicação de 30 segundos.
- Explicação de 2 minutos.
- Roteiro de demonstração de 5 minutos.
- Descrição para currículo baseada apenas no que foi entregue.
- O que mostrar primeiro a um recrutador.
- Afirmações que dependem de evidência ou de estudo antes de serem feitas.

## Parte J — Aprendizagem ativa
- Exercícios progressivos.
- Exercícios de prever o resultado antes de executar.
- Alterar uma regra e atualizar os testes.
- Implementar uma pequena melhoria.
- Diagnosticar uma falha sem consultar a resposta.
- Gabarito comentado em seção separada.
- Checklist de compreensão.

## Revisão visual obrigatória
Antes de entregar, renderize páginas do PDF em imagem e inspecione: paginação, fontes, margens, tabelas, links, diagramas e blocos de código sem cortes ou linhas estouradas. Corrija e gere de novo se houver problema.

## Se o ambiente impedir a geração
Declare o bloqueio com precisão (ferramenta ausente, erro exato), entregue a fonte completa e um comando reproduzível de geração. Não diga que gerou um arquivo inexistente.
</pdf_de_estudo>

<criterios_de_aceitacao>
Só declare o projeto concluído quando TODOS os itens tiverem evidência:
- [ ] Uma instalação limpa funciona seguindo o README.
- [ ] As migrações criam o banco.
- [ ] A autenticação funciona.
- [ ] O worker verifica alvos.
- [ ] O histórico persiste.
- [ ] Abertura e recuperação respeitam os limiares.
- [ ] Não há incidentes duplicados nos cenários testados.
- [ ] Falha de alerta não para as verificações.
- [ ] Retentativas são demonstráveis.
- [ ] Dashboard e métricas refletem dados reais.
- [ ] Ausência de dados e worker parado são visíveis.
- [ ] Restrições de rede foram verificadas.
- [ ] Testes, lint, formatação e tipagem têm evidência.
- [ ] O laboratório reproduz os fluxos.
- [ ] A documentação corresponde ao código.
- [ ] O PDF corresponde à versão final.
- [ ] A publicação está confirmada (com URL) ou claramente identificada como bloqueada.

Se algum item não puder ser atendido, o projeto NÃO está concluído: informe qual item, por quê e o que falta.
</criterios_de_aceitacao>

<formato_da_entrega_final>
Responda com estas seções, nesta ordem:
1. O que funciona.
2. Como executar.
3. Como demonstrar.
4. Verificações executadas e seus resultados (comando → resultado).
5. Bugs encontrados e corrigidos (com link para `docs/registro-de-bugs.md`).
6. Limitações.
7. URL do repositório, se publicado (ou o bloqueio).
8. Local do PDF e da fonte.
9. Primeiro roteiro de estudo para Amanda.
</formato_da_entrega_final>

<comece_agora>
1. Inspecione o ambiente.
2. Salve esta especificação em `docs/especificacao.md` e crie `docs/progresso.md` e `CLAUDE.md`.
3. Faça o refinamento objetivo (Etapa 1).
4. Implemente a primeira fatia executável (Etapas 2 e 3).
5. Continue pelas etapas até concluir.

Prioridades, em ordem: comportamento correto, execução reproduzível e capacidade de Amanda explicar o código.
</comece_agora>
