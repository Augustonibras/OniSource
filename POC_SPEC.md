# OniSource — Especificação da POC (Fase 0)

## 1. Objetivo

Validar se o OniSource pode funcionar como um motor interno e confiável de inteligência de sourcing antes de qualquer investimento em interface, aplicação web, banco de dados ou infraestrutura.

A Fase 0 possui dois casos obrigatórios e estruturalmente diferentes:

- **Caso A — produto de marca:** descobrir e comparar produtos potencialmente comparáveis ou substitutos técnicos ao BILLIONS R996 Titanium Dioxide.
- **Caso B — commodity por especificação:** descobrir fabricantes de Phosphoric Acid, CAS 7664-38-2, concentração 75% w/w mínimo, grau industrial/technical, e verificar objetivamente a conformidade.

A POC só poderá receber `PASS` final se os dois casos receberem `PASS` separadamente.

## 2. Escopo e não objetivos

Esta fase é exclusivamente uma prova de conceito do motor de sourcing.

Não fazem parte da Fase 0:

- frontend ou aplicação web;
- banco de dados;
- Docker ou Redis;
- autenticação;
- SaaS, billing ou CRM;
- envio automático de e-mails;
- avaliação de viabilidade de importação para o Brasil;
- avaliação comercial;
- consulta automática de registro empresarial.

Na Fase 0:

- `Brazil Import Viability = NOT_EVALUATED`;
- `Commercial Fit = NOT_EVALUATED`.

## 3. Regras normativas

Os termos `DEVE`, `NÃO DEVE` e `PODE` são normativos.

1. Toda afirmação externa DEVE possuir evidência rastreável.
2. Informação ausente, inacessível, ambígua ou sem evidência DEVE resultar em `UNKNOWN`.
3. O sistema NÃO DEVE completar lacunas usando conhecimento ou inferência do LLM.
4. O sistema NÃO DEVE inventar especificações.
5. O sistema NÃO DEVE inferir que uma empresa é fabricante pelo nome do domínio, aparência do site ou qualidade visual de um documento.
6. Falso positivo de fabricante é mais grave do que falso negativo.
7. Cada valor extraído DEVE permanecer ligado à sua evidência de origem.
8. Conflitos entre fontes NÃO DEVEM ser resolvidos silenciosamente; os valores e fontes conflitantes devem ser preservados e a propriedade deve permanecer `UNKNOWN` até existir regra ou decisão humana aplicável.

### 3.1 Glossário normativo

| Termo | Definição |
|---|---|
| `fonte independente` | Fonte cujo controle editorial não pertence à empresa avaliada, às suas afiliadas, aos seus representantes, distribuidores ou traders; controle não verificável não conta como independente. |
| `evidência suficiente` | `TBD_HUMAN` |
| `evidência explícita` | Afirmação literal presente na fonte, sem inferência além do texto ou dado publicado. |
| `contradição relevante` | `TBD_HUMAN` |
| `informação ambígua` | Informação que admite duas ou mais interpretações incompatíveis e não possui regra aprovada para selecionar uma delas. |
| `domínio oficial verificado` | `TBD_HUMAN` |

### 3.2 Cobertura de resultados e candidatos

Cada resultado de busca deve receber `INCLUDED` ou `EXCLUDED`.

Exclusões permitidas:

- `DUPLICATE_URL`: URL canônica já registrada, com referência ao registro preservado;
- `DUPLICATE_ENTITY_PRODUCT`: mesma combinação empresa-produto, com todas as URLs mescladas no registro preservado;
- `OUT_OF_SCOPE_PRODUCT`: evidência explícita demonstra que o produto não pertence ao caso avaliado.

Fetch bloqueado, timeout, formulário, JavaScript obrigatório ou ausência de especificação não permitem exclusão; o candidato permanece incluído com as propriedades não comprovadas como `UNKNOWN`. Toda exclusão deve guardar `exclusion_reason` e, quando aplicável, a evidência correspondente.

## 4. Contrato mínimo de evidência

Cada propriedade deve separar o estado do valor, suas evidências e as fontes consultadas:

