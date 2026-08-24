# OniSource

- O projeto se chama OniSource.
- É uma ferramenta INTERNA de inteligência de sourcing.
- Estamos somente na Fase 0 de prova de conceito.
- Simplicidade é prioridade.
- Não criar frontend.
- Não criar aplicação web.
- Não criar banco de dados.
- Não criar Docker.
- Não criar Redis.
- Não criar autenticação.
- Não criar SaaS.
- Não criar billing.
- Não criar CRM.
- Não criar envio automático de emails.
- Toda informação externa precisa de evidência.
- Ausência de evidência deve resultar em UNKNOWN.
- Nunca inventar especificações.
- Nunca inferir que uma empresa é fabricante apenas pelo domínio ou aparência do site.
- Falso positivo de fabricante é considerado pior que falso negativo.
- Benchmark ground truth deve ser fornecido por humanos.
- Codex não pode alterar o gabarito do benchmark para melhorar os resultados.
- Alterações devem ser testadas.
- Não ampliar o escopo sem solicitação explícita.
- A ferramenta de desenvolvimento está fixada no Codex até a POC terminar em PASS ou FAIL. Não trocar de agente no meio do projeto.
- Nunca executar comandos que exibam o conteúdo do `.env`, incluindo `cat .env`, `type .env` e `Get-Content .env`.
- Nunca imprimir o valor de `TAVILY_API_KEY` em logs, mensagens de erro ou saída de terminal.
- O diagnóstico de leitura de `TAVILY_API_KEY` deve informar somente se a variável foi encontrada ou não, sem revelar seu valor.
- Quando a suíte completa passar após uma alteração, criar automaticamente um commit local com mensagem descritiva em inglês.
- Regravar cassettes exige `--refresh-cassettes` e commit próprio; nunca incluir regravação de cassettes em commit automático.

## Comportamento do agente

### Antes de implementar
- Declare suas suposições. Se houver mais de uma interpretação, apresente-as
  e pare — não escolha em silêncio.
- Se existir caminho mais simples que atenda ao mesmo critério de
  verificação, diga antes de escrever código.
- Se algo estiver confuso, pare e nomeie o que está confuso.

### Escopo das mudanças
- Toda linha alterada deve rastrear até o pedido explícito.
- Não refatore, reformate nem "melhore" código adjacente que não foi pedido.
- Siga o estilo existente, mesmo que você preferisse outro.
- Remova apenas órfãos criados pelas suas próprias mudanças. Código morto
  pré-existente: mencione, não apague.

### Critérios de verificação
- Toda tarefa vira meta verificável antes de começar. "Corrigir bug" =
  escrever teste que reproduz, depois fazer passar.
- Tarefas de várias etapas: plano curto com a verificação de cada etapa.
- Suíte completa roda em cada commit, com contagem reportada.

### Regras invioláveis deste projeto
- O gabarito humano (benchmark/adjudicated_results.yaml) é imutável.
  Nenhuma etapa edita, reordena ou infere rótulos.
- Nenhuma chamada paga (busca, extração ou LLM) sem teto de crédito
  definido antes de rodar e sem aprovação explícita na mensagem.
- Nenhuma escolha de provedor sem aprovação explícita.
- Simplicidade é a regra, exceto onde uma abstração tem duas ou mais
  implementações reais em uso.
