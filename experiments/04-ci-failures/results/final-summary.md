# Experimento 04 (V5): resultado final

Análise principal: **8 casos** × 3 repetições × 2 versões = 48 tentativas (fora dela, contados à parte: OpenByteInc/QuantDinger, boyter/scc, nkanaev/yarr; emendas 24 e 27).

| Desfecho | v1 | v2 |
|---|---|---|
| equivalente | 10 | 11 |
| valida | 1 | 0 |
| pior | 3 | 3 |
| inconclusiva | 1 | 1 |
| ainda vermelho | 7 | 6 |
| desistiu | 2 | 3 |
| parou por orçamento | 0 | 0 |
| **total** | 24 | 24 |

- Patches verdes (suíte original 3/3, aprovados pelo validador): v1 15, v2 15.
- Correções (equivalente + válida): v1 11 de 24, v2 11 de 24.
- Verdes que não são correção (pior + inconclusiva): v1 4 de 15, v2 4 de 15.
- 'Pior' por tipo: v1 {'falhou nos testes ocultos': 3}; v2 {'falhou nos testes ocultos': 1, 'passou em tudo, julgado pior': 2}.
- Custo de API (todas as 33 tentativas por versão): v1 US$ 2.435, v2 US$ 2.559; só os casos da análise principal: v1 US$ 1.618, v2 US$ 1.692.
- US$ por correção (análise principal, tentativas falhas incluídas): v1 0.147, v2 0.154.
- Origem dos vereditos dos pacotes da análise principal: {'rule': 4, 'human': 5, 'codex_delegated': 21}.

## Por caso (r1 / r2 / r3)

| Caso | v1 | v2 |
|---|---|---|
| alicebob/miniredis | ainda vermelho / ainda vermelho / ainda vermelho | ainda vermelho / ainda vermelho / ainda vermelho |
| gobwas/ws | pior / pior / pior | pior / pior / pior |
| ludwig-ai/ludwig | valida / equivalente / equivalente | equivalente / equivalente / equivalente |
| mark3labs/mcp-go | ainda vermelho / ainda vermelho / ainda vermelho | ainda vermelho / ainda vermelho / ainda vermelho |
| pyinfra-dev/pyinfra | equivalente / equivalente / inconclusiva | equivalente / inconclusiva / equivalente |
| rmax/scrapy-redis | desistiu / desistiu / ainda vermelho | desistiu / desistiu / desistiu |
| sigstore/cosign | equivalente / equivalente / equivalente | equivalente / equivalente / equivalente |
| tdewolff/minify | equivalente / equivalente / equivalente | equivalente / equivalente / equivalente |

## Fora da análise principal (o mantenedor consertou o teste, não o código)

| Caso | v1 (desfecho do executor) | v2 |
|---|---|---|
| OpenByteInc/QuantDinger | {'green_fails_hidden': 3} | {'green_fails_hidden': 3} |
| boyter/scc | {'budget_exhausted': 3} | {'budget_exhausted': 2, 'green_fails_hidden': 1} |
| nkanaev/yarr | {'green_no_hidden_tests': 3} | {'green_no_hidden_tests': 3} |