| Campo | Regra |
|---|---|
| `property_status` | `EVIDENCED` ou `UNKNOWN`. |
| `value` | Valor exatamente sustentado pela fonte quando `EVIDENCED`; `UNKNOWN` quando `property_status = UNKNOWN`. |
| `unit` | Unidade declarada pela fonte; `UNKNOWN` quando ausente e `NOT_APPLICABLE` quando não se aplica. |
| `evidence[]` | Lista de evidências que sustentam o valor. Deve conter ao menos um item quando `EVIDENCED` e pode ser vazia quando `UNKNOWN`. |
| `sources_consulted[]` | Lista das fontes efetivamente consultadas, inclusive as que não forneceram evidência para a propriedade. |

Cada item de `evidence[]` deve guardar:

| Campo | Regra |
|---|---|
| `source_url` | URL exata da página ou do documento consultado. |
| `source_type` | Tipo da fonte, por exemplo: página de produto, TDS, SDS, catálogo, registro empresarial ou fonte independente. |
| `document_name` | Título ou nome do documento; `UNKNOWN` quando a fonte não o declarar. |
| `page` | Página do documento quando aplicável; caso contrário, `NOT_APPLICABLE`. |
| `evidence_excerpt` | Trecho exato que sustenta o valor. |
| `retrieved_at` | Data e hora da coleta em formato ISO 8601 com fuso horário. |

Uma URL sem trecho comprobatório pode constar em `sources_consulted[]`, mas não em `evidence[]`. O status `UNKNOWN` não autoriza preencher um valor presumido.

## 5. Classificação de empresas

Valores permitidos:

- `VERIFIED_MANUFACTURER`
- `PROBABLE_MANUFACTURER`
- `VERIFIED_DISTRIBUTOR`
- `PROBABLE_DISTRIBUTOR`
- `TRADER`
- `UNKNOWN`

Cada empresa deve prever os seguintes campos:

- `official_domain`;
- `business_registration_status`;
- `business_registration_number`;
- `business_registration_source`;
- `independent_producer_evidence`;
- `independent_distributor_evidence`.

Na POC, os campos de registro empresarial podem permanecer `NOT_IMPLEMENTED`. Isso não pode ser convertido em confirmação positiva.

### 5.1 Limiares humanos

- `official_domain_verification_rule = TBD_HUMAN`
- `manufacturer_independent_evidence_threshold = TBD_HUMAN`
- `distributor_evidence_threshold = TBD_HUMAN`
- `contradiction_resolution_rule = TBD_HUMAN`

### 5.2 Árvore de decisão

Aplicar na ordem:

1. Evidência ausente, ambígua ou com contradição relevante não resolvida: `UNKNOWN`.
2. Evidência explícita de atuação somente como trader, revendedor ou intermediário, sem evidência explícita de fabricação: `TRADER`.
3. Evidência explícita de fabricação ou produção:
   - domínio oficial verificado, evidência primária e limiar independente de fabricante atendido: `VERIFIED_MANUFACTURER`;
   - caso contrário: `PROBABLE_MANUFACTURER`.
4. Evidência explícita de distribuição ou revenda, sem evidência explícita de fabricação:
   - limiar de distribuição atendido: `VERIFIED_DISTRIBUTOR`;
   - caso contrário: `PROBABLE_DISTRIBUTOR`.
5. Nenhuma condição anterior atendida: `UNKNOWN`.

Sem limiar humano definido, o nível verificado correspondente não pode ser atribuído. Similaridade entre domínio e nome empresarial não conta como evidência.

## 6. Classificação de documentos

Valores permitidos:

- `OFFICIAL`
- `CORROBORATED`
- `THIRD_PARTY`
- `UNVERIFIED`

### 6.1 Limiar humano

`document_corroboration_threshold = TBD_HUMAN`

### 6.2 Árvore de decisão e precedência

Aplicar na ordem e atribuir somente a primeira classificação atendida:

1. `OFFICIAL`: documento obtido em domínio oficial verificado do fabricante alegado, com identidade consistente e existência do produto confirmada por fonte primária do fabricante.
2. `CORROBORATED`: não atende `OFFICIAL`, mas suas alegações atingem o limiar humano de corroboração por fonte oficial ou independente identificada.
3. `THIRD_PARTY`: não atende as classes anteriores e está hospedado ou foi fornecido por distribuidor, trader, marketplace ou outro terceiro identificável.
4. `UNVERIFIED`: nenhuma condição anterior é atendida.

