#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Simula as 200 vendas do evento de teste usando somente a biblioteca padrão."""

from pathlib import Path
from datetime import datetime, timezone, timedelta
import os
import sqlite3
import uuid

EVENTO_TESTE = "TESTE AUTOMATIZADO - 200 CARTELAS"
VALOR_CARTELA = 15.00
DB_PATH = Path(os.environ.get("BINGO_DB_PATH", str(Path(__file__).with_name("bingo.db"))))
BRASILIA_TZ = timezone(timedelta(hours=-3))


def agora_brasilia():
    return datetime.now(BRASILIA_TZ)


def iso_brasilia():
    return agora_brasilia().isoformat(timespec="seconds")


def conectar():
    if not DB_PATH.exists():
        raise RuntimeError(f"Banco não encontrado em {DB_PATH}.")
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=20000")
    return conn


def backup_banco(nome):
    pasta = Path(__file__).with_name("backups_testes")
    pasta.mkdir(exist_ok=True)
    destino = pasta / nome
    origem = sqlite3.connect(DB_PATH)
    alvo = sqlite3.connect(destino)
    try:
        origem.backup(alvo)
    finally:
        alvo.close()
        origem.close()
    return destino


def forma_por_posicao(posicao):
    if posicao <= 8:
        return "Dinheiro"
    if posicao <= 16:
        return "PIX"
    return "Outros"


def limpar_vendas_anteriores(conn, evento_id):
    uuids = [
        str(r["sync_uuid"])
        for r in conn.execute(
            "SELECT sync_uuid FROM movimentacoes_vendas WHERE evento_id=? AND sync_uuid IS NOT NULL AND sync_uuid<>''",
            (evento_id,),
        ).fetchall()
    ]
    if uuids:
        conn.executemany("DELETE FROM sync_recebidos WHERE uuid=?", [(u,) for u in uuids])
    conn.execute("DELETE FROM sync_eventos WHERE evento_id=?", (evento_id,))
    conn.execute("DELETE FROM movimentacoes_vendas WHERE evento_id=?", (evento_id,))
    conn.execute("DELETE FROM ganhadores WHERE evento_id=?", (evento_id,))
    conn.execute("DELETE FROM sorteios WHERE evento_id=?", (evento_id,))
    conn.execute("DELETE FROM acertos WHERE evento_id=?", (evento_id,))
    conn.execute("DELETE FROM caixa_movimentos WHERE evento_id=?", (evento_id,))
    conn.execute("DELETE FROM caixas WHERE evento_id=?", (evento_id,))
    conn.execute(
        """UPDATE cartelas SET status='disponivel',comprador=NULL,telefone=NULL,pagamento=NULL,
           vendido_em=NULL,vendido_por_usuario_id=NULL WHERE evento_id=?""",
        (evento_id,),
    )


