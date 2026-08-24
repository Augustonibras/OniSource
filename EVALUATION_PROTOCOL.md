# OniSource — Protocolo de Avaliação da POC (Fase 0)

## 1. Finalidade

Este protocolo define como avaliar, de forma reproduzível, os dois casos obrigatórios da Fase 0. Ele não define implementação, não cria ground truth e não autoriza alteração de requisitos durante a execução.

Os resultados finais permitidos são:

- `CASE_A = PASS` ou `CASE_A = FAIL`;
- `CASE_B = PASS` ou `CASE_B = FAIL`;
- `POC = PASS` somente quando `CASE_A = PASS` e `CASE_B = PASS`; caso contrário, `POC = FAIL`.

Antes da execução completa, um caso pode estar operacionalmente como `NOT_EVALUATED`. Esse estado não é aprovação final.

## 2. Pré-condições e congelamento do benchmark

Antes de iniciar uma rodada avaliada, humanos devem:

1. fornecer e versionar o ground truth aplicável;
2. confirmar os controles humanos e preencher as classificações esperadas da Seção 8;
3. definir a regra de domínio oficial, os limiares de evidência empresarial, a regra de contradições e o limiar de corroboração documental;
4. definir hard constraints, weighted properties, pesos e limiares necessários do Caso A;
5. aprovar a fórmula e os limiares de `Evidence Confidence`;
6. identificar a versão/configuração do `SearchProvider` usada na rodada;
7. registrar data e hora de início da rodada.

Campos ainda não definidos permanecem `TBD_HUMAN`. Se um campo humano indispensável impedir a aplicação de um critério, o caso permanece `NOT_EVALUATED`; ele não pode receber `PASS` por omissão.

Transição obrigatória de estados:

1. decisão humana indispensável ainda `TBD` ou `TBD_HUMAN`: `NOT_EVALUATED`;
2. todas as decisões humanas indispensáveis definidas e rodada iniciada: o caso deve terminar em `PASS` ou `FAIL`;
3. evidência externa ausente durante a rodada: propriedade `UNKNOWN`, sem retorno do caso para `NOT_EVALUATED`.

`TBD` e `TBD_HUMAN` representam decisão humana ausente. `UNKNOWN` representa evidência externa ausente ou insuficiente.

Depois do início da rodada:

- o gabarito fica congelado;
- o Codex e o sistema não podem adicionar, remover ou alterar expectativas;
- correções humanas devem gerar uma nova versão do benchmark e uma nova rodada;
- resultado anterior não pode ser reescrito para aparentar melhora.

## 3. Artefatos obrigatórios de cada rodada

Cada caso deve produzir:

- identificação do caso e da versão do benchmark;
- configuração do provider;
- log das consultas geradas com `query_id` e `query_family`;
- resultados de busca e URLs únicas;
- vínculo entre cada resultado e o `query_id` que o retornou;
- inventário de resultados `INCLUDED` e `EXCLUDED`, com motivo de exclusão;
- log de fetch com estado terminal por tentativa;
- documentos candidatos e classificação de proveniência;
- propriedades extraídas com o contrato completo de evidência;
- classificação de empresas com evidências favoráveis, contrárias e independentes;
- candidatos e decisões de avaliação;
- métricas brutas e taxas calculadas;
- lista de erros críticos, se houver;
- decisão final do caso com justificativa ligada aos critérios deste protocolo.

## 4. Gate global de segurança

Verificar separadamente em cada caso:

1. Algum trader foi classificado como `VERIFIED_MANUFACTURER`?
2. Algum documento third-party foi classificado como `OFFICIAL`?
3. Alguma especificação sem evidência foi apresentada como fato?
4. Alguma especificação foi inventada pelo modelo?

Se a resposta for “sim” a qualquer pergunta, o caso recebe `FAIL` imediatamente. O erro deve ser preservado no relatório; corrigir o resultado exige nova rodada, não alteração retroativa do benchmark.

## 5. Avaliação do Caso A — produto de marca

### 5.1 PASS do Caso A

`CASE_A = PASS` somente se todos os critérios abaixo forem satisfeitos:

1. **Entrada correta:** a referência usada é BILLIONS R996 Titanium Dioxide.
2. **Descoberta nominal e técnica:** o log contém consultas por referência nominal e consultas independentes baseadas em características técnicas documentadas; as consultas técnicas não dependem de “equivalent to R996” ou “alternative to R996”; e ao menos um candidato incluído foi retornado por consulta `TECHNICAL`, com rastreabilidade por `query_id`.
3. **Origem das características:** toda característica usada para busca ou comparação vem de evidência do produto de referência ou de entrada humana versionada.
4. **Controles positivos:** Tronox, KRONOS e LB Group são descobertos e avaliados; o ground truth permanece `MANUFACTURER`; e a classificação produzida coincide com a classificação esperada definida por humanos antes da rodada.
5. **Controle negativo:** Qingdao Lidayouxuan não recebe `VERIFIED_MANUFACTURER` sem evidência independente suficiente, e o documento R6618 não recebe `OFFICIAL` automaticamente.
6. **Comparação demonstrada:** todos os candidatos incluídos após deduplicação possuem registros comparativos com os campos mínimos do Caso A; cada exclusão usa um motivo permitido e preserva a rastreabilidade; propriedades ausentes aparecem como `UNKNOWN`.
7. **Fabricante verificado com cautela:** cada classificação empresarial obedece aos critérios documentados; domínio semelhante, aparência do site e material promocional isolado não são usados como prova de fabricação.
8. **Documentos classificados por proveniência:** todo TDS ou outro documento utilizado recebe `OFFICIAL`, `CORROBORATED`, `THIRD_PARTY` ou `UNVERIFIED` com justificativa rastreável.
9. **Hard constraints eliminatórios:** todos os hard constraints fornecidos por humanos são avaliados antes das propriedades ponderadas; candidato que falha em qualquer hard constraint não é aprovado como match.
10. **Pesos humanos:** nenhum peso é criado ou ajustado automaticamente; pesos ausentes permanecem `TBD`.
11. **Scores separados:** `Technical Match` e `Evidence Confidence` são calculados e reportados separadamente, sem colapso em score único.
12. **Dimensões fora de escopo:** `Brazil Import Viability` e `Commercial Fit` aparecem como `NOT_EVALUATED` e não afetam a decisão.
13. **Evidência completa:** toda propriedade `EVIDENCED` possui valor e ao menos um item completo em `evidence[]`; toda propriedade `UNKNOWN` possui `value = UNKNOWN` e não apresenta fato sem evidência; fontes consultadas sem suporte permanecem em `sources_consulted[]`.
14. **Métricas completas:** todos os contadores e taxas obrigatórios são apresentados e aritmeticamente consistentes.
15. **Gate crítico limpo:** nenhum erro crítico da Seção 4 ocorreu.

O `PASS` do Caso A comprova capacidade de descoberta e comparação; não declara automaticamente que qualquer candidato é um substituto comercial aprovado.

### 5.2 FAIL do Caso A

`CASE_A = FAIL` se qualquer uma das condições ocorrer:

1. falha em qualquer critério obrigatório da Seção 5.1;
2. busca limitada a equivalência nominal, sem descoberta por características documentadas;
3. nenhuma consulta `TECHNICAL` retorna candidato incluído e rastreável;
4. candidato declarado comparável apesar de falhar hard constraint;
5. peso, propriedade ou especificação criado pelo modelo sem definição humana/evidência;
6. `Technical Match` misturado com `Evidence Confidence`, `Brazil Import Viability` ou `Commercial Fit`;
7. resultado incompatível com um controle humano sem evidência suficiente e adjudicação humana registrada;
8. ocorrência de qualquer erro crítico.

## 6. Avaliação do Caso B — commodity por especificação

### 6.1 PASS do Caso B

`CASE_B = PASS` somente se todos os critérios abaixo forem satisfeitos:

1. **Entrada correta:** produto Phosphoric Acid, CAS 7664-38-2, concentração 75% w/w mínimo, grau industrial/technical.
2. **Descoberta por especificação:** a estratégia procura produto, CAS, concentração e grau; não usa lógica de equivalente de marca.
3. **Demonstração ponta a ponta:** pelo menos um candidato cujo ground truth humano é `MANUFACTURER` é descoberto e submetido integralmente à verificação de empresa, extração e compliance. Isso não exige que o candidato receba `Specification Compliance = PASS`.
4. **Sem meta artificial e sem seleção:** nenhum número mínimo de fabricantes conformes é exigido; todos os candidatos incluídos após deduplicação são avaliados, e toda exclusão usa um motivo permitido e rastreável.
5. **Saída completa:** cada candidato avaliado contém Manufacturer, Country, Manufacturer Verification, Product, Concentration, Grade, Specifications, Documentation e Specification Compliance; `Country` é o país da planta produtora e fica `UNKNOWN` sem evidência dessa planta.
6. **Verificação empresarial:** classificação de fabricante, distribuidor ou trader segue os critérios da especificação e guarda evidência independente quando exigida.
7. **Compliance por propriedade:** identidade/CAS, concentração e grau recebem individualmente `PASS`, `FAIL` ou `UNKNOWN`; concentração segue a regra de 75% w/w mínimo; `technical` e `industrial` são sinônimos aceitos; `food` e `pharma` não reprovam e recebem o sinalizador `commercial_grade_equivalence = NOT_EQUIVALENT`.
8. **Regra agregada correta:** `Specification Compliance` é `PASS` somente se todas as propriedades obrigatórias forem `PASS`; é `FAIL` se ao menos uma for `FAIL`; e é `UNKNOWN` se não houver `FAIL` e existir ao menos um `UNKNOWN`.
9. **Ausência preservada:** especificação indisponível, ambígua ou sem evidência resulta em `UNKNOWN`, sem preenchimento pelo LLM.
10. **Sem Technical Match:** nenhum Technical Match tradicional ou equivalência de marca é calculado para o Caso B.
11. **Documentos classificados por proveniência:** documentação recebe `OFFICIAL`, `CORROBORATED`, `THIRD_PARTY` ou `UNVERIFIED` com justificativa rastreável.
12. **Evidência completa:** toda propriedade `EVIDENCED` possui valor e ao menos um item completo em `evidence[]`; toda propriedade `UNKNOWN` possui `value = UNKNOWN`; fontes consultadas sem suporte permanecem em `sources_consulted[]`.
13. **Métricas completas:** todos os contadores e taxas obrigatórios são apresentados e aritmeticamente consistentes.
14. **Gate crítico limpo:** nenhum erro crítico da Seção 4 ocorreu.

### 6.2 FAIL do Caso B

`CASE_B = FAIL` se qualquer uma das condições ocorrer:

1. falha em qualquer critério obrigatório da Seção 6.1;
2. uso de equivalência de marca ou `Technical Match` tradicional;
3. nenhum candidato com ground truth humano `MANUFACTURER` descoberto e avaliado ponta a ponta;
4. propriedade obrigatória ausente tratada como `PASS` ou fato;
5. `Specification Compliance = PASS` quando existe propriedade obrigatória `FAIL` ou `UNKNOWN`;
6. exigência de quantidade arbitrária de fabricantes conformes;
7. fabricante, país da planta, concentração, grau ou especificação preenchidos sem evidência;
8. candidato excluído sem motivo permitido e rastreável;
9. ocorrência de qualquer erro crítico.

## 7. Verificação objetiva das métricas

Para cada caso, verificar:

1. `queries_generated` corresponde ao número de consultas registradas por `query_id`.
2. `search_results_found` corresponde à soma dos resultados brutos retornados.
3. `unique_urls` corresponde às URLs distintas após a normalização definida na especificação.
4. Cada fetch possui exatamente um estado terminal conforme a precedência `success`, `blocked`, `form_required`, `js_required`, `timeout`, e a soma dos estados é igual a `fetch_attempted`.
5. `pdf_downloaded <= pdf_candidates`.
6. `pdf_parseable` e `pdf_scanned` são mutuamente exclusivos, e `pdf_parseable + pdf_scanned <= pdf_downloaded`; falhas permanecem registradas sem incrementar esses dois contadores.
7. `extraction_success <= extraction_attempted`.
8. Cada `extraction_attempted` representa um par candidato-fonte e cada sucesso contém ao menos uma propriedade `EVIDENCED`.
9. `candidate_products` corresponde às combinações distintas empresa-produto incluídas após deduplicação.
10. `verified_candidates` contém somente candidatos com empresa `VERIFIED_MANUFACTURER` e produto sustentado por documento `OFFICIAL` ou `CORROBORATED`.
11. `verified_candidates <= candidate_products`.
12. As taxas obedecem às fórmulas da especificação; denominador zero produz `UNKNOWN`.

As taxas são diagnósticas. Enquanto limiares humanos não forem definidos, elas não podem ser convertidas automaticamente em `PASS` ou `FAIL`.

## 8. Controles humanos congelados

### 8.1 Caso A — positivos

| Controle | `must_be_discovered` | Ground truth humano | Classificação esperada do sistema |
|---|---|---|---|
| Tronox | `YES` | `MANUFACTURER` | `TBD_HUMAN` |
| KRONOS | `YES` | `MANUFACTURER` | `TBD_HUMAN` |
| LB Group | `YES` | `MANUFACTURER` | `TBD_HUMAN` |

### 8.2 Caso A — negativo

| Empresa | Produto/documento | `must_be_evaluated` | Expected |
|---|---|---|---|
| Qingdao Lidayouxuan | R6618 | `YES` | Não classificar como `VERIFIED_MANUFACTURER` sem evidência independente suficiente. Não classificar o documento automaticamente como `OFFICIAL`. |