Papel timbrado, logotipo, diagramação profissional ou nome de arquivo não são critérios de oficialidade. O domínio de hospedagem deve ser preservado mesmo quando um documento third-party recebe `CORROBORATED`.

## 7. Provedor de busca

A arquitetura futura deve depender da abstração `SearchProvider`.

O primeiro provedor previsto é Tavily Search API, mas ele deve ser substituível sem alterar a lógica principal de descoberta, extração, classificação ou avaliação do OniSource.

Tavily não será implementado nesta etapa de definição.

## 8. Caso A — produto de marca

### 8.1 Referência

- Produto: `BILLIONS R996 Titanium Dioxide`
- Objetivo: descobrir produtos potencialmente comparáveis ou substitutos técnicos.

### 8.2 Estratégia de descoberta obrigatória

A busca deve registrar e executar duas famílias distintas de consulta:

1. consultas por referência nominal, que podem conter R996, equivalente ou alternativa;
2. consultas por características técnicas documentadas do produto de referência, sem depender de expressões como “equivalent to R996” ou “alternative to R996”.

As características usadas nas consultas devem vir de evidência do produto de referência ou de entrada humana. Características presumidas pelo modelo são proibidas.

Rastreabilidade obrigatória:

- cada consulta guarda `query_id` e `query_family = NOMINAL | TECHNICAL`;
- cada consulta `TECHNICAL` guarda os identificadores das evidências das características utilizadas;
- cada resultado de busca guarda o `query_id` que o retornou;
- cada candidato guarda `discovered_by_query_ids`;
- a capacidade de descoberta técnica só é demonstrada quando ao menos um candidato incluído foi retornado por uma consulta `TECHNICAL`.

### 8.3 Saída mínima por candidato

- `candidate_product`;
- `discovered_by_query_ids`;
- `manufacturer`;
- `manufacturer_verification`;
- `product_page`;
- `TDS`;
- `specifications`;
- `applications`;
- `source_urls`;
- evidência por propriedade conforme a Seção 4;
- `hard_constraints`;
- `Technical Match`;
- `Evidence Confidence`;
- `Brazil Import Viability = NOT_EVALUATED`;
- `Commercial Fit = NOT_EVALUATED`.

### 8.4 Comparação técnica

`Technical Match` e `Evidence Confidence` são dimensões independentes e não podem ser somadas ou substituídas uma pela outra.

- `hard_constraints` são eliminatórios e devem ser definidos por humanos.
- `weighted_properties` somente podem usar pesos fornecidos pelo usuário e pela equipe técnica.
- Peso não definido deve ser armazenado como `TBD`.
- Enquanto hard constraints, propriedades ponderadas, pesos ou limiares necessários estiverem `TBD`, nenhum candidato pode ser declarado substituto aprovado e o cálculo correspondente deve permanecer `TBD`.
- Uma propriedade sem evidência recebe `UNKNOWN`; ela não recebe valor neutro, médio ou presumido.
- A fórmula e os limiares de `Evidence Confidence` devem ser documentados e aprovados por humanos antes da execução do benchmark; até lá, permanecem `TBD_HUMAN`.
- `TBD` e `TBD_HUMAN` representam decisão humana ausente; `UNKNOWN` representa evidência externa ausente ou insuficiente.

## 9. Caso B — commodity por especificação

### 9.1 Referência

- Produto: `Phosphoric Acid`
- CAS: `7664-38-2`
- Concentração: `75% w/w mínimo`
- Grau: `industrial/technical`

O Caso B não possui conceito de equivalente de marca e não usa `Technical Match` tradicional.

### 9.2 Saída mínima por candidato

- `Manufacturer`;
- `Country`;
- `Manufacturer Verification`;
- `Product`;
- `Concentration`;
- `Grade`;
- `Specifications`;
- `Documentation`;
- `Specification Compliance`.