def main():
    print("=" * 72)
    print(" BINGO COMUNIDADE - SIMULAÇÃO DE 200 VENDAS")
    print("=" * 72)
    print(f"Banco: {DB_PATH}")

    conn = conectar()
    try:
        evento = conn.execute(
            "SELECT * FROM eventos WHERE nome=? ORDER BY id DESC LIMIT 1", (EVENTO_TESTE,)
        ).fetchone()
        if not evento:
            raise RuntimeError("Evento de teste não encontrado. Execute primeiro 01_PREPARAR_TESTE_200_CARTELAS.bat")

        total = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=?", (evento["id"],)).fetchone()["c"]
        if total != 200:
            raise RuntimeError(f"O evento deveria ter 200 cartelas, mas possui {total}.")
        sem_vendedor = conn.execute(
            "SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id IS NULL", (evento["id"],)
        ).fetchone()["c"]
        if sem_vendedor:
            raise RuntimeError(f"Existem {sem_vendedor} cartelas sem vendedor. Rode novamente o script de preparação.")
    finally:
        conn.close()

    backup = backup_banco(f"antes_vendas_teste_200_{agora_brasilia().strftime('%Y%m%d_%H%M%S')}.db")
    print(f"Backup de segurança criado: {backup}")

    conn = conectar()
    try:
        evento = conn.execute(
            "SELECT * FROM eventos WHERE nome=? ORDER BY id DESC LIMIT 1", (EVENTO_TESTE,)
        ).fetchone()
        limpar_vendas_anteriores(conn, evento["id"])

        cards = conn.execute(
            """SELECT c.id,c.numero,c.vendedor_id,v.nome vendedor
               FROM cartelas c JOIN vendedores v ON v.id=c.vendedor_id
               WHERE c.evento_id=? ORDER BY v.id,c.numero""",
            (evento["id"],),
        ).fetchall()

        posicoes = {}
        contagem = {"Dinheiro": 0, "PIX": 0, "Outros": 0}
        por_vendedor = {}
        inicio = agora_brasilia() - timedelta(minutes=len(cards))

        for indice, card in enumerate(cards, 1):
            vendedor_id = card["vendedor_id"]
            posicoes[vendedor_id] = posicoes.get(vendedor_id, 0) + 1
            pagamento = forma_por_posicao(posicoes[vendedor_id])
            contagem[pagamento] += 1
            por_vendedor.setdefault(card["vendedor"], {"Dinheiro": 0, "PIX": 0, "Outros": 0})[pagamento] += 1

            comprador = f"Comprador Teste {card['numero']:04d}"
            telefone = f"(91) 99{card['numero']:03d}-{(7000 + card['numero']) % 10000:04d}"
            criado_em = (inicio + timedelta(minutes=indice)).isoformat(timespec="seconds")
            suid = str(uuid.uuid4())

            conn.execute(
                """UPDATE cartelas SET status='vendida',comprador=?,telefone=?,pagamento=?,
                   vendido_em=?,vendido_por_usuario_id=NULL WHERE id=?""",
                (comprador, telefone, pagamento, criado_em, card["id"]),
            )
            conn.execute(
                """INSERT INTO movimentacoes_vendas
                   (evento_id,cartela_id,numero,tipo,comprador,telefone,pagamento,vendedor_id,
                    usuario_id,criado_em,origem,sync_uuid,sync_enviado)
                   VALUES (?,?,?,?,?,?,?,?,NULL,?,?,?,0)""",
                (evento["id"], card["id"], card["numero"], "venda", comprador, telefone,
                 pagamento, vendedor_id, criado_em, "celular", suid),
            )

        agora = iso_brasilia()
        conn.execute("UPDATE rodadas SET status='pendente' WHERE evento_id=?", (evento["id"],))
        primeira = conn.execute(
            "SELECT id FROM rodadas WHERE evento_id=? ORDER BY ordem,id LIMIT 1", (evento["id"],)
        ).fetchone()
        if primeira:
            conn.execute("UPDATE rodadas SET status='ativa' WHERE id=?", (primeira["id"],))
        conn.execute(
            """UPDATE eventos SET ativo=1,status='em_andamento',encerrado_em=NULL,
               vendas_fechadas_em=?,vendas_fechadas_por=NULL WHERE id=?""",
            (agora, evento["id"]),
        )
        conn.execute("UPDATE eventos SET ativo=0 WHERE id<>?", (evento["id"],))
        conn.commit()

        backup_final = backup_banco(
            f"pre_sorteio_teste_200_evento_{evento['id']}_{agora_brasilia().strftime('%Y%m%d_%H%M%S')}.db"
        )

        valores = {k: v * VALOR_CARTELA for k, v in contagem.items()}
        total_valor = sum(valores.values())
        resumo = Path(__file__).with_name("RESUMO_VENDAS_TESTE_200.txt")
        linhas = [
            "BINGO COMUNIDADE - RESUMO DAS VENDAS DE TESTE", "",
            f"Evento: {EVENTO_TESTE}", "200 de 200 cartelas vendidas",
            f"Dinheiro: {contagem['Dinheiro']} cartelas = R$ {valores['Dinheiro']:.2f}",
            f"PIX: {contagem['PIX']} cartelas = R$ {valores['PIX']:.2f}",
            f"Outros: {contagem['Outros']} cartelas = R$ {valores['Outros']:.2f}",
            f"TOTAL REGISTRADO: R$ {total_valor:.2f}", "", "POR VENDEDOR:",
        ]
        for vendedor, formas in sorted(por_vendedor.items()):
            linhas.append(
                f"{vendedor}: 20 vendas | Dinheiro {formas['Dinheiro']} | PIX {formas['PIX']} | Outros {formas['Outros']}"
            )
        linhas += [
            "", "Estado final:", "- vendas fechadas", "- evento em andamento",
            "- primeira rodada ativa", "- sorteio zerado", f"- backup pré-sorteio: {backup_final.name}",
            "", "Se usa o Railway, abra Online + Offline e clique em Sincronizar agora antes do sorteio."
        ]
        resumo.write_text("\n".join(linhas), encoding="utf-8")

        print("\nSIMULAÇÃO CONCLUÍDA")
        print(f"✓ Dinheiro: {contagem['Dinheiro']} vendas = R$ {valores['Dinheiro']:.2f}")
        print(f"✓ PIX:      {contagem['PIX']} vendas = R$ {valores['PIX']:.2f}")
        print(f"✓ Outros:   {contagem['Outros']} vendas = R$ {valores['Outros']:.2f}")
        print(f"✓ Total:    200 vendas = R$ {total_valor:.2f}")
        print("✓ Vendas fechadas")
        print("✓ Evento em andamento")
        print("✓ 1ª rodada ativa e sorteio zerado")
        print(f"✓ Backup pré-sorteio: {backup_final}")
        print(f"✓ Resumo: {resumo.name}")
        print("\nSe estiver usando o Railway: abra Online + Offline e clique em SINCRONIZAR AGORA.")
        print("Depois disso, basta abrir o menu SORTEIO.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