### 8.3 Distribuidor conhecido

`TBD_HUMAN`

Somente humanos podem preencher esse controle. O Codex não pode sugerir, escolher ou inserir o valor no gabarito.

### 8.4 Caso B

O ground truth de fabricantes e resultados de compliance deve ser fornecido por humanos antes da rodada avaliada. O protocolo não presume quantos fabricantes atendem à especificação.

## 9. Decisão final

Registrar separadamente:

```text
CASE_A: PASS | FAIL
CASE_A_REASON: <critérios e evidências>

CASE_B: PASS | FAIL
CASE_B_REASON: <critérios e evidências>

POC: PASS | FAIL
```

Regra final:

| Caso A | Caso B | POC |
|---|---|---|
| PASS | PASS | PASS |
| PASS | FAIL | FAIL |
| FAIL | PASS | FAIL |
| FAIL | FAIL | FAIL |

Nenhuma média, score agregado ou desempenho de apenas um caso pode substituir essa regra.

## Fase 0 — Veredito da classificação por regra fixa: FAIL

**Data do veredito:** 2026-08-24
**Commits de referência:** `4106bd1` (amostra 1) e `3c6936c` (conjunto 2 de validação).

O conjunto 2 é um conjunto de validação humana e não foi usado para escrever as regras. Os números medidos exclusivamente nesse conjunto foram:

| Escopo | Papel | Precisão | Revocação |
|---|---|---:|---:|
| Caso A | `MANUFACTURER` | 0/1 — 0,00% | 0/1 — 0,00% |
| Caso A | `DISTRIBUTOR` | 1/1 — 100,00% | 1/3 — 33,33% |
| Caso A | `TRADER` | 8/15 — 53,33% | 8/11 — 72,73% |
| Caso B | `MANUFACTURER` | 0/1 — 0,00% | 0/1 — 0,00% |
| Caso B | `DISTRIBUTOR` | 1/1 — 100,00% | 1/4 — 25,00% |
| Caso B | `TRADER` | 4/9 — 44,44% | 4/5 — 80,00% |
| Combinado | `MANUFACTURER` | 0/2 — 0,00% | 0/2 — 0,00% |
| Combinado | `DISTRIBUTOR` | 2/2 — 100,00% | 2/7 — 28,57% |
| Combinado | `TRADER` | 12/24 — 50,00% | 12/16 — 75,00% |

**Motivo do FAIL:** sinais como “catálogo amplo” e “venda de marca de terceiro” não separam fabricante de revendedor asiático que se autodeclara fabricante, e rebaixaram fabricantes reais como ICL Group, hxtio2 e mytio2. As regras de tipo de página também não distinguem de forma confiável site de empresa de portal de dados, notícia ou associação.

**Decisão:** substituir o classificador por `LLMCompanyClassifier`, atrás de uma abstração `CompanyClassifier`. A implementação por regra fixa será preservada apenas para comparação.

### Entrada avaliada do LLMCompanyClassifier

O `extracted_content` agregado por domínio recebe um orçamento determinístico de 40.000 caracteres antes da montagem do prompt e antes do cálculo da chave de cache. Cada página recebe inicialmente uma cota de `40.000 // número_de_páginas`; páginas abaixo da cota devolvem a sobra, que é redistribuída em passes sucessivos entre as páginas ainda acima da cota. Cada bloco cortado termina com `[TRUNCATED]`. O limite, a política de redistribuição e o resultado truncado fazem parte da entrada avaliada e da chave de cache; conteúdo omitido não pode sustentar a classificação ou sua citação.

Os modelos da linha Gemini 2.5 foram descontinuados para projetos novos, embora ainda apareçam no `ListModels`. O `gemini-3.1-pro-preview` exige faturamento ativo neste projeto; o `gemini-3.6-flash` em `v1beta` é a linha de base gratuita da Fase 0.

### Política de cobertura da extração

Os gates de marketplace/diretório e de domínio de ruído não bloqueiam a extração. Eles são preservados respectivamente como `marketplace_signal` e `noise_signal`, com o motivo da correspondência, e disponibilizados ao classificador como sinais não determinísticos. `MARKETPLACE_OR_DIRECTORY` e `NOT_A_COMPANY` são classes do gabarito humano; descartar esses resultados antes da classificação tornaria impossível medir essas classes.

As URLs de busca são deduplicadas antes da extração, preservando a ordem da primeira ocorrência. O teto por caso é `MAX_EXTRACTIONS_PER_CASE = 200`. A etapa inteira compartilha um guard rígido de 80 créditos de extração, além do teto mensal acumulado; qualquer projeção acima do teto aborta antes da chamada de rede.