`Country` significa o país da planta produtora. País da sede, do escritório comercial ou do domínio não pode substituí-lo. Sem evidência da planta produtora, `Country = UNKNOWN`.

### 9.3 Propriedades obrigatórias e regra de compliance

Cada propriedade obrigatória deve receber `PASS`, `FAIL` ou `UNKNOWN`, sempre com evidência quando o resultado não for `UNKNOWN`.

| Propriedade | `PASS` | `FAIL` | `UNKNOWN` |
|---|---|---|---|
| Identidade/CAS | A fonte identifica Phosphoric Acid e o CAS 7664-38-2. | A fonte identifica produto ou CAS diferente/incompatível. | CAS ou identidade não estão disponíveis, são ambíguos ou não têm evidência. |
| Concentração | A fonte declara `% w/w` e ao menos uma condição: mínimo `>= 75,0%`; faixa que contém `75,0%`; ou valor típico/nominal `>= 75,0%`. | A fonte declara valor aplicável abaixo de `75,0% w/w` e nenhuma condição de `PASS` é atendida. | Valor, unidade, base ou tipo do valor estão ausentes ou ambíguos. |
| Grau | `technical` e `industrial` recebem `PASS`. `food` e `pharma` também não reprovam e recebem `PASS` com `commercial_grade_equivalence = NOT_EQUIVALENT`. | Outro grau recebe `FAIL` somente quando uma regra humana aprovada o define como incompatível. | Grau ausente, ambíguo ou sem regra humana aplicável. |

`Specification Compliance` deve ser calculado sem score ponderado:

- `PASS`: todas as propriedades obrigatórias são `PASS`;
- `FAIL`: pelo menos uma propriedade obrigatória é `FAIL`;
- `UNKNOWN`: nenhuma propriedade é `FAIL` e pelo menos uma é `UNKNOWN`.

Não existe quantidade mínima predeterminada de fabricantes que precise receber `PASS`. O objetivo é classificar corretamente cada candidato encontrado.

O sinalizador `commercial_grade_equivalence` não altera `Commercial Fit = NOT_EVALUATED`.

Para demonstrar descoberta de fabricantes, ao menos um candidato cujo ground truth humano seja `MANUFACTURER` deve ser descoberto e avaliado ponta a ponta. Isso não exige que qualquer fabricante receba `Specification Compliance = PASS`.

## 10. Métricas obrigatórias

Cada execução deve registrar:

- `queries_generated`;
- `search_results_found`;
- `unique_urls`;
- `fetch_attempted`;
- `fetch_success`;
- `fetch_blocked`;
- `fetch_timeout`;
- `fetch_form_required`;
- `fetch_js_required`;
- `pdf_candidates`;
- `pdf_downloaded`;
- `pdf_parseable`;
- `pdf_scanned`;
- `extraction_attempted`;
- `extraction_success`;
- `candidate_products`;
- `verified_candidates`.

### 10.1 Unidade de contagem

| Métrica | Definição |
|---|---|
| `queries_generated` | Quantidade de registros de consulta criados, identificados por `query_id`. |
| `search_results_found` | Quantidade total de itens brutos retornados pelo provider, incluindo duplicatas. |
| `unique_urls` | Quantidade de URLs canônicas distintas após converter scheme e host para minúsculas, remover fragmento e porta padrão e normalizar barra final. |
| `fetch_attempted` | Quantidade de tentativas efetivamente iniciadas de recuperar uma URL canônica; cada retry conta como nova tentativa. |
| `fetch_success` | Tentativas que obtêm conteúdo não vazio e utilizável para extração. |
| `fetch_blocked` | Tentativas encerradas por negação explícita de acesso, como bloqueio HTTP ou CAPTCHA. |
| `fetch_timeout` | Tentativas sem resposta utilizável dentro do timeout configurado e sem outro estado terminal observável. |
| `fetch_form_required` | Tentativas encerradas porque o conteúdo exige submissão obrigatória de formulário. |
| `fetch_js_required` | Tentativas encerradas porque somente um shell sem conteúdo utilizável foi obtido e a página exige execução de JavaScript. |
| `pdf_candidates` | Quantidade de URLs canônicas distintas identificadas como possível PDF por URL, content type ou resultado de busca. |
| `pdf_downloaded` | PDFs candidatos cujos bytes foram obtidos e possuem assinatura válida de PDF. |
| `pdf_parseable` | PDFs baixados com texto utilizável extraível sem OCR. |
| `pdf_scanned` | PDFs baixados sem texto utilizável e identificados como conteúdo baseado em imagem que exige OCR. |
| `extraction_attempted` | Quantidade de pares candidato-fonte submetidos à extração. |
| `extraction_success` | Extrações que produzem registro estruturalmente válido com ao menos uma propriedade `EVIDENCED`. |
| `candidate_products` | Quantidade de combinações distintas empresa-produto incluídas após deduplicação. |
| `verified_candidates` | Candidatos cuja empresa é `VERIFIED_MANUFACTURER` e cuja existência do produto é sustentada por documento `OFFICIAL` ou `CORROBORATED`. |

