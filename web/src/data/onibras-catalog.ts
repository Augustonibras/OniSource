export interface OnibrasProduct {
  name: string;
  market: 'sugar_ethanol' | 'water_treatment' | 'industrial' | 'paints_coatings';
  marketLabel: string;
  description: string;
  application: string;
}

export const ONIBRAS_CATALOG: OnibrasProduct[] = [
  // Sugar & Ethanol
  { name: 'Sugarpol', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Reagente clarificante analítico para análise de POL, livre de chumbo, homologado CONSECANA-SP', application: 'Laboratório de usinas — análise polarimétrica de açúcar' },
  { name: 'OniBiotico', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Antibacteriano USP que elimina bactérias sem prejudicar leveduras na fermentação', application: 'Fermentação alcoólica' },
  { name: 'OniCida', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Bactericida industrial potente para processos de açúcar e etanol, aprovado para uso alimentício', application: 'Higiene de processo' },
  { name: 'OniClar', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Clarificante catiônico que remove impurezas formadoras de cor do caldo e xarope, sem resíduo', application: 'Clarificação de caldo' },
  { name: 'OniDisper', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Dispersante e antiespumante dual de grau alimentício', application: 'Controle de espuma em processos' },
  { name: 'OniFloc A', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Floculante aniônico de alto peso molecular para clarificação rápida e limpa do caldo', application: 'Floculação e decantação' },
  { name: 'OniLub', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Lubrificante biodegradável para massa cozida que reduz viscosidade e acelera cristalização', application: 'Cristalização — cozimento a vácuo' },
  { name: 'OniIncrust', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Sequestrante de cálcio, magnésio e ferro em evaporadores', application: 'Evaporação — anti-incrustante' },
  { name: 'OniSpuma', market: 'sugar_ethanol', marketLabel: 'Açúcar & Etanol', description: 'Antiespumante biodegradável para fermentação, estável mesmo após armazenamento prolongado', application: 'Controle de espuma na fermentação' },

  // Water Treatment
  { name: 'OniFloc A (Água)', market: 'water_treatment', marketLabel: 'Tratamento de Água', description: 'Polímero aniônico que agrega partículas suspensas para remoção em água potável e efluentes', application: 'Floculação em ETA e ETE' },
  { name: 'OniFloc C', market: 'water_treatment', marketLabel: 'Tratamento de Água', description: 'Polímero catiônico para coagulação, decantação e desidratação de lodo', application: 'Coagulação e tratamento de lodo' },
  { name: 'OniFloc CA', market: 'water_treatment', marketLabel: 'Tratamento de Água', description: 'Clarificante para ampla faixa de pH e temperatura, sem resíduo após tratamento', application: 'Clarificação de água e efluentes' },

  // Industrial Care
  { name: 'OniLimp LS', market: 'industrial', marketLabel: 'Industrial', description: 'Limpador ácido não corrosivo para tubulações, tanques, evaporadores e trocadores de calor', application: 'Limpeza industrial — superfícies metálicas' },
  { name: 'OniLimp RD', market: 'industrial', marketLabel: 'Industrial', description: 'Limpador ácido superconcentrado para aço e inox que reduz tempo de esfregação', application: 'Limpeza de metais e inox' },
  { name: 'OniGrax DM', market: 'industrial', marketLabel: 'Industrial', description: 'Desengraxante biodegradável de alto poder de penetração', application: 'Desengraxe industrial' },
  { name: 'OniGrax BA', market: 'industrial', marketLabel: 'Industrial', description: 'Desengraxante base água, sem vapores tóxicos, concentrado e econômico', application: 'Desengraxe sem solvente' },
  { name: 'OniFer', market: 'industrial', marketLabel: 'Industrial', description: 'Desengraxe, desoxidação e fosfatização 3-em-1 para preparação de superfícies metálicas', application: 'Tratamento de superfície pré-pintura/galvanização' },

  // Paints & Coatings
  { name: 'OniDisper 607T', market: 'paints_coatings', marketLabel: 'Tintas & Revestimentos', description: 'Reduz tempo e energia na dispersão de pigmentos, permitindo maior carga de pigmento', application: 'Dispersão de pigmentos' },
  { name: 'OniBact 295T', market: 'paints_coatings', marketLabel: 'Tintas & Revestimentos', description: 'Bactericida potente que também controla protozoários, algas e fungos em tintas', application: 'Preservação in-can' },
  { name: 'OniSpuma 509T', market: 'paints_coatings', marketLabel: 'Tintas & Revestimentos', description: 'Quebra microespuma em sistemas de látex acrílico', application: 'Controle de espuma em tintas' },
  { name: 'OniCida 290T', market: 'paints_coatings', marketLabel: 'Tintas & Revestimentos', description: 'Fungicida/bactericida sem formaldeído, eficaz em baixas concentrações', application: 'Preservação de tintas' },
  { name: 'OniCor', market: 'paints_coatings', marketLabel: 'Tintas & Revestimentos', description: 'Corretor de pH sem metais que protege contra corrosão e descoloração', application: 'Correção de pH em tintas' },
  { name: 'OniEsp T/M', market: 'paints_coatings', marketLabel: 'Tintas & Revestimentos', description: 'Espessante acrílico substituto de celulose, mantém pigmentos suspensos e evita escorrimento', application: 'Reologia de tintas' },
  { name: 'OniCryl', market: 'paints_coatings', marketLabel: 'Tintas & Revestimentos', description: 'Resina acrílica para aderência, resistência ao intemperismo e à abrasão em acabamentos', application: 'Resina para tintas de alta qualidade' },
  { name: 'OniPar', market: 'paints_coatings', marketLabel: 'Tintas & Revestimentos', description: 'Emulsão de parafina para acabamento aveludado e resistente a manchas de água', application: 'Massas e revestimentos decorativos' },
];

export const BRAZILIAN_REGIONS = [
  { value: 'sudeste', label: 'Sudeste (SP, MG, RJ, ES)' },
  { value: 'sul', label: 'Sul (PR, SC, RS)' },
  { value: 'centro-oeste', label: 'Centro-Oeste (GO, MT, MS, DF)' },
  { value: 'nordeste', label: 'Nordeste (BA, PE, AL, SE, CE, MA, PI, PB, RN)' },
  { value: 'norte', label: 'Norte (PA, AM, TO, RO, AC, AP, RR)' },
];

export const CONTINENTS = [
  { value: 'south_america', label: 'América do Sul' },
  { value: 'central_america', label: 'América Central & Caribe' },
  { value: 'north_america', label: 'América do Norte' },
  { value: 'africa', label: 'África' },
  { value: 'europe', label: 'Europa' },
  { value: 'asia', label: 'Ásia' },
];
