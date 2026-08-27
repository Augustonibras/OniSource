# OniSource — Design System

## Princípios
- Profissional, corporativo, formal, limpo.
- Sem emojis em nenhum lugar da interface — usar ícones SVG da biblioteca Lucide.
- Sem linguagem informal ("Opa!", "Legal!", "Uhu!"). Tom neutro e direto.
- Sem bordas arredondadas excessivas — máximo rounded-lg. Cards com rounded-xl no máximo.
- Sem sombras exageradas — usar shadow-sm ou shadow.
- Sem gradientes no conteúdo — gradiente apenas no símbolo da marca (SVG).
- Espaçamento generoso mas não exagerado.

## Paleta
- Primário: brand-blue-800 (#16327F) — botões, títulos, links
- Hover: brand-blue-700 (#2B4FAE)
- Fundo da página: #F8F9FC (cinza quase branco com tom azul)
- Cards: branco (#FFFFFF) com borda #E5E7EB
- Texto principal: #1F2937 (gray-800)
- Texto secundário: #6B7280 (gray-500)
- Sucesso/Fabricante: #059669 (emerald-600)
- Alerta/Trader: #D97706 (amber-600)
- Info/Distribuidor: #2563EB (blue-600)
- Erro: #DC2626 (red-600)

## Tipografia
- Font-family: Inter (importar do Google Fonts). Fallback: system-ui, sans-serif.
- Títulos: font-semibold, não bold. Nunca uppercase em títulos longos.
- Labels e badges: text-xs uppercase tracking-wider.

## Ícones
- Biblioteca: Lucide React (já disponível ou instalar `lucide-react`).
- Tamanho padrão: 16px (w-4 h-4) inline, 20px (w-5 h-5) em botões.
- Cor: herdar do texto (currentColor).
