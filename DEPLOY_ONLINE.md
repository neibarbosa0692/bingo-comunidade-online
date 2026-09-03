# Bingo Comunidade V11 — servidor online

A V11 usa **duas instâncias do mesmo sistema**:

1. **Computador local**: é a base principal do sorteio e continua funcionando sem internet.
2. **Servidor online**: recebe as baixas dos vendedores pela internet e sincroniza com o computador local.

## Variáveis obrigatórias no servidor online

- `BINGO_MODE=cloud`
- `BINGO_SYNC_TOKEN=<uma chave secreta longa>`
- `BINGO_SECRET_KEY=<outra chave secreta longa para manter as sessões dos vendedores>`
- `BINGO_DB_PATH=<caminho de armazenamento persistente>/bingo_cloud.db`
- `PORT` é normalmente informado automaticamente pelo provedor de hospedagem.

Use `GERAR_CHAVE_SYNC.bat` no computador para gerar a chave. A mesma chave deve ser configurada no servidor online e no menu **Online / Offline** da instalação local.

## Comando de inicialização

Instale `requirements_cloud.txt` e inicie com:

```text
gunicorn -w 1 --threads 4 -b 0.0.0.0:$PORT cloud_entry:app
```

O uso de **um único worker** é intencional quando o banco online for SQLite.

## Armazenamento persistente é obrigatório

O banco online não pode ficar em um diretório temporário. Configure um disco/volume persistente no serviço de hospedagem e aponte `BINGO_DB_PATH` para esse volume. Sem isso, o servidor pode perder as vendas ao reiniciar.

## Primeira sincronização

Depois que o endereço online estiver funcionando:

1. Abra a V11 no computador do bingo.
2. Entre em **Online / Offline**.
3. Informe a URL pública, por exemplo `https://bingo.exemplo.com`.
4. Cole a mesma chave de sincronização.
5. Marque **Habilitar sincronização automática**.
6. Clique em **Sincronizar agora**.
7. Abra **Celulares** para obter o QR e o código individual de cada vendedor.

## Regra de segurança contra venda duplicada

Cada cartela distribuída a um vendedor fica sob responsabilidade exclusiva dele. O balcão local não pode dar baixa em uma cartela que ainda esteja atribuída a um vendedor externo. Assim, se a internet do local cair enquanto o vendedor continua online em outro lugar, os dois lados não vendem a mesma cartela.

## Antes do sorteio

Use **Online / Offline → Encerrar vendas / Preparar sorteio**. O sistema:

- tenta puxar todas as vendas online;
- envia alterações locais pendentes;
- cria um backup local automático;
- fecha as vendas na base local e na base online;
- mantém sorteio, telão e conferência disponíveis offline.

Se a internet já tiver caído, existe uma opção explícita de contingência para fechar com a última cópia local. Use somente quando for impossível restabelecer a conexão.