### 10.2 Estados terminais de fetch

Cada tentativa recebe exatamente um estado. Se mais de uma condição for observada, aplicar a precedência:

1. `success`;
2. `blocked`;
3. `form_required`;
4. `js_required`;
5. `timeout`.

Assim:

`fetch_attempted = fetch_success + fetch_blocked + fetch_timeout + fetch_form_required + fetch_js_required`

`pdf_parseable` e `pdf_scanned` são mutuamente exclusivos. PDF corrompido ou sem classificação válida não incrementa nenhum dos dois contadores e sua falha permanece registrada. Portanto:

`pdf_parseable + pdf_scanned <= pdf_downloaded`

Taxas:

- `fetch_success_rate = fetch_success / fetch_attempted`;
- `extraction_success_rate = extraction_success / extraction_attempted`;
- `end_to_end_success_rate = verified_candidates / candidate_products`.

Se o denominador for zero, a taxa deve ser `UNKNOWN`, nunca zero presumido. As taxas devem ser reportadas separadamente por caso e no consolidado. Nenhum limiar numérico de aprovação é definido automaticamente; eventual limiar deve ser `TBD_HUMAN` até aprovação humana.

## 11. Erros críticos

São erros críticos:

1. trader classificado como `VERIFIED_MANUFACTURER`;
2. documento third-party classificado como `OFFICIAL`;
3. especificação sem evidência apresentada como fato;
4. especificação inventada pelo modelo.

Qualquer erro crítico causa `FAIL` no caso em que ocorrer e impede `PASS` final da POC.

## 12. Benchmark e controles humanos

O ground truth pertence exclusivamente a humanos. O Codex e o sistema não podem criar, completar ou alterar o gabarito para melhorar resultados.

### 12.1 Controles positivos conhecidos do Caso A

| Controle | `must_be_discovered` | Ground truth humano | Classificação esperada do sistema |
|---|---|---|---|
| Tronox | `YES` | `MANUFACTURER` | `TBD_HUMAN` |
| KRONOS | `YES` | `MANUFACTURER` | `TBD_HUMAN` |
| LB Group | `YES` | `MANUFACTURER` | `TBD_HUMAN` |

### 12.2 Controle negativo conhecido do Caso A

| Empresa | Produto/documento | `must_be_evaluated` | Expectativa humana registrada |
|---|---|---|---|
| Qingdao Lidayouxuan | R6618 | `YES` | Não pode receber `VERIFIED_MANUFACTURER` sem evidência independente suficiente. O documento R6618 não pode ser classificado automaticamente como `OFFICIAL`. |

### 12.3 Distribuidor conhecido

`TBD_HUMAN`

O Codex não pode escolher ou preencher esse controle.

### 12.4 Itens que permanecem sob controle humano

- ground truth completo dos Casos A e B;
- classificação esperada do sistema para os controles positivos do Caso A;
- regra de verificação de domínio oficial;
- limiares de evidência independente de fabricante e distribuidor;
- regra de resolução de contradições relevantes;
- limiar de corroboração documental;
- hard constraints do Caso A;
- weighted properties e respectivos pesos;
- limiares de aprovação de scores e métricas;
- fórmula e limiares de `Evidence Confidence`;
- distribuidor conhecido do benchmark;
- adjudicação de evidência ambígua ou conflitante.
