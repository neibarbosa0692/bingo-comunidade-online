# Bingo Comunidade V11.2 — Híbrido + Lotes Automáticos

Esta versão mantém o **computador local como base principal do sorteio** e adiciona um **servidor online sincronizado** para que vendedores possam dar baixa nas cartelas de qualquer lugar.

## Início local

Execute `INICIAR_BINGO.bat`.

O sistema escolhe uma porta livre automaticamente e abre o navegador. A operação local continua funcionando sem internet.

## Recursos híbridos

- lotes automáticos de 10 cartelas já no momento da geração;
- distribuição manual posterior dos lotes aos vendedores;
- numeração das cartelas exibida sem o símbolo #;

- banco SQLite local para sorteio, telão, conferência e relatórios;
- servidor online separado para vendas remotas;
- sincronização automática e manual;
- indicador de última sincronização;
- lotes exclusivos por vendedor para evitar venda duplicada;
- código e QR privado por vendedor;
- fechamento de vendas antes do sorteio;
- backup automático no fechamento;
- modo de contingência quando a internet já caiu;
- template PNG oficial da cartela preservado.

## Migrar seu banco atual

Se você já usa uma versão anterior, feche os dois sistemas e copie o arquivo `bingo.db` da pasta antiga para esta pasta **antes de iniciar a V11**. A V11.2 fará as migrações necessárias automaticamente.

Faça uma cópia de segurança do `bingo.db` antes da migração.

## Parte online

Leia `DEPLOY_ONLINE.md`. Para que vendedores acessem de qualquer lugar, a parte online precisa ser hospedada em um servidor com endereço público e armazenamento persistente.


## V11.3 — Zerar dados de teste da nuvem

Na tela **Online + Offline**, o Administrador agora possui a ação **Zerar dados de teste da nuvem**.

- exige a confirmação textual `ZERAR NUVEM`;
- limpa somente o servidor online: cartelas, lotes, vendas/estornos, sorteios, ganhadores e filas de sincronização;
- preserva evento, vendedores, QR/códigos de acesso e configurações;
- cria backup automático do banco cloud em `/data/backups_cloud` antes da exclusão;
- reinicia o cursor local para evitar conflitos com eventos antigos da nuvem.

A ação não apaga as cartelas do computador local. Se existirem cartelas locais, uma sincronização completa futura poderá enviá-las novamente para a nuvem.
