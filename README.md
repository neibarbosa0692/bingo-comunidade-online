# Bingo Comunidade V11 — Híbrido Online + Offline

Esta versão mantém o **computador local como base principal do sorteio** e adiciona um **servidor online sincronizado** para que vendedores possam dar baixa nas cartelas de qualquer lugar.

## Início local

Execute `INICIAR_BINGO.bat`.

O sistema escolhe uma porta livre automaticamente e abre o navegador. A operação local continua funcionando sem internet.

## Recursos híbridos

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

Se você já usa uma versão anterior, feche os dois sistemas e copie o arquivo `bingo.db` da pasta antiga para esta pasta **antes de iniciar a V11**. A V11 fará as migrações necessárias automaticamente.

Faça uma cópia de segurança do `bingo.db` antes da migração.

## Parte online

Leia `DEPLOY_ONLINE.md`. Para que vendedores acessem de qualquer lugar, a parte online precisa ser hospedada em um servidor com endereço público e armazenamento persistente.
Atualização para deploy Docker.
