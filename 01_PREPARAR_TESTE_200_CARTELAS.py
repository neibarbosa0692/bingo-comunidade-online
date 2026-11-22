#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prepara um evento de teste completo com 200 cartelas.

Standalone: usa apenas a biblioteca padrão do Python e o mesmo banco SQLite do
Bingo Comunidade. Execute na pasta do sistema, preferencialmente com o Bingo fechado.
"""

from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import os
import random
import secrets
import sqlite3
import urllib.request
import urllib.error

EVENTO_TESTE = "TESTE AUTOMATIZADO - 200 CARTELAS"
QTD_CARTELAS = 200
QTD_VENDEDORES = 10
CARTELAS_POR_LOTE = 10
VALOR_CARTELA = 15.00
COMMUNITY_NAME = "Comunidade Jesus Misericordioso"
DB_PATH = Path(os.environ.get("BINGO_DB_PATH", str(Path(__file__).with_name("bingo.db"))))
BRASILIA_TZ = timezone(timedelta(hours=-3))

RODADAS = [
    ("1ª Rodada - 1 linha", "linha", 100.00),
    ("2ª Rodada - 2 linhas", "duas_linhas", 150.00),
    ("3ª Rodada - 4 cantos", "quatro_cantos", 200.00),
    ("4ª Rodada - X completo", "x", 250.00),
    ("5ª Rodada - Cartela cheia", "cartela_cheia", 500.00),
]


def agora_brasilia():
    return datetime.now(BRASILIA_TZ)


def iso_brasilia():
    return agora_brasilia().isoformat(timespec="seconds")


def conectar():
    if not DB_PATH.exists():
        raise RuntimeError(
            f"Banco não encontrado em {DB_PATH}. Abra o Bingo pelo menos uma vez antes de executar este script."
        )
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def exigir_colunas(conn, tabela, colunas):
    existentes = {r["name"] for r in conn.execute(f"PRAGMA table_info({tabela})").fetchall()}
    faltando = [c for c in colunas if c not in existentes]
    if faltando:
        raise RuntimeError(
            f"Seu banco parece ser de uma versão antiga. Tabela {tabela} sem: {', '.join(faltando)}. "
            "Atualize o sistema antes de rodar o teste."
        )


def validar_schema(conn):
    exigir_colunas(conn, "eventos", ["id", "nome", "data", "valor_cartela", "modalidade", "ativo", "status", "criado_em", "organizador_cartela", "horario_cartela", "premios_cartela", "vendas_fechadas_em"])
    exigir_colunas(conn, "vendedores", ["id", "nome", "telefone", "acesso_token", "codigo_acesso", "online_ativo"])
    exigir_colunas(conn, "cartelas", ["id", "evento_id", "numero", "numeros", "status", "vendedor_id", "lote_id", "impressa_em", "vendido_em"])
    exigir_colunas(conn, "lotes", ["id", "evento_id", "codigo", "inicio", "fim", "status", "vendedor_id", "criado_em", "impresso_em"])
    exigir_colunas(conn, "rodadas", ["id", "evento_id", "nome", "padrao", "premio", "ordem", "status"])


def backup_banco():
    pasta = Path(__file__).with_name("backups_testes")
    pasta.mkdir(exist_ok=True)
    destino = pasta / f"antes_teste_200_{agora_brasilia().strftime('%Y%m%d_%H%M%S')}.db"
    origem = sqlite3.connect(DB_PATH)
    alvo = sqlite3.connect(destino)
    try:
        origem.backup(alvo)
    finally:
        alvo.close()
        origem.close()
    return destino


def gerar_cartela_75():
    colunas = [
        random.sample(range(1, 16), 5),
        random.sample(range(16, 31), 5),
        random.sample(range(31, 46), 5),
        random.sample(range(46, 61), 5),
        random.sample(range(61, 76), 5),
    ]
    grade = [[colunas[col][linha] for col in range(5)] for linha in range(5)]
    grade[2][2] = 0
    return grade


def credencial_unica(conn):
    usados = {
        str(r["codigo_acesso"])
        for r in conn.execute(
            "SELECT codigo_acesso FROM vendedores WHERE codigo_acesso IS NOT NULL AND codigo_acesso<>''"
        ).fetchall()
    }
    while True:
        codigo = f"{secrets.randbelow(1000000):06d}"
        if codigo not in usados:
            return codigo, secrets.token_urlsafe(24)


def limpar_evento_teste_anterior(conn):
    rows = conn.execute("SELECT id FROM eventos WHERE nome=?", (EVENTO_TESTE,)).fetchall()
    for row in rows:
        eid = row["id"]
        uuids = set()
        if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='movimentacoes_vendas'").fetchone():
            for r in conn.execute(
                "SELECT sync_uuid FROM movimentacoes_vendas WHERE evento_id=? AND sync_uuid IS NOT NULL AND sync_uuid<>''",
                (eid,),
            ).fetchall():
                uuids.add(str(r["sync_uuid"]))
        if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_eventos'").fetchone():
            for r in conn.execute("SELECT uuid FROM sync_eventos WHERE evento_id=?", (eid,)).fetchall():
                uuids.add(str(r["uuid"]))
        if uuids and conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sync_recebidos'").fetchone():
            conn.executemany("DELETE FROM sync_recebidos WHERE uuid=?", [(u,) for u in uuids])

        tabelas = [
            "ganhadores", "sorteios", "movimentacoes_vendas", "acertos", "caixa_movimentos",
            "caixas", "rodadas", "sync_eventos", "auditoria", "cartelas", "lotes"
        ]
        existentes = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        for tabela in tabelas:
            if tabela in existentes:
                conn.execute(f"DELETE FROM {tabela} WHERE evento_id=?", (eid,))
        conn.execute("DELETE FROM eventos WHERE id=?", (eid,))


def obter_ou_criar_vendedores(conn):
    vendedores = []
    for i in range(1, QTD_VENDEDORES + 1):
        nome = f"TESTE - Vendedor {i:02d}"
        telefone = f"(91) 98000-{i:04d}"
        row = conn.execute("SELECT * FROM vendedores WHERE nome=? ORDER BY id LIMIT 1", (nome,)).fetchone()
        if row:
            codigo = row["codigo_acesso"] or None
            token = row["acesso_token"] or None
            if not codigo or not token:
                codigo, token = credencial_unica(conn)
            conn.execute(
                "UPDATE vendedores SET telefone=?,codigo_acesso=?,acesso_token=?,online_ativo=1 WHERE id=?",
                (telefone, codigo, token, row["id"]),
            )
            vendedor_id = row["id"]
        else:
            codigo, token = credencial_unica(conn)
            cur = conn.execute(
                "INSERT INTO vendedores (nome,telefone,acesso_token,codigo_acesso,online_ativo) VALUES (?,?,?,?,1)",
                (nome, telefone, token, codigo),
            )
            vendedor_id = cur.lastrowid
        vendedores.append({"id": vendedor_id, "nome": nome, "telefone": telefone, "codigo": codigo})
    return vendedores


def gerar_cartelas(conn, evento_id):
    assinaturas = set()
    numero = 1
    while numero <= QTD_CARTELAS:
        grade = gerar_cartela_75()
        assinatura = json.dumps(grade)
        if assinatura in assinaturas:
            continue
        conn.execute(
            "INSERT INTO cartelas (evento_id,numero,numeros,status) VALUES (?,?,?,'disponivel')",
            (evento_id, numero, assinatura),
        )
        assinaturas.add(assinatura)
        numero += 1


def criar_lotes_e_distribuir(conn, evento_id, vendedores, agora):
    lotes = []
    total_lotes = QTD_CARTELAS // CARTELAS_POR_LOTE
    for idx in range(total_lotes):
        inicio = idx * CARTELAS_POR_LOTE + 1
        fim = inicio + CARTELAS_POR_LOTE - 1
        vendedor = vendedores[idx // 2]  # 2 lotes = 20 cartelas por vendedor
        codigo = f"LOTE-{idx + 1:03d}"
        cur = conn.execute(
            """INSERT INTO lotes
               (evento_id,codigo,inicio,fim,status,observacao,vendedor_id,criado_em,impresso_em)
               VALUES (?,?,?,?, 'distribuido', ?,?,?,?)""",
            (evento_id, codigo, inicio, fim,
             "Lote criado automaticamente pelo script de teste de 200 cartelas",
             vendedor["id"], agora, agora),
        )
        lote_id = cur.lastrowid
        conn.execute(
            """UPDATE cartelas SET lote_id=?,vendedor_id=?,impressa_em=?
               WHERE evento_id=? AND numero BETWEEN ? AND ?""",
            (lote_id, vendedor["id"], agora, evento_id, inicio, fim),
        )
        lotes.append((codigo, inicio, fim, vendedor["nome"]))
    return lotes


def tentar_zerar_nuvem(conn):
    try:
        cfg = conn.execute("SELECT * FROM sync_config WHERE id=1").fetchone()
    except sqlite3.OperationalError:
        return
    if not cfg or not cfg["enabled"] or not (cfg["remote_url"] or "").strip() or not (cfg["token"] or "").strip():
        return
    print("\nA sincronização online está configurada.")
    print("Se já existem dados de teste no Railway, é recomendado limpá-los antes deste novo teste.")
    confirmacao = input("Digite ZERAR NUVEM para limpar a nuvem agora, ou ENTER para manter: ").strip()
    if confirmacao != "ZERAR NUVEM":
        print("Nuvem mantida. Você também pode usar o botão 'Zerar dados de teste da nuvem' no sistema.")
        return
    remote = (cfg["remote_url"] or "").strip().rstrip("/")
    token = (cfg["token"] or "").strip()
    body = json.dumps({"confirmacao": "ZERAR NUVEM", "solicitado_em": iso_brasilia()}).encode("utf-8")
    req = urllib.request.Request(
        remote + "/api/sync/reset-test-data",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "X-Bingo-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("ok"):
            conn.execute("UPDATE sync_config SET last_pull_seq=0,last_catalog_em=NULL")
            print("Nuvem zerada com sucesso.")
        else:
            print("A nuvem não confirmou a limpeza:", data.get("message") or data)
    except Exception as exc:
        print("Não foi possível zerar a nuvem:", exc)
        print("O teste local continuará normalmente.")


def main():
    print("=" * 72)
    print(" BINGO COMUNIDADE - PREPARAÇÃO AUTOMÁTICA DO TESTE COM 200 CARTELAS")
    print("=" * 72)
    print(f"Banco: {DB_PATH}")
    print("Eventos reais são preservados. Somente o evento de teste é recriado.")

    conn = conectar()
    try:
        validar_schema(conn)
    finally:
        conn.close()

    backup = backup_banco()
    print(f"Backup de segurança criado: {backup}")

    conn = conectar()
    try:
        tentar_zerar_nuvem(conn)
        limpar_evento_teste_anterior(conn)
        conn.execute("UPDATE eventos SET ativo=0")

        agora = iso_brasilia()
        data_evento = agora_brasilia().strftime("%Y-%m-%d")
        premios_texto = "\n".join(
            f"{nome}: R$ {premio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            for nome, _, premio in RODADAS
        )
        cur = conn.execute(
            """INSERT INTO eventos
               (nome,data,valor_cartela,modalidade,ativo,status,criado_em,organizador_cartela,horario_cartela,premios_cartela)
               VALUES (?,?,?,?,1,'preparacao',?,?,?,?)""",
            (EVENTO_TESTE, data_evento, VALOR_CARTELA, 75, agora,
             COMMUNITY_NAME, "Teste automatizado", premios_texto),
        )
        evento_id = cur.lastrowid

        vendedores = obter_ou_criar_vendedores(conn)
        gerar_cartelas(conn, evento_id)
        lotes = criar_lotes_e_distribuir(conn, evento_id, vendedores, agora)

        for ordem, (nome, padrao, premio) in enumerate(RODADAS, 1):
            conn.execute(
                "INSERT INTO rodadas (evento_id,nome,padrao,premio,ordem,status) VALUES (?,?,?,?,?,?)",
                (evento_id, nome, padrao, premio, ordem, "ativa" if ordem == 1 else "pendente"),
            )

        conn.execute(
            "UPDATE eventos SET vendas_fechadas_em=NULL,vendas_fechadas_por=NULL,status='preparacao' WHERE id=?",
            (evento_id,),
        )
        conn.commit()

        resumo = Path(__file__).with_name("RESUMO_TESTE_200_CARTELAS.txt")
        linhas = [
            "BINGO COMUNIDADE - RESUMO DO TESTE AUTOMATIZADO", "",
            f"Evento: {EVENTO_TESTE}", f"Cartelas: {QTD_CARTELAS}",
            f"Lotes: {len(lotes)} (10 cartelas por lote)",
            f"Vendedores: {QTD_VENDEDORES} (20 cartelas por vendedor)",
            f"Valor da cartela: R$ {VALOR_CARTELA:.2f}", "", "RODADAS:",
        ]
        for ordem, (nome, padrao, premio) in enumerate(RODADAS, 1):
            linhas.append(f"{ordem}. {nome} | padrão={padrao} | prêmio=R$ {premio:.2f}")
        linhas += ["", "VENDEDORES / CÓDIGOS:"]
        for v in vendedores:
            faixas = [f"{ini:04d}-{fim:04d}" for _, ini, fim, nome in lotes if nome == v["nome"]]
            linhas.append(f"{v['nome']} | código {v['codigo']} | cartelas {', '.join(faixas)}")
        resumo.write_text("\n".join(linhas), encoding="utf-8")

        print("\nPREPARAÇÃO CONCLUÍDA")
        print("✓ Evento de teste criado")
        print("✓ 200 cartelas únicas")
        print("✓ 20 lotes de 10")
        print("✓ 10 vendedores; 20 cartelas para cada um")
        print("✓ 5 rodadas/prêmios; primeira rodada ativa")
        print("✓ Cartelas e lotes marcados como impressos/distribuídos para o teste")
        print(f"✓ Resumo: {resumo.name}")
        print("\nAgora execute: 02_SIMULAR_VENDAS_200_CARTELAS.bat")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
