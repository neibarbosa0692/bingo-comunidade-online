from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, Response, session, g
import sqlite3
import random
import json
import socket
import shutil
from pathlib import Path
from io import BytesIO
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import os
import uuid
import time
import threading
import urllib.request
import urllib.error

import qrcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics

app = Flask(__name__)
DB_PATH = Path(os.environ.get('BINGO_DB_PATH', str(Path(__file__).with_name('bingo.db'))))
SECRET_PATH = Path(__file__).with_name(".secret_key")
ENV_SECRET = os.environ.get('BINGO_SECRET_KEY','').strip()
if ENV_SECRET:
    app.secret_key = ENV_SECRET
elif SECRET_PATH.exists():
    app.secret_key = SECRET_PATH.read_text(encoding="utf-8").strip()
else:
    app.secret_key = secrets.token_hex(32)
    try:
        SECRET_PATH.write_text(app.secret_key, encoding="utf-8")
    except Exception:
        pass

PRIMARY = HexColor('#5B46E8')
TEXT = HexColor('#172033')
MUTED = HexColor('#6F7890')
LINE = HexColor('#E4E8F0')
SOFT = HexColor('#F4F2FF')
SUCCESS = HexColor('#1AAE72')

# Identidade visual da cartela personalizada
CARD_NAVY = HexColor('#0A2342')
CARD_GOLD = HexColor('#B77816')
CARD_RED = HexColor('#C62828')
CARD_BLUE = HexColor('#157AA6')
CARD_PALE = HexColor('#FBF8F0')
COMMUNITY_NAME = 'Comunidade Jesus Misericordioso'
LOGO_PATH = Path(__file__).with_name('static') / 'logo_comunidade.png'
CARD_TEMPLATE_PATH = Path(__file__).with_name('static') / 'cartela_template_oficial.png'
SYSTEM_BUILD = 'V11-HIBRIDO-ONLINE-OFFLINE-2026-09-02'
SYSTEM_PORT = int(os.environ.get('BINGO_PORT', '8765'))
BINGO_MODE = os.environ.get('BINGO_MODE', 'local').strip().lower()
CLOUD_SYNC_TOKEN = os.environ.get('BINGO_SYNC_TOKEN', '').strip()
SYNC_WORKER_STARTED = False
DEFAULT_CARD_TIME = 'Após a Santa Missa das 18h'
DEFAULT_CARD_PRIZES = [
    'R$ 300,00',
    'R$ 100,00 + Liquidificador',
    'R$ 100,00 + Liquidificador',
    'Sanduicheira + Batedeira',
    'Cesta Básica + Liquidificador Turbo',
]


def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=20000')
    try:
        conn.execute('PRAGMA journal_mode=WAL')
    except Exception:
        pass
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        data TEXT,
        valor_cartela REAL NOT NULL DEFAULT 10,
        modalidade INTEGER NOT NULL DEFAULT 75,
        ativo INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS vendedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        telefone TEXT
    );

    CREATE TABLE IF NOT EXISTS cartelas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        numero INTEGER NOT NULL,
        numeros TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'disponivel',
        vendedor_id INTEGER,
        comprador TEXT,
        telefone TEXT,
        pagamento TEXT,
        UNIQUE(evento_id, numero)
    );

    CREATE TABLE IF NOT EXISTS sorteios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        numero INTEGER NOT NULL,
        ordem INTEGER NOT NULL,
        UNIQUE(evento_id, numero)
    );

    CREATE TABLE IF NOT EXISTS ganhadores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        cartela_id INTEGER NOT NULL,
        padrao TEXT NOT NULL,
        confirmado INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS acertos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        vendedor_id INTEGER NOT NULL,
        valor REAL NOT NULL,
        observacao TEXT,
        criado_em TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS rodadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        padrao TEXT NOT NULL DEFAULT 'cartela_cheia',
        premio REAL NOT NULL DEFAULT 0,
        ordem INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'pendente'
    );

    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        usuario TEXT NOT NULL UNIQUE,
        senha_hash TEXT NOT NULL,
        perfil TEXT NOT NULL DEFAULT 'operador',
        ativo INTEGER NOT NULL DEFAULT 1,
        obrigar_troca INTEGER NOT NULL DEFAULT 0,
        criado_em TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS auditoria (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER,
        usuario_id INTEGER,
        usuario_nome TEXT,
        acao TEXT NOT NULL,
        entidade TEXT,
        detalhes TEXT,
        ip TEXT,
        criado_em TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS movimentacoes_vendas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        cartela_id INTEGER NOT NULL,
        numero INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        comprador TEXT,
        telefone TEXT,
        pagamento TEXT,
        vendedor_id INTEGER,
        usuario_id INTEGER,
        motivo TEXT,
        criado_em TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS caixas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        aberto_por INTEGER,
        aberto_em TEXT NOT NULL,
        valor_inicial REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'aberto',
        fechado_por INTEGER,
        fechado_em TEXT,
        valor_informado REAL,
        valor_sistema REAL,
        diferenca REAL,
        observacao TEXT
    );

    CREATE TABLE IF NOT EXISTS caixa_movimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        caixa_id INTEGER NOT NULL,
        evento_id INTEGER NOT NULL,
        tipo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        usuario_id INTEGER,
        criado_em TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS lotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evento_id INTEGER NOT NULL,
        codigo TEXT NOT NULL,
        inicio INTEGER NOT NULL,
        fim INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'preparado',
        observacao TEXT,
        vendedor_id INTEGER,
        criado_por INTEGER,
        criado_em TEXT NOT NULL,
        impresso_em TEXT,
        UNIQUE(evento_id, codigo)
    );

    CREATE TABLE IF NOT EXISTS sync_config (
        id INTEGER PRIMARY KEY CHECK (id=1),
        remote_url TEXT,
        token TEXT,
        enabled INTEGER NOT NULL DEFAULT 0,
        auto_interval INTEGER NOT NULL DEFAULT 60,
        last_pull_seq INTEGER NOT NULL DEFAULT 0,
        last_sync_em TEXT,
        last_sync_ok INTEGER NOT NULL DEFAULT 0,
        last_sync_msg TEXT,
        last_catalog_em TEXT
    );

    CREATE TABLE IF NOT EXISTS sync_eventos (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid TEXT NOT NULL UNIQUE,
        tipo TEXT NOT NULL,
        evento_id INTEGER,
        numero INTEGER,
        payload TEXT NOT NULL,
        origem TEXT NOT NULL,
        criado_em TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sync_recebidos (
        uuid TEXT PRIMARY KEY,
        origem TEXT,
        recebido_em TEXT NOT NULL
    );
    """)

    # Migrações compatíveis com bancos das versões anteriores.
    cols_eventos = {r['name'] for r in conn.execute("PRAGMA table_info(eventos)").fetchall()}
    if 'url_rede' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN url_rede TEXT")
    if 'status' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN status TEXT NOT NULL DEFAULT 'preparacao'")
    if 'criado_em' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN criado_em TEXT")
    if 'encerrado_em' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN encerrado_em TEXT")
    if 'organizador_cartela' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN organizador_cartela TEXT")
    if 'horario_cartela' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN horario_cartela TEXT")
    if 'premios_cartela' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN premios_cartela TEXT")
    if 'vendas_fechadas_em' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN vendas_fechadas_em TEXT")
    if 'vendas_fechadas_por' not in cols_eventos:
        conn.execute("ALTER TABLE eventos ADD COLUMN vendas_fechadas_por INTEGER")
    conn.execute("UPDATE eventos SET status='preparacao' WHERE status IS NULL OR status=''")
    conn.execute("UPDATE eventos SET organizador_cartela=? WHERE organizador_cartela IS NULL OR organizador_cartela=''", (COMMUNITY_NAME,))
    conn.execute("UPDATE eventos SET horario_cartela=? WHERE horario_cartela IS NULL OR horario_cartela=''", (DEFAULT_CARD_TIME,))
    conn.execute("UPDATE eventos SET premios_cartela=? WHERE premios_cartela IS NULL OR premios_cartela=''", ('\n'.join(DEFAULT_CARD_PRIZES),))
    conn.execute("UPDATE eventos SET criado_em=? WHERE criado_em IS NULL OR criado_em=''", (datetime.now().isoformat(timespec='seconds'),))
    cols_ganhadores = {r['name'] for r in conn.execute("PRAGMA table_info(ganhadores)").fetchall()}
    if 'rodada_id' not in cols_ganhadores:
        conn.execute("ALTER TABLE ganhadores ADD COLUMN rodada_id INTEGER")

    cols_vendedores = {r['name'] for r in conn.execute("PRAGMA table_info(vendedores)").fetchall()}
    if 'acesso_token' not in cols_vendedores:
        conn.execute("ALTER TABLE vendedores ADD COLUMN acesso_token TEXT")
    if 'codigo_acesso' not in cols_vendedores:
        conn.execute("ALTER TABLE vendedores ADD COLUMN codigo_acesso TEXT")
    if 'online_ativo' not in cols_vendedores:
        conn.execute("ALTER TABLE vendedores ADD COLUMN online_ativo INTEGER NOT NULL DEFAULT 1")

    cols_cartelas = {r['name'] for r in conn.execute("PRAGMA table_info(cartelas)").fetchall()}
    if 'vendido_em' not in cols_cartelas:
        conn.execute("ALTER TABLE cartelas ADD COLUMN vendido_em TEXT")
    if 'vendido_por_usuario_id' not in cols_cartelas:
        conn.execute("ALTER TABLE cartelas ADD COLUMN vendido_por_usuario_id INTEGER")
    if 'lote_id' not in cols_cartelas:
        conn.execute("ALTER TABLE cartelas ADD COLUMN lote_id INTEGER")
    if 'impressa_em' not in cols_cartelas:
        conn.execute("ALTER TABLE cartelas ADD COLUMN impressa_em TEXT")
    if 'inutilizada_em' not in cols_cartelas:
        conn.execute("ALTER TABLE cartelas ADD COLUMN inutilizada_em TEXT")
    if 'inutilizada_motivo' not in cols_cartelas:
        conn.execute("ALTER TABLE cartelas ADD COLUMN inutilizada_motivo TEXT")

    cols_mov_vendas = {r['name'] for r in conn.execute("PRAGMA table_info(movimentacoes_vendas)").fetchall()}
    if 'origem' not in cols_mov_vendas:
        conn.execute("ALTER TABLE movimentacoes_vendas ADD COLUMN origem TEXT")
    if 'sync_uuid' not in cols_mov_vendas:
        conn.execute("ALTER TABLE movimentacoes_vendas ADD COLUMN sync_uuid TEXT")
    if 'sync_enviado' not in cols_mov_vendas:
        conn.execute("ALTER TABLE movimentacoes_vendas ADD COLUMN sync_enviado INTEGER NOT NULL DEFAULT 0")
    conn.execute("UPDATE movimentacoes_vendas SET sync_enviado=1 WHERE sync_uuid IS NULL OR sync_uuid=''")

    cols_acertos = {r['name'] for r in conn.execute("PRAGMA table_info(acertos)").fetchall()}
    if 'forma_pagamento' not in cols_acertos:
        conn.execute("ALTER TABLE acertos ADD COLUMN forma_pagamento TEXT")

    conn.execute("INSERT OR IGNORE INTO sync_config (id,enabled,auto_interval,last_pull_seq,last_sync_ok) VALUES (1,0,60,0,0)")

    # Credenciais individuais dos vendedores para acesso remoto.
    vendedores_sem_credencial = conn.execute("SELECT id FROM vendedores WHERE acesso_token IS NULL OR acesso_token='' OR codigo_acesso IS NULL OR codigo_acesso=''").fetchall()
    usados = {str(r['codigo_acesso']) for r in conn.execute("SELECT codigo_acesso FROM vendedores WHERE codigo_acesso IS NOT NULL AND codigo_acesso<>''").fetchall()}
    for row in vendedores_sem_credencial:
        codigo = None
        for _ in range(50):
            candidato = f"{secrets.randbelow(1000000):06d}"
            if candidato not in usados:
                codigo = candidato; usados.add(candidato); break
        codigo = codigo or secrets.token_hex(3).upper()
        conn.execute("UPDATE vendedores SET acesso_token=COALESCE(NULLIF(acesso_token,''),?), codigo_acesso=COALESCE(NULLIF(codigo_acesso,''),?), online_ativo=COALESCE(online_ativo,1) WHERE id=?",
                     (secrets.token_urlsafe(24), codigo, row['id']))

    # Primeiro acesso da V5: administrador local temporário.
    if conn.execute("SELECT COUNT(*) c FROM usuarios").fetchone()['c'] == 0:
        conn.execute("""INSERT INTO usuarios (nome,usuario,senha_hash,perfil,ativo,obrigar_troca,criado_em)
            VALUES (?,?,?,?,1,1,?)""",
            ('Administrador', 'admin', generate_password_hash('admin123'), 'admin', datetime.now().isoformat(timespec='seconds')))

    evento = conn.execute("SELECT * FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
    if not evento:
        conn.execute(
            """INSERT INTO eventos (nome, data, valor_cartela, modalidade, ativo, status, criado_em, organizador_cartela, horario_cartela, premios_cartela)
               VALUES (?, ?, ?, ?, 1, 'preparacao', ?, ?, ?, ?)""",
            ("Ação Entre Amigos", "2026-11-07", 15.0, 75, datetime.now().isoformat(timespec='seconds'),
             COMMUNITY_NAME, DEFAULT_CARD_TIME, '\n'.join(DEFAULT_CARD_PRIZES))
        )
        conn.commit()
        evento = conn.execute("SELECT * FROM eventos WHERE ativo=1 ORDER BY id DESC LIMIT 1").fetchone()

    criar_rodadas_padrao(conn, evento['id'])
    conn.commit()
    conn.close()


def evento_ativo(conn):
    evento = conn.execute("SELECT * FROM eventos WHERE ativo=1 ORDER BY id DESC LIMIT 1").fetchone()
    if evento:
        return evento
    evento = conn.execute("SELECT * FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
    if evento:
        conn.execute("UPDATE eventos SET ativo=0")
        conn.execute("UPDATE eventos SET ativo=1 WHERE id=?", (evento['id'],))
        conn.commit()
        evento = conn.execute("SELECT * FROM eventos WHERE id=?", (evento['id'],)).fetchone()
    return evento


def status_evento_label(status):
    return {
        'preparacao': 'Em preparação',
        'em_andamento': 'Em andamento',
        'encerrado': 'Encerrado',
    }.get(status or 'preparacao', status or 'Em preparação')


def criar_rodadas_padrao(conn, evento_id):
    qtd = conn.execute("SELECT COUNT(*) c FROM rodadas WHERE evento_id=?", (evento_id,)).fetchone()['c']
    if qtd == 0:
        conn.executemany(
            "INSERT INTO rodadas (evento_id,nome,padrao,premio,ordem,status) VALUES (?,?,?,?,?,?)",
            [
                (evento_id, '1ª premiação — 1 linha', 'linha', 0, 1, 'ativa'),
                (evento_id, '2ª premiação — 2 linhas', 'duas_linhas', 0, 2, 'pendente'),
                (evento_id, 'Prêmio principal — Cartela cheia', 'cartela_cheia', 0, 3, 'pendente'),
            ]
        )


def evento_encerrado(evento):
    return bool(evento and 'status' in evento.keys() and evento['status'] == 'encerrado')


def local_ip():
    """Melhor tentativa de descobrir o IP do notebook na rede local, sem depender da internet."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(('10.255.255.255', 1))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'


def base_url_rede(evento):
    configurada = (evento['url_rede'] or '').strip() if 'url_rede' in evento.keys() else ''
    if configurada:
        return configurada.rstrip('/')
    return f"http://{local_ip()}:{SYSTEM_PORT}"



def _sync_cfg(conn=None):
    fechar = False
    if conn is None:
        conn = get_db(); fechar = True
    row = conn.execute("SELECT * FROM sync_config WHERE id=1").fetchone()
    if fechar:
        conn.close()
    return row


def _remote_base_url():
    if BINGO_MODE == 'cloud':
        return ''
    try:
        cfg = _sync_cfg()
        return (cfg['remote_url'] or '').strip().rstrip('/') if cfg else ''
    except Exception:
        return ''


def base_url_publico(evento):
    """URL gravada nos QR Codes. Quando a nuvem está configurada, prioriza a URL online."""
    remoto = _remote_base_url()
    if remoto:
        return remoto
    return base_url_rede(evento)


def vendas_fechadas(evento):
    try:
        return bool(evento and 'vendas_fechadas_em' in evento.keys() and evento['vendas_fechadas_em'])
    except Exception:
        return False


def _sync_token_valido():
    recebido = request.headers.get('X-Bingo-Token', '').strip()
    esperado = CLOUD_SYNC_TOKEN
    if not esperado:
        try:
            cfg = _sync_cfg()
            esperado = (cfg['token'] or '').strip() if cfg else ''
        except Exception:
            esperado = ''
    return bool(esperado and recebido and secrets.compare_digest(recebido, esperado))


def _http_json(method, url, payload=None, token='', timeout=12):
    data = None
    headers = {'Accept': 'application/json', 'User-Agent': 'Bingo-Comunidade-V11'}
    if token:
        headers['X-Bingo-Token'] = token
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json; charset=utf-8'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw else {}


def _sync_atualizar_status(ok, mensagem, catalog=False):
    if BINGO_MODE != 'local':
        return
    try:
        conn = get_db(); agora = datetime.now().isoformat(timespec='seconds')
        if catalog:
            conn.execute("UPDATE sync_config SET last_sync_em=?,last_sync_ok=?,last_sync_msg=?,last_catalog_em=? WHERE id=1",
                         (agora, 1 if ok else 0, str(mensagem)[:500], agora))
        else:
            conn.execute("UPDATE sync_config SET last_sync_em=?,last_sync_ok=?,last_sync_msg=? WHERE id=1",
                         (agora, 1 if ok else 0, str(mensagem)[:500]))
        conn.commit(); conn.close()
    except Exception:
        pass


def _snapshot_local():
    conn = get_db(); evento = evento_ativo(conn)
    if not evento:
        conn.close(); return {'evento': None, 'vendedores': [], 'lotes': [], 'cartelas': []}
    eid = evento['id']
    campos_evento = ['id','nome','data','valor_cartela','modalidade','ativo','status','criado_em','encerrado_em','url_rede',
                     'organizador_cartela','horario_cartela','premios_cartela','vendas_fechadas_em','vendas_fechadas_por']
    ed = {k:evento[k] for k in campos_evento if k in evento.keys()}
    vendedores = [dict(r) for r in conn.execute("SELECT * FROM vendedores ORDER BY id").fetchall()]
    lotes = [dict(r) for r in conn.execute("SELECT * FROM lotes WHERE evento_id=? ORDER BY id", (eid,)).fetchall()]
    cartelas = [dict(r) for r in conn.execute("SELECT * FROM cartelas WHERE evento_id=? ORDER BY numero", (eid,)).fetchall()]
    conn.close()
    return {'build':SYSTEM_BUILD,'gerado_em':datetime.now().isoformat(timespec='seconds'),'evento':ed,
            'vendedores':vendedores,'lotes':lotes,'cartelas':cartelas}


def _cloud_aplicar_snapshot(snapshot):
    evento = snapshot.get('evento') or {}
    if not evento or not evento.get('id'):
        return {'ok':False,'message':'Snapshot sem evento.'}
    conn = get_db(); eid = int(evento['id'])
    # Evento: o computador local é a autoridade das configurações operacionais.
    existente = conn.execute("SELECT id FROM eventos WHERE id=?", (eid,)).fetchone()
    if existente:
        conn.execute("""UPDATE eventos SET nome=?,data=?,valor_cartela=?,modalidade=?,ativo=?,status=?,url_rede=?,organizador_cartela=?,horario_cartela=?,premios_cartela=?,vendas_fechadas_em=?,vendas_fechadas_por=? WHERE id=?""",
                     (evento.get('nome'),evento.get('data'),evento.get('valor_cartela',10),evento.get('modalidade',75),evento.get('ativo',1),
                      evento.get('status','preparacao'),evento.get('url_rede'),evento.get('organizador_cartela'),evento.get('horario_cartela'),
                      evento.get('premios_cartela'),evento.get('vendas_fechadas_em'),evento.get('vendas_fechadas_por'),eid))
    else:
        conn.execute("""INSERT INTO eventos (id,nome,data,valor_cartela,modalidade,ativo,status,criado_em,url_rede,organizador_cartela,horario_cartela,premios_cartela,vendas_fechadas_em,vendas_fechadas_por)
                     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (eid,evento.get('nome') or 'Bingo',evento.get('data'),evento.get('valor_cartela',10),evento.get('modalidade',75),evento.get('ativo',1),
                      evento.get('status','preparacao'),evento.get('criado_em') or datetime.now().isoformat(timespec='seconds'),evento.get('url_rede'),
                      evento.get('organizador_cartela'),evento.get('horario_cartela'),evento.get('premios_cartela'),evento.get('vendas_fechadas_em'),evento.get('vendas_fechadas_por')))
    if evento.get('ativo'):
        conn.execute("UPDATE eventos SET ativo=CASE WHEN id=? THEN 1 ELSE 0 END", (eid,))

    for v in snapshot.get('vendedores') or []:
        if not v.get('id'): continue
        atual = conn.execute("SELECT id FROM vendedores WHERE id=?", (v['id'],)).fetchone()
        vals=(v.get('nome') or 'Vendedor',v.get('telefone'),v.get('acesso_token'),v.get('codigo_acesso'),v.get('online_ativo',1),v['id'])
        if atual:
            conn.execute("UPDATE vendedores SET nome=?,telefone=?,acesso_token=?,codigo_acesso=?,online_ativo=? WHERE id=?", vals)
        else:
            conn.execute("INSERT INTO vendedores (id,nome,telefone,acesso_token,codigo_acesso,online_ativo) VALUES (?,?,?,?,?,?)",
                         (v['id'],v.get('nome') or 'Vendedor',v.get('telefone'),v.get('acesso_token'),v.get('codigo_acesso'),v.get('online_ativo',1)))

    for l in snapshot.get('lotes') or []:
        if not l.get('id'): continue
        atual=conn.execute("SELECT id FROM lotes WHERE id=?",(l['id'],)).fetchone()
        vals=(l.get('evento_id',eid),l.get('codigo') or f"L{l['id']}",l.get('inicio',0),l.get('fim',0),l.get('status','preparado'),
              l.get('observacao'),l.get('vendedor_id'),l.get('criado_por'),l.get('criado_em') or datetime.now().isoformat(timespec='seconds'),l.get('impresso_em'),l['id'])
        if atual:
            conn.execute("UPDATE lotes SET evento_id=?,codigo=?,inicio=?,fim=?,status=?,observacao=?,vendedor_id=?,criado_por=?,criado_em=?,impresso_em=? WHERE id=?",vals)
        else:
            conn.execute("INSERT INTO lotes (evento_id,codigo,inicio,fim,status,observacao,vendedor_id,criado_por,criado_em,impresso_em,id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",vals)

    # Nunca sobrescreve uma venda feita na nuvem com um snapshot local ainda atrasado.
    for c in snapshot.get('cartelas') or []:
        numero=c.get('numero')
        if numero is None: continue
        atual=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=?",(eid,numero)).fetchone()
        if atual:
            manter_venda = atual['status']=='vendida' and c.get('status')!='vendida'
            if manter_venda:
                conn.execute("UPDATE cartelas SET numeros=?,vendedor_id=?,lote_id=?,impressa_em=?,inutilizada_em=?,inutilizada_motivo=? WHERE id=?",
                             (c.get('numeros'),c.get('vendedor_id'),c.get('lote_id'),c.get('impressa_em'),c.get('inutilizada_em'),c.get('inutilizada_motivo'),atual['id']))
            else:
                conn.execute("""UPDATE cartelas SET numeros=?,status=?,vendedor_id=?,comprador=?,telefone=?,pagamento=?,vendido_em=?,vendido_por_usuario_id=?,lote_id=?,impressa_em=?,inutilizada_em=?,inutilizada_motivo=? WHERE id=?""",
                             (c.get('numeros'),c.get('status','disponivel'),c.get('vendedor_id'),c.get('comprador'),c.get('telefone'),c.get('pagamento'),
                              c.get('vendido_em'),c.get('vendido_por_usuario_id'),c.get('lote_id'),c.get('impressa_em'),c.get('inutilizada_em'),c.get('inutilizada_motivo'),atual['id']))
        else:
            conn.execute("""INSERT INTO cartelas (evento_id,numero,numeros,status,vendedor_id,comprador,telefone,pagamento,vendido_em,vendido_por_usuario_id,lote_id,impressa_em,inutilizada_em,inutilizada_motivo)
                         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (eid,numero,c.get('numeros') or '[]',c.get('status','disponivel'),c.get('vendedor_id'),c.get('comprador'),c.get('telefone'),c.get('pagamento'),
                          c.get('vendido_em'),c.get('vendido_por_usuario_id'),c.get('lote_id'),c.get('impressa_em'),c.get('inutilizada_em'),c.get('inutilizada_motivo')))
    conn.commit(); conn.close()
    return {'ok':True,'message':f"Catálogo atualizado: {len(snapshot.get('cartelas') or [])} cartelas."}


def _novo_sync_uuid():
    return str(uuid.uuid4())


def _garantir_uuid_movimento(conn, movimento_id):
    row=conn.execute("SELECT sync_uuid FROM movimentacoes_vendas WHERE id=?",(movimento_id,)).fetchone()
    if row and row['sync_uuid']:
        return row['sync_uuid']
    uid=_novo_sync_uuid(); conn.execute("UPDATE movimentacoes_vendas SET sync_uuid=? WHERE id=?",(uid,movimento_id)); return uid


def _registrar_evento_sync(conn, uid, tipo, evento_id, numero, payload, origem):
    conn.execute("INSERT OR IGNORE INTO sync_eventos (uuid,tipo,evento_id,numero,payload,origem,criado_em) VALUES (?,?,?,?,?,?,?)",
                 (uid,tipo,evento_id,numero,json.dumps(payload,ensure_ascii=False),origem,datetime.now().isoformat(timespec='seconds')))


def _aplicar_movimento_recebido(conn, mov, origem='remoto'):
    uid=(mov.get('sync_uuid') or mov.get('uuid') or '').strip()
    if not uid:
        return False, 'Movimento sem UUID.'
    if conn.execute("SELECT 1 FROM sync_recebidos WHERE uuid=?",(uid,)).fetchone():
        return True, 'duplicado'
    eid=int(mov.get('evento_id') or 0); numero=int(mov.get('numero') or 0); tipo=mov.get('tipo') or 'venda'
    card=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=?",(eid,numero)).fetchone()
    if not card:
        return False, f'Cartela {numero:04d} não existe.'
    agora=mov.get('criado_em') or datetime.now().isoformat(timespec='seconds')
    if tipo=='venda':
        if card['status']=='vendida':
            # Venda idêntica é idempotente; venda diferente vira conflito.
            mesmo=(str(card['comprador'] or '')==str(mov.get('comprador') or '') and str(card['vendedor_id'] or '')==str(mov.get('vendedor_id') or ''))
            if not mesmo:
                return False, f'CONFLITO: cartela {numero:04d} já vendida.'
        else:
            conn.execute("""UPDATE cartelas SET status='vendida',comprador=?,telefone=?,pagamento=?,vendedor_id=?,vendido_em=?,vendido_por_usuario_id=NULL WHERE id=?""",
                         (mov.get('comprador'),mov.get('telefone'),mov.get('pagamento'),mov.get('vendedor_id') or card['vendedor_id'],agora,card['id']))
    elif tipo=='cancelamento':
        conn.execute("UPDATE cartelas SET status='disponivel',comprador=NULL,telefone=NULL,pagamento=NULL,vendido_em=NULL,vendido_por_usuario_id=NULL WHERE id=?",(card['id'],))
    else:
        return False, f'Tipo não suportado: {tipo}'
    existente=conn.execute("SELECT id FROM movimentacoes_vendas WHERE sync_uuid=?",(uid,)).fetchone()
    if not existente:
        conn.execute("""INSERT INTO movimentacoes_vendas (evento_id,cartela_id,numero,tipo,comprador,telefone,pagamento,vendedor_id,usuario_id,motivo,criado_em,origem,sync_uuid,sync_enviado)
                     VALUES (?,?,?,?,?,?,?,?,NULL,?,?,?,?,1)""",
                     (eid,card['id'],numero,tipo,mov.get('comprador'),mov.get('telefone'),mov.get('pagamento'),mov.get('vendedor_id'),mov.get('motivo'),agora,origem,uid))
    conn.execute("INSERT OR IGNORE INTO sync_recebidos (uuid,origem,recebido_em) VALUES (?,?,?)",(uid,origem,datetime.now().isoformat(timespec='seconds')))
    return True, 'ok'


def _sync_push_movimentos(remote, token):
    conn=get_db()
    rows=conn.execute("SELECT * FROM movimentacoes_vendas WHERE COALESCE(sync_enviado,0)=0 ORDER BY id LIMIT 500").fetchall()
    if not rows:
        conn.close(); return 0, []
    movimentos=[]
    for r in rows:
        uid=_garantir_uuid_movimento(conn,r['id'])
        d=dict(r); d['sync_uuid']=uid; movimentos.append(d)
    conn.commit(); conn.close()
    resp=_http_json('POST',remote+'/api/sync/movements',{'movimentos':movimentos},token)
    aceitos=set(resp.get('accepted') or [])
    conflitos=resp.get('conflicts') or []
    if aceitos:
        conn=get_db(); conn.executemany("UPDATE movimentacoes_vendas SET sync_enviado=1 WHERE sync_uuid=?",[(u,) for u in aceitos]); conn.commit(); conn.close()
    return len(aceitos), conflitos


def _sync_pull_eventos(remote, token):
    conn=get_db(); cfg=conn.execute("SELECT * FROM sync_config WHERE id=1").fetchone(); since=int(cfg['last_pull_seq'] or 0); conn.close()
    resp=_http_json('GET',f"{remote}/api/sync/events?since={since}",None,token)
    eventos=resp.get('events') or []; max_seq=since; conflitos=[]; aplicados=0
    conn=get_db()
    for ev in eventos:
        seq=int(ev.get('seq') or 0); max_seq=max(max_seq,seq)
        payload=ev.get('payload') or {}
        if isinstance(payload,str):
            try: payload=json.loads(payload)
            except Exception: payload={}
        payload['sync_uuid']=ev.get('uuid')
        payload['evento_id']=ev.get('evento_id') or payload.get('evento_id')
        payload['numero']=ev.get('numero') or payload.get('numero')
        payload['tipo']=ev.get('tipo') or payload.get('tipo')
        ok,msg=_aplicar_movimento_recebido(conn,payload,ev.get('origem') or 'nuvem')
        if ok: aplicados+=1
        else: conflitos.append(msg)
    conn.execute("UPDATE sync_config SET last_pull_seq=? WHERE id=1",(max_seq,)); conn.commit(); conn.close()
    return aplicados, conflitos


def sync_cycle(full=False):
    """Sincroniza computador local ↔ nuvem. Não interrompe a operação local se a internet cair."""
    if BINGO_MODE != 'local':
        return {'ok':False,'message':'Sincronização ativa somente na instalação local.'}
    cfg=_sync_cfg()
    if not cfg or not cfg['enabled']:
        return {'ok':False,'message':'Sincronização online ainda não está habilitada.'}
    remote=(cfg['remote_url'] or '').strip().rstrip('/'); token=(cfg['token'] or '').strip()
    if not remote or not token:
        return {'ok':False,'message':'Informe a URL do servidor online e a chave de sincronização.'}
    try:
        health=_http_json('GET',remote+'/api/sync/health',None,token,timeout=7)
        if not health.get('ok'):
            raise RuntimeError('Servidor online não respondeu corretamente.')
        catalog=False
        last_cat=cfg['last_catalog_em']
        if full or not last_cat:
            catalog=True
        else:
            try:
                dt=datetime.fromisoformat(last_cat); catalog=(datetime.now()-dt).total_seconds()>=300
            except Exception:
                catalog=True
        # O catálogo sobe primeiro. Assim, uma cartela recém-criada já existe na nuvem
        # antes de enviarmos uma venda local referente a ela. Vendas já feitas na nuvem
        # são preservadas pelo aplicador de snapshot.
        if catalog:
            resp=_http_json('POST',remote+'/api/sync/snapshot',_snapshot_local(),token,timeout=30)
            if not resp.get('ok'): raise RuntimeError(resp.get('message') or 'Falha ao enviar catálogo.')
        enviados, conflitos_push=_sync_push_movimentos(remote,token)
        recebidos, conflitos_pull=_sync_pull_eventos(remote,token)
        conflitos=(conflitos_push or [])+(conflitos_pull or [])
        msg=f"Online. {enviados} movimento(s) enviados; {recebidos} recebido(s)."
        if conflitos: msg += f" {len(conflitos)} conflito(s): " + '; '.join(str(x) for x in conflitos[:3])
        _sync_atualizar_status(not conflitos,msg,catalog=catalog)
        return {'ok':not conflitos,'message':msg,'conflicts':conflitos,'sent':enviados,'received':recebidos}
    except Exception as exc:
        msg=f"OFFLINE / sem sincronização: {exc}"
        _sync_atualizar_status(False,msg)
        return {'ok':False,'message':msg,'conflicts':[]}


def _sync_worker_loop():
    while True:
        try:
            cfg=_sync_cfg(); intervalo=max(30,min(int(cfg['auto_interval'] or 60),3600)) if cfg else 60
            if cfg and cfg['enabled']:
                sync_cycle(full=False)
        except Exception:
            intervalo=60
        time.sleep(intervalo)


def start_sync_worker():
    global SYNC_WORKER_STARTED
    if BINGO_MODE!='local' or SYNC_WORKER_STARTED:
        return
    SYNC_WORKER_STARTED=True
    threading.Thread(target=_sync_worker_loop,daemon=True,name='bingo-sync-worker').start()


def criar_backup_fechamento(evento_id):
    pasta=Path(__file__).with_name('backups'); pasta.mkdir(exist_ok=True)
    destino=pasta/f"pre_sorteio_evento_{evento_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    origem=sqlite3.connect(DB_PATH); alvo=sqlite3.connect(destino)
    try:
        origem.backup(alvo)
    finally:
        alvo.close(); origem.close()
    return destino


def rodada_ativa(conn, evento_id):
    return conn.execute("SELECT * FROM rodadas WHERE evento_id=? AND status='ativa' ORDER BY ordem,id LIMIT 1", (evento_id,)).fetchone()


def padrao_label(padrao):
    return {
        'linha': '1 linha horizontal',
        'duas_linhas': '2 linhas horizontais',
        'quatro_cantos': '4 cantos',
        'x': 'X completo',
        'cartela_cheia': 'Cartela cheia',
    }.get(padrao, padrao.replace('_',' ').title())


def _marcado(n, sorteados):
    return n == 0 or n in sorteados


def cartela_atende_padrao(grade, sorteados, padrao):
    sorteados = set(sorteados)
    linhas_h = [row for row in grade]
    linhas_completas = sum(1 for row in linhas_h if all(_marcado(n, sorteados) for n in row))
    if padrao == 'linha':
        return linhas_completas >= 1
    if padrao == 'duas_linhas':
        return linhas_completas >= 2
    if padrao == 'quatro_cantos':
        return all(_marcado(grade[r][c], sorteados) for r,c in [(0,0),(0,4),(4,0),(4,4)])
    if padrao == 'x':
        diag1 = all(_marcado(grade[i][i], sorteados) for i in range(5))
        diag2 = all(_marcado(grade[i][4-i], sorteados) for i in range(5))
        return diag1 and diag2
    return cartela_cheia(grade, sorteados)


def cartela_status_rodada(card, sorteados, rodada):
    if not rodada:
        return False
    return cartela_atende_padrao(json.loads(card['numeros']), sorteados, rodada['padrao'])


def cartela_proximidade_padrao(grade, sorteados, padrao):
    """Retorna (quantidade_faltante, numeros_faltantes) para o caminho mais curto até o padrão da rodada."""
    sorteados = set(sorteados)

    def faltantes_valores(valores):
        return sorted({n for n in valores if n != 0 and n not in sorteados})

    if padrao == 'linha':
        candidatos = [faltantes_valores(row) for row in grade]
    elif padrao == 'duas_linhas':
        faltas_linhas = [set(faltantes_valores(row)) for row in grade]
        candidatos = []
        for i in range(len(faltas_linhas)):
            for j in range(i + 1, len(faltas_linhas)):
                candidatos.append(sorted(faltas_linhas[i] | faltas_linhas[j]))
    elif padrao == 'quatro_cantos':
        candidatos = [faltantes_valores([grade[0][0], grade[0][4], grade[4][0], grade[4][4]])]
    elif padrao == 'x':
        valores = [grade[i][i] for i in range(5)] + [grade[i][4-i] for i in range(5)]
        candidatos = [faltantes_valores(valores)]
    else:
        candidatos = [faltantes_valores([n for row in grade for n in row])]

    melhor = min(candidatos, key=lambda itens: (len(itens), itens)) if candidatos else []
    return len(melhor), melhor


def detectar_proximas_cartelas(conn, evento_id, sorteados, rodada, limite_por_grupo=None):
    grupos = {5: [], 4: [], 3: [], 2: [], 1: []}
    if not rodada:
        return grupos
    cards = conn.execute("""SELECT c.*,v.nome vendedor,l.codigo lote
        FROM cartelas c
        LEFT JOIN vendedores v ON v.id=c.vendedor_id
        LEFT JOIN lotes l ON l.id=c.lote_id
        WHERE c.evento_id=? AND c.status='vendida'
        ORDER BY c.numero""", (evento_id,)).fetchall()
    for card in cards:
        grade = json.loads(card['numeros'])
        qtd, faltantes = cartela_proximidade_padrao(grade, sorteados, rodada['padrao'])
        if qtd in grupos:
            grupos[qtd].append({
                'numero': card['numero'],
                'comprador': card['comprador'] or '',
                'telefone': card['telefone'] or '',
                'vendedor': card['vendedor'] or '',
                'lote': card['lote'] or '',
                'faltantes': faltantes,
            })
    if limite_por_grupo:
        return {k: v[:limite_por_grupo] for k, v in grupos.items()}
    return grupos


def gerar_cartela_75():
    colunas = [
        random.sample(range(1, 16), 5),
        random.sample(range(16, 31), 5),
        random.sample(range(31, 46), 5),
        random.sample(range(46, 61), 5),
        random.sample(range(61, 76), 5),
    ]
    grade = []
    for linha in range(5):
        grade.append([colunas[col][linha] for col in range(5)])
    grade[2][2] = 0
    return grade


def linhas_cartela(grade):
    linhas = [row[:] for row in grade]
    for c in range(5):
        linhas.append([grade[r][c] for r in range(5)])
    return linhas


def cartela_tem_linha(grade, sorteados):
    sorteados = set(sorteados)
    for linha in linhas_cartela(grade):
        if all(n == 0 or n in sorteados for n in linha):
            return True
    return False


def cartela_cheia(grade, sorteados):
    sorteados = set(sorteados)
    return all(n == 0 or n in sorteados for row in grade for n in row)


def letra_numero(n):
    if 1 <= n <= 15: return 'B'
    if 16 <= n <= 30: return 'I'
    if 31 <= n <= 45: return 'N'
    if 46 <= n <= 60: return 'G'
    if 61 <= n <= 75: return 'O'
    return ''


def qr_payload(evento, numero):
    return f"{base_url_publico(evento)}/m/{evento['id']}/{numero}"


def qr_image(payload):
    qr = qrcode.QRCode(version=2, box_size=7, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color='black', back_color='white').convert('RGB')



def evento_cartela_campo(evento, campo, padrao=''):
    try:
        valor = evento[campo] if campo in evento.keys() else None
    except Exception:
        valor = None
    return (valor or padrao).strip() if isinstance((valor or padrao), str) else (valor or padrao)


def premios_cartela_evento(evento):
    raw = evento_cartela_campo(evento, 'premios_cartela', '\n'.join(DEFAULT_CARD_PRIZES))
    itens = [linha.strip() for linha in str(raw).splitlines() if linha.strip()]
    return (itens + DEFAULT_CARD_PRIZES)[:5]


def data_cartela_formatada(valor):
    if not valor:
        return 'Data a definir'
    try:
        return datetime.strptime(valor, '%Y-%m-%d').strftime('%d/%m/%Y')
    except Exception:
        return str(valor)


def _fit_font(texto, fonte, max_size, min_size, largura):
    tamanho = max_size
    while tamanho > min_size and pdfmetrics.stringWidth(str(texto), fonte, tamanho) > largura:
        tamanho -= .3
    return max(tamanho, min_size)


def _wrap_pdf(texto, fonte, tamanho, largura):
    palavras = str(texto).split()
    if not palavras:
        return ['']
    linhas=[]; atual=''
    for palavra in palavras:
        teste = palavra if not atual else atual + ' ' + palavra
        if pdfmetrics.stringWidth(teste, fonte, tamanho) <= largura:
            atual=teste
        else:
            if atual: linhas.append(atual)
            atual=palavra
    if atual: linhas.append(atual)
    return linhas


def _draw_logo(c, x, y, w, h):
    if LOGO_PATH.exists():
        try:
            c.drawImage(str(LOGO_PATH), x, y, w, h, preserveAspectRatio=True, anchor='c', mask='auto')
            return True
        except Exception:
            pass
    return False


def _card_value(card, key, default=None):
    try:
        return card[key]
    except Exception:
        if isinstance(card, dict):
            return card.get(key, default)
        return default


def _card_lote_codigo(card):
    valor = _card_value(card, 'lote_codigo')
    if valor not in (None, ''):
        return str(valor)
    valor = _card_value(card, 'lote')
    if valor not in (None, ''):
        return str(valor)
    valor = _card_value(card, 'lote_id')
    return str(valor) if valor not in (None, '') else ''


def _template_box(x, y, w, h, left, top, width, height):
    """Converte pixels do template 1024x1536 para coordenadas do PDF."""
    tpl_w, tpl_h = 1024.0, 1536.0
    bx = x + (left / tpl_w) * w
    by = y + h - ((top + height) / tpl_h) * h
    bw = (width / tpl_w) * w
    bh = (height / tpl_h) * h
    return bx, by, bw, bh


def _draw_centered(c, box, text, font='Helvetica-Bold', size=16, color=CARD_NAVY):
    bx, by, bw, bh = box
    c.setFillColor(color)
    c.setFont(font, size)
    c.drawCentredString(bx + bw/2, by + bh/2 - size*0.34, str(text))


def draw_card_pdf(c, evento, card, x, y, w, h):
    """
    TEMPLATE OFICIAL: a cartela NÃO é desenhada pelo código.
    O PNG anexado pelo usuário é impresso integralmente como fundo.
    O sistema só sobrepõe números, número da cartela, lote e QR Code.
    """
    if not CARD_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f'Template oficial não encontrado: {CARD_TEMPLATE_PATH}')

    # O PNG oficial ocupa 100% da área da cartela.
    c.drawImage(str(CARD_TEMPLATE_PATH), x, y, w, h,
                preserveAspectRatio=False, mask='auto')

    grade = json.loads(card['numeros']) if isinstance(card['numeros'], str) else card['numeros']

    # Células brancas do template original (pixels na imagem 1024x1536).
    # Limites externos medidos diretamente no PNG enviado.
    grid_left = 46.0
    grid_top = 544.0
    grid_right = 667.0
    grid_bottom = 1137.0
    cell_w = (grid_right - grid_left) / 5.0
    cell_h = (grid_bottom - grid_top) / 5.0

    number_size = max(8, min(21, h * 0.030))
    for row in range(5):
        for col in range(5):
            value = grade[row][col]
            if value == 0:  # centro GRÁTIS já faz parte do PNG e não deve ser coberto
                continue
            cell = _template_box(
                x, y, w, h,
                grid_left + col * cell_w,
                grid_top + row * cell_h,
                cell_w,
                cell_h,
            )
            _draw_centered(c, cell, value, size=number_size, color=CARD_NAVY)

    numero = int(_card_value(card, 'numero', 0))
    numero_box = _template_box(x, y, w, h, 243, 1332, 198, 47)
    _draw_centered(c, numero_box, f'{numero:04d}', size=max(7, min(14, h * 0.018)), color=TEXT)

    lote = _card_lote_codigo(card)
    if lote:
        lote_box = _template_box(x, y, w, h, 548, 1332, 150, 47)
        _draw_centered(c, lote_box, lote, size=max(7, min(13, h * 0.017)), color=TEXT)

    qr = qr_image(qr_payload(evento, numero))
    qr_buf = BytesIO()
    qr.save(qr_buf, format='PNG')
    qr_buf.seek(0)
    qr_area = _template_box(x, y, w, h, 744, 1324, 250, 130)
    qx, qy, qw, qh = qr_area
    qsize = min(qw * 0.58, qh * 0.72)
    c.drawImage(ImageReader(qr_buf), qx + (qw-qsize)/2, qy + (qh-qsize)/2 - 1.0*mm,
                qsize, qsize, mask='auto')


def draw_card_pdf_compacto(c, evento, card, x, y, w, h):
    # Compatibilidade com links antigos: agora também usa obrigatoriamente o PNG oficial.
    draw_card_pdf(c, evento, card, x, y, w, h)


# ===== V5: usuários, permissões, auditoria, estornos e caixa =====
PERFIL_LABELS = {
    'admin': 'Administrador',
    'coordenador': 'Coordenação',
    'caixa': 'Caixa',
    'operador': 'Operador do bingo',
    'auditor': 'Consulta / Auditoria',
}

PERMISSOES = {
    'admin': {'*'},
    'coordenador': {'dashboard','eventos','operacao','cartelas','estoque','vendedores','distribuicao','vendas','busca','financeiro','caixa','rodadas','celulares','sorteio','estatisticas','relatorios','auditoria','backups','sincronizacao'},
    'caixa': {'dashboard','vendas','busca','financeiro','caixa','estatisticas','relatorios'},
    'operador': {'dashboard','rodadas','sorteio','estatisticas','relatorios'},
    'auditor': {'dashboard','busca','estatisticas','relatorios','auditoria'},
}

ENDPOINT_PERMISSAO = {
    'dashboard':'dashboard',
    'eventos':'eventos','evento_ativar':'eventos','evento':'eventos','evento_editar':'eventos','evento_excluir':'eventos',
    'operacao':'operacao','evento_status':'operacao',
    'cartelas':'cartelas','cartelas_pdf':'cartelas','cartela_qr':'cartelas',
    'estoque':'estoque','lote_pdf':'estoque',
    'vendedores':'vendedores','distribuicao':'distribuicao',
    'vendas':'vendas','venda_cancelar':'vendas','comprovante_venda':'vendas',
    'busca':'busca',
    'financeiro':'financeiro','comprovante_acerto':'financeiro','caixa':'caixa',
    'estatisticas':'estatisticas',
    'rodadas':'rodadas','rodada_acao':'rodadas',
    'acesso_movel':'celulares','acesso_movel_qr':'celulares','vendedor_acesso_qr':'celulares',
    'sorteio':'sorteio','sorteio_evento_acao':'sorteio','conferir':'sorteio','confirmar_ganhador':'sorteio','reiniciar_sorteio':'sorteio',
    'relatorios':'relatorios','relatorio_pdf':'relatorios',
    'backups':'backups','backup_criar':'backups','backup_download':'backups','backup_restaurar':'backups','backup_upload':'backups',
    'usuarios':'usuarios','usuario_acao':'usuarios',
    'auditoria':'auditoria',
    'sincronizacao':'sincronizacao','sincronizacao_acao':'sincronizacao',
}

PUBLIC_ENDPOINTS = {
    'login','logout','static','health','telao','api_estado_sorteio',
    'mobile_home','mobile_vendedor','mobile_selecionar','mobile_sair','mobile_abrir_cartela','mobile_cartela','mobile_comprovante',
    'api_sync_health','api_sync_snapshot','api_sync_movements','api_sync_events',
}


def perfil_label(perfil):
    return PERFIL_LABELS.get(perfil, perfil.title() if perfil else 'Usuário')


def pode(permissao):
    user = getattr(g, 'usuario', None)
    if not user:
        return False
    permissoes = PERMISSOES.get(user['perfil'], set())
    return '*' in permissoes or permissao in permissoes


def evento_atual_id_safe():
    try:
        conn = get_db(); evento = evento_ativo(conn); eid = evento['id'] if evento else None; conn.close(); return eid
    except Exception:
        return None


def gravar_auditoria(acao, entidade='', detalhes='', usuario_id=None, usuario_nome=None, evento_id=None, ip=None):
    try:
        conn = get_db()
        conn.execute("""INSERT INTO auditoria (evento_id,usuario_id,usuario_nome,acao,entidade,detalhes,ip,criado_em)
            VALUES (?,?,?,?,?,?,?,?)""", (evento_id, usuario_id, usuario_nome, acao, entidade, detalhes, ip, datetime.now().isoformat(timespec='seconds')))
        conn.commit(); conn.close()
    except Exception:
        pass


def usuario_atual_id():
    return session.get('usuario_id')


@app.context_processor
def _v5_context():
    sync_resumo=None
    try:
        sync_resumo=_sync_cfg()
    except Exception:
        sync_resumo=None
    return {'usuario_atual': getattr(g, 'usuario', None), 'pode': pode, 'perfil_label': perfil_label,
            'bingo_mode': BINGO_MODE, 'system_build': SYSTEM_BUILD, 'sync_resumo': sync_resumo}


@app.before_request
def _v5_auth():
    g.usuario = None
    uid = session.get('usuario_id')
    if uid:
        conn = get_db(); user = conn.execute("SELECT * FROM usuarios WHERE id=? AND ativo=1", (uid,)).fetchone(); conn.close()
        if user:
            g.usuario = user
        else:
            session.pop('usuario_id', None)

    if BINGO_MODE=='cloud' and request.endpoint in {'login','logout'}:
        return redirect(url_for('mobile_home'))
    if BINGO_MODE=='cloud' and request.endpoint not in PUBLIC_ENDPOINTS and request.endpoint is not None:
        return jsonify({'ok':False,'message':'Painel administrativo desativado no nó online. Use o computador local.'}),404
    if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
        return None
    if not g.usuario:
        return redirect(url_for('login', next=request.path))
    if g.usuario['obrigar_troca'] and request.endpoint not in {'minha_senha','logout'}:
        flash('Por segurança, altere a senha temporária antes de continuar.', 'warning')
        return redirect(url_for('minha_senha'))
    permissao = ENDPOINT_PERMISSAO.get(request.endpoint)
    if permissao and not pode(permissao):
        flash('Seu perfil não possui permissão para acessar esta área.', 'danger')
        return redirect(url_for('dashboard'))
    return None


@app.after_request
def _v5_auditar_posts(response):
    if request.method == 'POST' and request.endpoint not in {'login'} and response.status_code < 400 and (getattr(g, 'usuario', None) or request.endpoint in {'mobile_selecionar','mobile_abrir_cartela','mobile_cartela'}):
        dados = {}
        for k,v in request.form.items():
            if 'senha' in k.lower() or 'password' in k.lower():
                dados[k] = '***'
            else:
                dados[k] = v[:180] if isinstance(v,str) else str(v)[:180]
        ator_id = session.get('usuario_id')
        ator_nome = None
        if getattr(g, 'usuario', None):
            ator_nome = g.usuario['nome']
        elif session.get('vendedor_id'):
            try:
                conn=get_db(); vend=conn.execute("SELECT nome FROM vendedores WHERE id=?", (session['vendedor_id'],)).fetchone(); conn.close()
                ator_nome = f"Vendedor: {vend['nome']}" if vend else 'Vendedor móvel'
            except Exception:
                ator_nome = 'Vendedor móvel'
        else:
            ator_nome = 'Acesso móvel/QR'
        evento_id = None
        if request.view_args and request.view_args.get('evento_id'):
            evento_id = request.view_args.get('evento_id')
        if not evento_id:
            evento_id = evento_atual_id_safe()
        gravar_auditoria(request.endpoint or 'post', request.path, json.dumps(dados, ensure_ascii=False), ator_id, ator_nome, evento_id, request.remote_addr)
    return response


init_db()


@app.before_request
def _ensure_db():
    # Bloqueia alterações operacionais depois do encerramento oficial do evento.
    if request.method != 'POST':
        return None
    liberados = {
        'evento', 'eventos', 'evento_ativar', 'evento_editar', 'evento_excluir', 'evento_status', 'sorteio_evento_acao',
        'backup_criar', 'backup_restaurar', 'backup_upload'
    }
    if request.endpoint in liberados:
        return None
    mutacoes = {
        'cartelas', 'estoque', 'vendedores', 'distribuicao', 'vendas', 'venda_cancelar', 'financeiro', 'caixa',
        'rodadas', 'rodada_acao', 'mobile_cartela', 'sorteio', 'conferir',
        'confirmar_ganhador', 'reiniciar_sorteio'
    }
    if request.endpoint not in mutacoes:
        return None
    conn = get_db()
    if request.endpoint == 'mobile_cartela' and request.view_args and request.view_args.get('evento_id'):
        evento = conn.execute("SELECT * FROM eventos WHERE id=?", (request.view_args['evento_id'],)).fetchone()
    else:
        evento = evento_ativo(conn)
    conn.close()
    if evento_encerrado(evento):
        flash('Este evento está encerrado. Reabra-o em Operação para fazer alterações.', 'warning')
        return redirect(request.referrer or url_for('dashboard'))
    return None


@app.route('/health')
def health():
    return jsonify({
        'ok': True,
        'build': SYSTEM_BUILD,
        'port': SYSTEM_PORT,
        'template': CARD_TEMPLATE_PATH.name,
        'template_exists': CARD_TEMPLATE_PATH.exists(),
        'mode': BINGO_MODE,
    })



@app.route('/api/sync/health')
def api_sync_health():
    if not _sync_token_valido():
        return jsonify({'ok':False,'error':'unauthorized'}),401
    return jsonify({'ok':True,'build':SYSTEM_BUILD,'mode':BINGO_MODE,'time':datetime.now().isoformat(timespec='seconds')})


@app.route('/api/sync/snapshot', methods=['POST'])
def api_sync_snapshot():
    if not _sync_token_valido():
        return jsonify({'ok':False,'error':'unauthorized'}),401
    if BINGO_MODE != 'cloud':
        return jsonify({'ok':False,'message':'Este endpoint deve ser usado no servidor online.'}),409
    try:
        resultado=_cloud_aplicar_snapshot(request.get_json(silent=True) or {})
        return jsonify(resultado), (200 if resultado.get('ok') else 400)
    except Exception as exc:
        return jsonify({'ok':False,'message':str(exc)}),500


@app.route('/api/sync/movements', methods=['POST'])
def api_sync_movements():
    if not _sync_token_valido():
        return jsonify({'ok':False,'error':'unauthorized'}),401
    if BINGO_MODE != 'cloud':
        return jsonify({'ok':False,'message':'Este endpoint deve ser usado no servidor online.'}),409
    data=request.get_json(silent=True) or {}; movimentos=data.get('movimentos') or []
    accepted=[]; conflicts=[]; conn=get_db()
    try:
        for mov in movimentos[:1000]:
            uid=(mov.get('sync_uuid') or '').strip()
            if not uid: continue
            if conn.execute("SELECT 1 FROM sync_recebidos WHERE uuid=?",(uid,)).fetchone():
                accepted.append(uid); continue
            ok,msg=_aplicar_movimento_recebido(conn,mov,'local')
            if ok:
                _registrar_evento_sync(conn,uid,mov.get('tipo') or 'venda',mov.get('evento_id'),mov.get('numero'),mov,'local')
                accepted.append(uid)
            else:
                conflicts.append({'uuid':uid,'numero':mov.get('numero'),'message':msg})
        conn.commit()
    finally:
        conn.close()
    return jsonify({'ok':not conflicts,'accepted':accepted,'conflicts':conflicts})


@app.route('/api/sync/events')
def api_sync_events():
    if not _sync_token_valido():
        return jsonify({'ok':False,'error':'unauthorized'}),401
    if BINGO_MODE != 'cloud':
        return jsonify({'ok':False,'message':'Este endpoint deve ser usado no servidor online.'}),409
    try: since=max(0,int(request.args.get('since','0')))
    except ValueError: since=0
    conn=get_db(); rows=conn.execute("SELECT * FROM sync_eventos WHERE seq>? ORDER BY seq LIMIT 1000",(since,)).fetchall(); conn.close()
    eventos=[]
    for r in rows:
        d=dict(r)
        try: d['payload']=json.loads(d['payload'])
        except Exception: d['payload']={}
        eventos.append(d)
    return jsonify({'ok':True,'events':eventos,'last_seq':eventos[-1]['seq'] if eventos else since})


@app.route('/sincronizacao')
def sincronizacao():
    conn=get_db(); evento=evento_ativo(conn); cfg=conn.execute("SELECT * FROM sync_config WHERE id=1").fetchone()
    pendentes=conn.execute("SELECT COUNT(*) c FROM movimentacoes_vendas WHERE COALESCE(sync_enviado,0)=0").fetchone()['c']
    total=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=?",(evento['id'],)).fetchone()['c'] if evento else 0
    vendidas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='vendida'",(evento['id'],)).fetchone()['c'] if evento else 0
    conn.close()
    return render_template('sincronizacao.html',evento=evento,cfg=cfg,mode=BINGO_MODE,pendentes=pendentes,total=total,vendidas=vendidas,remote=_remote_base_url())


@app.route('/sincronizacao/acao', methods=['POST'])
def sincronizacao_acao():
    acao=request.form.get('acao','')
    if BINGO_MODE!='local':
        flash('As configurações de sincronização são feitas no computador local.','warning'); return redirect(url_for('sincronizacao'))
    if acao=='configurar':
        remote=request.form.get('remote_url','').strip().rstrip('/'); token=request.form.get('token','').strip()
        try: intervalo=max(30,min(int(request.form.get('auto_interval','60')),3600))
        except ValueError: intervalo=60
        enabled=1 if request.form.get('enabled')=='1' else 0
        conn=get_db(); atual=conn.execute("SELECT token FROM sync_config WHERE id=1").fetchone(); token_final=token or (atual['token'] if atual else '')
        conn.execute("UPDATE sync_config SET remote_url=?,token=?,enabled=?,auto_interval=? WHERE id=1",(remote,token_final,enabled,intervalo)); conn.commit(); conn.close()
        flash('Configuração online salva.','success');
        if enabled: start_sync_worker()
    elif acao=='sincronizar':
        r=sync_cycle(full=True); flash(r['message'],'success' if r.get('ok') else 'warning')
    elif acao=='fechar_vendas':
        r=sync_cycle(full=True)
        force=request.form.get('forcar')=='1'
        if not r.get('ok') and not force:
            flash('Não fechei as vendas porque a nuvem não foi sincronizada. Se a internet realmente acabou, marque a opção de contingência para usar a última cópia local.','danger')
            return redirect(url_for('sincronizacao'))
        conn=get_db(); evento=evento_ativo(conn); backup=criar_backup_fechamento(evento['id']); agora=datetime.now().isoformat(timespec='seconds')
        conn.execute("UPDATE eventos SET vendas_fechadas_em=?,vendas_fechadas_por=? WHERE id=?",(agora,usuario_atual_id(),evento['id'])); conn.commit(); conn.close()
        if r.get('ok'):
            r2=sync_cycle(full=True)
            r3=sync_cycle(full=False)
            combinado=(r2.get('message','')+' '+r3.get('message','')).strip()
            flash(f'Vendas encerradas e backup criado: {backup.name}. '+combinado,'success' if r2.get('ok') and r3.get('ok') else 'warning')
        else:
            flash(f'MODO CONTINGÊNCIA: vendas fechadas apenas no computador local usando a última sincronização. Backup: {backup.name}.','warning')
    elif acao=='reabrir_vendas':
        conn=get_db(); evento=evento_ativo(conn); conn.execute("UPDATE eventos SET vendas_fechadas_em=NULL,vendas_fechadas_por=NULL WHERE id=?",(evento['id'],)); conn.commit(); conn.close()
        r=sync_cycle(full=True); flash('Vendas reabertas. '+r.get('message',''),'success' if r.get('ok') else 'warning')
    return redirect(url_for('sincronizacao'))


@app.route('/')
def dashboard():
    conn = get_db(); evento = evento_ativo(conn); eid = evento['id']
    total = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=?", (eid,)).fetchone()['c']
    vendidas = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='vendida'", (eid,)).fetchone()['c']
    distribuidas = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id IS NOT NULL", (eid,)).fetchone()['c']
    vendedores = conn.execute("SELECT COUNT(*) c FROM vendedores").fetchone()['c']
    sorteados = conn.execute("SELECT COUNT(*) c FROM sorteios WHERE evento_id=?", (eid,)).fetchone()['c']
    arrecadado = vendidas * float(evento['valor_cartela'])
    impressas = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND impressa_em IS NOT NULL", (eid,)).fetchone()['c']
    inutilizadas = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='inutilizada'", (eid,)).fetchone()['c']
    lotes = conn.execute("SELECT COUNT(*) c FROM lotes WHERE evento_id=?", (eid,)).fetchone()['c']
    top_vendedor = conn.execute("""SELECT v.nome,COUNT(*) qtd FROM cartelas c JOIN vendedores v ON v.id=c.vendedor_id
        WHERE c.evento_id=? AND c.status='vendida' GROUP BY v.id ORDER BY qtd DESC,v.nome LIMIT 1""", (eid,)).fetchone()
    ultimos = conn.execute("SELECT numero FROM sorteios WHERE evento_id=? ORDER BY ordem DESC LIMIT 8", (eid,)).fetchall()
    conn.close()
    return render_template('dashboard.html', evento=evento, total=total, vendidas=vendidas,
                           disponiveis=max(total-vendidas-inutilizadas,0), distribuidas=distribuidas, vendedores=vendedores,
                           sorteados=sorteados, arrecadado=arrecadado, impressas=impressas, inutilizadas=inutilizadas, lotes=lotes,
                           taxa_venda=(vendidas/total*100 if total else 0), top_vendedor=top_vendedor,
                           ultimos=[r['numero'] for r in ultimos], status_evento_label=status_evento_label)


@app.route('/evento', methods=['GET','POST'])
def evento():
    conn = get_db(); evento = evento_ativo(conn)
    if request.method == 'POST':
        nome = request.form['nome'].strip(); data = request.form.get('data','')
        valor = float(request.form.get('valor_cartela','10').replace(',','.'))
        url_rede = request.form.get('url_rede','').strip().rstrip('/')
        organizador = request.form.get('organizador_cartela', COMMUNITY_NAME).strip() or COMMUNITY_NAME
        horario = request.form.get('horario_cartela', DEFAULT_CARD_TIME).strip() or DEFAULT_CARD_TIME
        premios = request.form.get('premios_cartela','').strip() or '\n'.join(DEFAULT_CARD_PRIZES)
        conn.execute("UPDATE eventos SET nome=?, data=?, valor_cartela=?, url_rede=?, organizador_cartela=?, horario_cartela=?, premios_cartela=? WHERE id=?",
                     (nome, data, valor, url_rede, organizador, horario, premios, evento['id']))
        conn.commit(); flash('Evento e modelo da cartela atualizados com sucesso.', 'success'); evento = evento_ativo(conn)
    conn.close(); return render_template('evento.html', evento=evento)


@app.route('/cartelas', methods=['GET','POST'])
def cartelas():
    conn = get_db(); evento = evento_ativo(conn)
    if request.method == 'POST':
        qtd = max(1, min(int(request.form.get('quantidade', 100)), 5000))
        existentes = conn.execute("SELECT numeros FROM cartelas WHERE evento_id=?", (evento['id'],)).fetchall()
        assinaturas = {r['numeros'] for r in existentes}
        inicio = conn.execute("SELECT COALESCE(MAX(numero),0)+1 n FROM cartelas WHERE evento_id=?", (evento['id'],)).fetchone()['n']
        geradas = 0; numero = inicio
        while geradas < qtd:
            grade = gerar_cartela_75(); assinatura = json.dumps(grade)
            if assinatura in assinaturas: continue
            conn.execute("INSERT INTO cartelas (evento_id, numero, numeros) VALUES (?, ?, ?)", (evento['id'], numero, assinatura))
            assinaturas.add(assinatura); numero += 1; geradas += 1
        conn.commit(); flash(f'{geradas} cartelas geradas.', 'success')

    cards = conn.execute("""
        SELECT c.*, v.nome vendedor FROM cartelas c
        LEFT JOIN vendedores v ON v.id=c.vendedor_id
        WHERE c.evento_id=? ORDER BY c.numero LIMIT 120
    """, (evento['id'],)).fetchall()
    total = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=?", (evento['id'],)).fetchone()['c']
    minimo = conn.execute("SELECT MIN(numero) n FROM cartelas WHERE evento_id=?", (evento['id'],)).fetchone()['n'] or 1
    maximo = conn.execute("SELECT MAX(numero) n FROM cartelas WHERE evento_id=?", (evento['id'],)).fetchone()['n'] or 1
    conn.close()
    parsed=[]
    for card in cards:
        d=dict(card); d['grade']=json.loads(d['numeros']); parsed.append(d)
    return render_template('cartelas.html', evento=evento, cartelas=parsed, total=total, minimo=minimo, maximo=maximo)


@app.route('/cartelas/pdf')
def cartelas_pdf():
    conn=get_db(); evento=evento_ativo(conn)
    try:
        inicio=int(request.args.get('inicio','1')); fim=int(request.args.get('fim',str(inicio+19)))
    except ValueError:
        inicio, fim = 1, 20
    if fim < inicio: inicio, fim = fim, inicio
    if fim-inicio+1 > 500: fim=inicio+499
    cards=conn.execute("""SELECT c.*, l.codigo AS lote_codigo
        FROM cartelas c
        LEFT JOIN lotes l ON l.id=c.lote_id
        WHERE c.evento_id=? AND c.numero BETWEEN ? AND ?
        ORDER BY c.numero""", (evento['id'], inicio, fim)).fetchall()
    conn.close()
    if not cards:
        flash('Nenhuma cartela encontrada nessa faixa.', 'warning'); return redirect(url_for('cartelas'))

    # O template tem proporção 2:3. Mantemos essa proporção para não deformar a arte.
    buf=BytesIO()
    page=landscape(A4); pdf=canvas.Canvas(buf,pagesize=page); pw,ph=page
    card_h=190*mm
    card_w=card_h*(1024/1536)
    gap=5*mm
    total_w=2*card_w+gap
    left=(pw-total_w)/2
    bottom=(ph-card_h)/2
    positions=[(left,bottom),(left+card_w+gap,bottom)]
    for i,card in enumerate(cards):
        if i>0 and i%2==0: pdf.showPage()
        x,y=positions[i%2]
        draw_card_pdf(pdf,evento,card,x,y,card_w,card_h)
    pdf.save(); buf.seek(0)
    return send_file(buf,mimetype='application/pdf',as_attachment=True,
                     download_name=f'cartelas_TEMPLATE_OFICIAL_{inicio:04d}_a_{fim:04d}.pdf')


@app.route('/cartela/<int:numero>/qr.png')
def cartela_qr(numero):
    conn=get_db(); evento=evento_ativo(conn)
    card=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=?", (evento['id'], numero)).fetchone(); conn.close()
    if not card: return Response(status=404)
    img=qr_image(qr_payload(evento, numero)); buf=BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return send_file(buf, mimetype='image/png')


@app.route('/vendedores', methods=['GET','POST'])
def vendedores():
    conn=get_db(); evento=evento_ativo(conn)
    if request.method=='POST':
        nome=request.form['nome'].strip(); telefone=request.form.get('telefone','').strip()
        if nome:
            usados={str(r['codigo_acesso']) for r in conn.execute("SELECT codigo_acesso FROM vendedores WHERE codigo_acesso IS NOT NULL").fetchall()}
            codigo=f"{secrets.randbelow(1000000):06d}"
            while codigo in usados: codigo=f"{secrets.randbelow(1000000):06d}"
            conn.execute("INSERT INTO vendedores (nome,telefone,acesso_token,codigo_acesso,online_ativo) VALUES (?,?,?,?,1)", (nome,telefone,secrets.token_urlsafe(24),codigo)); conn.commit(); flash(f'Vendedor cadastrado. Código de acesso online: {codigo}', 'success')
    rows=conn.execute("""
        SELECT v.*,
          SUM(CASE WHEN c.evento_id=? THEN 1 ELSE 0 END) recebidas,
          SUM(CASE WHEN c.evento_id=? AND c.status='vendida' THEN 1 ELSE 0 END) vendidas
        FROM vendedores v LEFT JOIN cartelas c ON c.vendedor_id=v.id
        GROUP BY v.id ORDER BY v.nome
    """, (evento['id'], evento['id'])).fetchall()
    conn.close(); return render_template('vendedores.html', vendedores=rows, evento=evento)


@app.route('/distribuicao', methods=['GET','POST'])
def distribuicao():
    conn=get_db(); evento=evento_ativo(conn)
    if request.method=='POST':
        acao=request.form.get('acao','atribuir'); vendedor_id=int(request.form['vendedor_id'])
        if acao=='devolver_todas':
            cur=conn.execute("UPDATE cartelas SET vendedor_id=NULL WHERE evento_id=? AND vendedor_id=? AND status='disponivel'", (evento['id'], vendedor_id))
            conn.commit(); flash(f'{cur.rowcount} cartelas não vendidas devolvidas ao estoque.', 'success')
        else:
            try:
                inicio=int(request.form['inicio']); fim=int(request.form['fim'])
            except ValueError:
                inicio=fim=0
            if fim<inicio: inicio,fim=fim,inicio
            if acao=='atribuir':
                cur=conn.execute("""UPDATE cartelas SET vendedor_id=?
                    WHERE evento_id=? AND numero BETWEEN ? AND ? AND status='disponivel'""",
                    (vendedor_id, evento['id'], inicio, fim))
                conn.commit(); flash(f'{cur.rowcount} cartelas distribuídas.', 'success')
            elif acao=='devolver_faixa':
                cur=conn.execute("""UPDATE cartelas SET vendedor_id=NULL
                    WHERE evento_id=? AND vendedor_id=? AND numero BETWEEN ? AND ? AND status='disponivel'""",
                    (evento['id'], vendedor_id, inicio, fim))
                conn.commit(); flash(f'{cur.rowcount} cartelas devolvidas.', 'success')
    vend=conn.execute("SELECT * FROM vendedores ORDER BY nome").fetchall()
    resumo=conn.execute("""
        SELECT v.id,v.nome,
          SUM(CASE WHEN c.evento_id=? THEN 1 ELSE 0 END) distribuidas,
          SUM(CASE WHEN c.evento_id=? AND c.status='vendida' THEN 1 ELSE 0 END) vendidas,
          MIN(CASE WHEN c.evento_id=? THEN c.numero END) inicio,
          MAX(CASE WHEN c.evento_id=? THEN c.numero END) fim
        FROM vendedores v LEFT JOIN cartelas c ON c.vendedor_id=v.id
        GROUP BY v.id ORDER BY v.nome
    """, (evento['id'],evento['id'],evento['id'],evento['id'])).fetchall()
    conn.close(); return render_template('distribuicao.html', evento=evento, vendedores=vend, resumo=resumo)


@app.route('/vendas', methods=['GET','POST'])
def vendas():
    conn=get_db(); evento=evento_ativo(conn)
    if request.method=='POST':
        if vendas_fechadas(evento):
            flash('As vendas estão encerradas para preparação do sorteio. Reabra-as em Sincronização se realmente precisar.','warning')
        else:
            try: numero=int(request.form['numero'])
            except ValueError: numero=0
            comprador=request.form.get('comprador','').strip(); telefone=request.form.get('telefone','').strip(); pagamento=request.form.get('pagamento','').strip()
            vendedor_form=request.form.get('vendedor_id') or None
            card=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=?", (evento['id'], numero)).fetchone()
            if not card: flash('Cartela não encontrada.', 'danger')
            elif card['status']=='vendida': flash(f'Cartela {numero:04d} já está vendida. Cancele a venda atual antes de registrar outra.', 'warning')
            elif card['status']!='disponivel': flash(f'Cartela {numero:04d} está {card["status"]} e não pode ser vendida.', 'warning')
            elif BINGO_MODE=='local' and card['vendedor_id'] is not None:
                flash(f'Cartela {numero:04d} está sob responsabilidade de um vendedor externo. Para evitar venda duplicada durante uma queda de internet, a baixa deve ser feita pelo vendedor responsável.', 'danger')
            else:
                vendedor_id=vendedor_form if vendedor_form is not None else card['vendedor_id']
                agora=datetime.now().isoformat(timespec='seconds'); uid=usuario_atual_id(); suid=_novo_sync_uuid()
                conn.execute("""UPDATE cartelas SET status='vendida', comprador=?, telefone=?, pagamento=?, vendedor_id=?, vendido_em=?, vendido_por_usuario_id=? WHERE id=?""",
                             (comprador, telefone, pagamento, vendedor_id, agora, uid, card['id']))
                conn.execute("""INSERT INTO movimentacoes_vendas (evento_id,cartela_id,numero,tipo,comprador,telefone,pagamento,vendedor_id,usuario_id,criado_em,origem,sync_uuid,sync_enviado)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (evento['id'],card['id'],numero,'venda',comprador,telefone,pagamento,vendedor_id,uid,agora,'painel',suid,0 if BINGO_MODE=='local' else 1))
                if BINGO_MODE=='cloud':
                    payload={'sync_uuid':suid,'evento_id':evento['id'],'numero':numero,'tipo':'venda','comprador':comprador,'telefone':telefone,'pagamento':pagamento,'vendedor_id':vendedor_id,'criado_em':agora}
                    _registrar_evento_sync(conn,suid,'venda',evento['id'],numero,payload,'nuvem')
                conn.commit(); flash(f'Cartela {numero:04d} marcada como vendida.', 'success')
    vend=conn.execute("SELECT * FROM vendedores ORDER BY nome").fetchall()
    recentes=conn.execute("""SELECT c.numero,c.comprador,c.pagamento,c.vendido_em,v.nome vendedor,
        (SELECT MAX(m.id) FROM movimentacoes_vendas m WHERE m.cartela_id=c.id AND m.tipo='venda') movimento_id
        FROM cartelas c LEFT JOIN vendedores v ON v.id=c.vendedor_id WHERE c.evento_id=? AND c.status='vendida'
        ORDER BY COALESCE(c.vendido_em,'' ) DESC,c.id DESC LIMIT 20""", (evento['id'],)).fetchall()
    historico=conn.execute("""SELECT m.*,v.nome vendedor,u.nome usuario_nome FROM movimentacoes_vendas m
        LEFT JOIN vendedores v ON v.id=m.vendedor_id LEFT JOIN usuarios u ON u.id=m.usuario_id
        WHERE m.evento_id=? ORDER BY m.id DESC LIMIT 40""", (evento['id'],)).fetchall()
    conn.close(); return render_template('vendas.html', evento=evento, vendedores=vend, recentes=recentes, historico=historico, vendas_fechadas=vendas_fechadas(evento))


@app.route('/financeiro', methods=['GET','POST'])
def financeiro():
    conn=get_db(); evento=evento_ativo(conn)
    if request.method=='POST':
        vendedor_id=int(request.form['vendedor_id'])
        try: valor=float(request.form['valor'].replace(',','.'))
        except ValueError: valor=0
        obs=request.form.get('observacao','').strip(); forma_pagamento=request.form.get('forma_pagamento','').strip()
        if valor>0:
            conn.execute("INSERT INTO acertos (evento_id,vendedor_id,valor,observacao,criado_em,forma_pagamento) VALUES (?,?,?,?,?,?)",
                         (evento['id'], vendedor_id, valor, obs, datetime.now().isoformat(timespec='seconds'),forma_pagamento))
            conn.commit(); flash('Recebimento registrado.', 'success')
    vendedores=conn.execute("SELECT * FROM vendedores ORDER BY nome").fetchall(); resumo=[]
    for v in vendedores:
        dist=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id=?", (evento['id'],v['id'])).fetchone()['c']
        sold=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id=? AND status='vendida'", (evento['id'],v['id'])).fetchone()['c']
        received=conn.execute("SELECT COALESCE(SUM(valor),0) s FROM acertos WHERE evento_id=? AND vendedor_id=?", (evento['id'],v['id'])).fetchone()['s']
        due=sold*float(evento['valor_cartela']); resumo.append({'id':v['id'],'nome':v['nome'],'distribuidas':dist,'vendidas':sold,'nao_vendidas':max(dist-sold,0),'devido':due,'recebido':received,'saldo':due-received})
    historico=conn.execute("""SELECT a.*,v.nome vendedor FROM acertos a JOIN vendedores v ON v.id=a.vendedor_id
        WHERE a.evento_id=? ORDER BY a.id DESC LIMIT 30""", (evento['id'],)).fetchall()
    total_devido=sum(x['devido'] for x in resumo); total_recebido=sum(x['recebido'] for x in resumo)
    conn.close(); return render_template('financeiro.html', evento=evento, resumo=resumo, historico=historico, total_devido=total_devido, total_recebido=total_recebido)



@app.route('/rodadas', methods=['GET','POST'])
def rodadas():
    conn=get_db(); evento=evento_ativo(conn)
    if request.method=='POST':
        nome=request.form.get('nome','').strip()
        padrao=request.form.get('padrao','cartela_cheia')
        try: premio=float(request.form.get('premio','0').replace(',','.'))
        except ValueError: premio=0
        if nome:
            ordem=conn.execute("SELECT COALESCE(MAX(ordem),0)+1 n FROM rodadas WHERE evento_id=?", (evento['id'],)).fetchone()['n']
            conn.execute("INSERT INTO rodadas (evento_id,nome,padrao,premio,ordem,status) VALUES (?,?,?,?,?,'pendente')", (evento['id'],nome,padrao,premio,ordem))
            conn.commit(); flash('Rodada criada.', 'success')
    rows=conn.execute("""SELECT r.*,
        (SELECT COUNT(*) FROM ganhadores g WHERE g.rodada_id=r.id AND g.confirmado=1) vencedores
        FROM rodadas r WHERE r.evento_id=? ORDER BY r.ordem,r.id""", (evento['id'],)).fetchall()
    conn.close(); return render_template('rodadas.html', evento=evento, rodadas=rows, padrao_label=padrao_label)


@app.route('/rodadas/<int:rodada_id>/acao', methods=['POST'])
def rodada_acao(rodada_id):
    conn=get_db(); evento=evento_ativo(conn)
    rodada=conn.execute("SELECT * FROM rodadas WHERE id=? AND evento_id=?", (rodada_id,evento['id'])).fetchone()
    if not rodada:
        conn.close(); flash('Rodada não encontrada.','danger'); return redirect(url_for('rodadas'))
    acao=request.form.get('acao')
    if acao in ('ativar','ativar_reset'):
        if rodada['status']=='finalizada':
            conn.close(); flash('Esta rodada já foi finalizada e não pode ser reativada.', 'warning'); return redirect(url_for('rodadas'))
        conn.execute("UPDATE rodadas SET status='pendente' WHERE evento_id=? AND status='ativa'", (evento['id'],))
        conn.execute("UPDATE rodadas SET status='ativa' WHERE id=?", (rodada_id,))
        if acao=='ativar_reset':
            conn.execute("DELETE FROM sorteios WHERE evento_id=?", (evento['id'],))
        conn.commit(); flash(f"Rodada ativa: {rodada['nome']}", 'success')
    elif acao=='finalizar':
        conn.execute("UPDATE rodadas SET status='finalizada' WHERE id=?", (rodada_id,)); conn.commit(); flash('Rodada finalizada.','success')
    elif acao=='excluir' and rodada['status']!='ativa':
        conn.execute("DELETE FROM rodadas WHERE id=?", (rodada_id,)); conn.commit(); flash('Rodada excluída.','warning')
    conn.close(); return redirect(url_for('rodadas'))


@app.route('/acesso-movel')
def acesso_movel():
    conn=get_db(); evento=evento_ativo(conn); vendedores=conn.execute("SELECT * FROM vendedores ORDER BY nome").fetchall(); conn.close()
    return render_template('acesso_movel.html', evento=evento, vendedores=vendedores, base_url=base_url_rede(evento), online_url=_remote_base_url(), ip=local_ip(), mode=BINGO_MODE)


@app.route('/acesso-movel/qr.png')
def acesso_movel_qr():
    conn=get_db(); evento=evento_ativo(conn); conn.close()
    img=qr_image(f"{base_url_rede(evento)}/mobile"); buf=BytesIO(); img.save(buf,format='PNG'); buf.seek(0)
    return send_file(buf,mimetype='image/png')


@app.route('/vendedor/<int:vendedor_id>/acesso.png')
def vendedor_acesso_qr(vendedor_id):
    conn=get_db(); evento=evento_ativo(conn); vendedor=conn.execute("SELECT * FROM vendedores WHERE id=?", (vendedor_id,)).fetchone(); conn.close()
    if not vendedor: return Response(status=404)
    destino=base_url_publico(evento)
    token=vendedor['acesso_token'] or ''
    img=qr_image(f"{destino}/mobile/vendedor/{vendedor_id}?token={token}"); buf=BytesIO(); img.save(buf,format='PNG'); buf.seek(0)
    return send_file(buf,mimetype='image/png')


@app.route('/mobile')
def mobile_home():
    conn=get_db(); evento=evento_ativo(conn); vendedores=conn.execute("SELECT * FROM vendedores WHERE online_ativo=1 ORDER BY nome").fetchall() if BINGO_MODE=='local' else []
    vendedor=None
    if session.get('vendedor_id'):
        vendedor=conn.execute("SELECT * FROM vendedores WHERE id=?", (session['vendedor_id'],)).fetchone()
    vendidas=0; minhas=[]
    if vendedor:
        vendidas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id=? AND status='vendida'", (evento['id'],vendedor['id'])).fetchone()['c']
        minhas=conn.execute("SELECT numero,status,comprador FROM cartelas WHERE evento_id=? AND vendedor_id=? AND status<>'inutilizada' ORDER BY numero LIMIT 500",(evento['id'],vendedor['id'])).fetchall()
    conn.close(); return render_template('mobile_home.html', evento=evento, vendedores=vendedores, vendedor=vendedor, vendidas=vendidas, minhas=minhas, mode=BINGO_MODE, vendas_fechadas=vendas_fechadas(evento))


@app.route('/mobile/vendedor/<int:vendedor_id>')
def mobile_vendedor(vendedor_id):
    conn=get_db(); vendedor=conn.execute("SELECT * FROM vendedores WHERE id=? AND online_ativo=1", (vendedor_id,)).fetchone(); conn.close()
    token=request.args.get('token','')
    if vendedor and vendedor['acesso_token'] and secrets.compare_digest(token, vendedor['acesso_token']):
        session['vendedor_id']=vendedor_id; flash(f"Celular identificado como {vendedor['nome']}.", 'success')
    else:
        flash('Link de vendedor inválido ou expirado. Use seu código de acesso.', 'danger')
    return redirect(url_for('mobile_home'))


@app.route('/mobile/selecionar', methods=['POST'])
def mobile_selecionar():
    codigo=request.form.get('codigo_acesso','').strip()
    try: vendedor_id=int(request.form.get('vendedor_id','0'))
    except ValueError: vendedor_id=0
    conn=get_db()
    if codigo:
        vendedor=conn.execute("SELECT * FROM vendedores WHERE codigo_acesso=? AND online_ativo=1",(codigo,)).fetchone()
    elif BINGO_MODE=='local' and vendedor_id:
        vendedor=conn.execute("SELECT * FROM vendedores WHERE id=? AND online_ativo=1",(vendedor_id,)).fetchone()
    else:
        vendedor=None
    conn.close()
    if vendedor:
        session['vendedor_id']=vendedor['id']; flash(f"Acesso liberado para {vendedor['nome']}.",'success')
    else:
        flash('Código de vendedor inválido.','danger')
    return redirect(url_for('mobile_home'))


@app.route('/mobile/sair')
def mobile_sair():
    session.pop('vendedor_id',None); return redirect(url_for('mobile_home'))


@app.route('/mobile/abrir-cartela', methods=['POST'])
def mobile_abrir_cartela():
    conn=get_db(); evento=evento_ativo(conn); conn.close()
    try: numero=int(request.form.get('numero','0'))
    except ValueError: numero=0
    if numero <= 0:
        flash('Digite um número de cartela válido.','warning'); return redirect(url_for('mobile_home'))
    return redirect(url_for('mobile_cartela', evento_id=evento['id'], numero=numero))


@app.route('/m/<int:evento_id>/<int:numero>', methods=['GET','POST'])
def mobile_cartela(evento_id, numero):
    conn=get_db(); evento=conn.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone()
    if not evento:
        conn.close(); return render_template('mobile_erro.html', titulo='Evento não encontrado', mensagem='Este QR Code não pertence a um evento disponível.'),404
    card=conn.execute("""SELECT c.*,v.nome vendedor FROM cartelas c LEFT JOIN vendedores v ON v.id=c.vendedor_id
        WHERE c.evento_id=? AND c.numero=?""", (evento_id,numero)).fetchone()
    if not card:
        conn.close(); return render_template('mobile_erro.html', titulo='Cartela não encontrada', mensagem=f'Cartela {numero:04d} não existe neste evento.'),404
    vendedor=None
    if session.get('vendedor_id'):
        vendedor=conn.execute("SELECT * FROM vendedores WHERE id=? AND online_ativo=1", (session['vendedor_id'],)).fetchone()
    if request.method=='POST':
        if not evento['ativo']:
            flash('Este bingo não é mais o evento ativo e não aceita novas vendas.','warning')
        elif vendas_fechadas(evento):
            flash('As vendas deste bingo já foram encerradas para preparação do sorteio.','warning')
        elif not vendedor:
            flash('Identifique o vendedor antes de registrar uma venda.','danger')
        elif card['vendedor_id'] != vendedor['id']:
            flash('Esta cartela não pertence ao seu lote. Para evitar venda duplicada, somente o vendedor responsável pode dar baixa nela.','danger')
        elif card['status']=='vendida':
            flash('Esta cartela já está marcada como vendida.','warning')
        elif card['status']!='disponivel':
            flash('Esta cartela não está disponível para venda.','warning')
        else:
            comprador=request.form.get('comprador','').strip(); telefone=request.form.get('telefone','').strip(); pagamento=request.form.get('pagamento','').strip()
            vendedor_id=vendedor['id']; agora=datetime.now().isoformat(timespec='seconds'); suid=_novo_sync_uuid()
            conn.execute("UPDATE cartelas SET status='vendida',comprador=?,telefone=?,pagamento=?,vendedor_id=?,vendido_em=?,vendido_por_usuario_id=NULL WHERE id=?",
                         (comprador,telefone,pagamento,vendedor_id,agora,card['id']))
            cur=conn.execute("""INSERT INTO movimentacoes_vendas (evento_id,cartela_id,numero,tipo,comprador,telefone,pagamento,vendedor_id,usuario_id,criado_em,origem,sync_uuid,sync_enviado)
                VALUES (?,?,?,?,?,?,?,?,NULL,?,?,?,?)""",
                (evento_id,card['id'],numero,'venda',comprador,telefone,pagamento,vendedor_id,agora,'nuvem' if BINGO_MODE=='cloud' else 'celular',suid,1 if BINGO_MODE=='cloud' else 0))
            payload={'sync_uuid':suid,'evento_id':evento_id,'numero':numero,'tipo':'venda','comprador':comprador,'telefone':telefone,'pagamento':pagamento,
                     'vendedor_id':vendedor_id,'criado_em':agora,'origem':'nuvem' if BINGO_MODE=='cloud' else 'celular'}
            if BINGO_MODE=='cloud':
                _registrar_evento_sync(conn,suid,'venda',evento_id,numero,payload,'nuvem')
                conn.execute("INSERT OR IGNORE INTO sync_recebidos (uuid,origem,recebido_em) VALUES (?,?,?)",(suid,'nuvem',agora))
            conn.commit(); flash(f'Cartela {numero:04d} vendida com sucesso.','success')
            card=conn.execute("""SELECT c.*,v.nome vendedor FROM cartelas c LEFT JOIN vendedores v ON v.id=c.vendedor_id WHERE c.id=?""", (card['id'],)).fetchone()
    rodada=rodada_ativa(conn,evento_id)
    sorteados=[r['numero'] for r in conn.execute("SELECT numero FROM sorteios WHERE evento_id=? ORDER BY ordem", (evento_id,)).fetchall()]
    atende=bool(card['status']=='vendida' and rodada and cartela_status_rodada(card,sorteados,rodada))
    vendedores=[] if BINGO_MODE=='cloud' else conn.execute("SELECT * FROM vendedores WHERE online_ativo=1 ORDER BY nome").fetchall()
    grade=json.loads(card['numeros']); conn.close()
    return render_template('mobile_cartela.html', evento=evento, card=card, grade=grade, vendedor=vendedor, vendedores=vendedores, rodada=rodada,
                           atende=atende, padrao_label=padrao_label, mode=BINGO_MODE, vendas_fechadas=vendas_fechadas(evento))


@app.route('/sorteio/evento/<int:evento_id>/acao', methods=['POST'])
def sorteio_evento_acao(evento_id):
    conn=get_db(); alvo=conn.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone(); acao=request.form.get('acao')
    if not alvo:
        flash('Evento não encontrado.', 'danger')
    elif acao=='iniciar' and alvo['status']=='preparacao':
        conn.execute("UPDATE eventos SET status='em_andamento',encerrado_em=NULL WHERE id=?", (evento_id,)); conn.commit(); flash('Evento iniciado. Bom bingo!', 'success')
    elif acao=='reabrir' and alvo['status']=='encerrado':
        conn.execute("UPDATE eventos SET status='em_andamento',encerrado_em=NULL WHERE id=?", (evento_id,)); conn.commit(); flash('Evento reaberto para o sorteio.', 'warning')
    conn.close(); return redirect(url_for('sorteio'))


@app.route('/sorteio', methods=['GET','POST'])
def sorteio():
    conn=get_db(); evento=evento_ativo(conn)
    if request.method=='POST':
        acao=request.form.get('acao'); existentes=[r['numero'] for r in conn.execute("SELECT numero FROM sorteios WHERE evento_id=? ORDER BY ordem", (evento['id'],)).fetchall()]
        if acao=='sortear':
            restantes=[n for n in range(1,76) if n not in existentes]; numero=random.choice(restantes) if restantes else None
        else:
            try: numero=int(request.form.get('numero',0))
            except ValueError: numero=0
        if numero and 1<=numero<=75:
            if numero in existentes: flash(f'O número {numero} já foi sorteado.', 'warning')
            else:
                conn.execute("INSERT INTO sorteios (evento_id,numero,ordem) VALUES (?,?,?)", (evento['id'],numero,len(existentes)+1)); conn.commit(); flash(f'Número {numero} registrado.', 'success')
    sorteados=[r['numero'] for r in conn.execute("SELECT numero FROM sorteios WHERE evento_id=? ORDER BY ordem", (evento['id'],)).fetchall()]
    rodada=rodada_ativa(conn,evento['id']); possiveis=[]
    vendidas=conn.execute("""SELECT c.*,v.nome vendedor,l.codigo lote FROM cartelas c
        LEFT JOIN vendedores v ON v.id=c.vendedor_id
        LEFT JOIN lotes l ON l.id=c.lote_id
        WHERE c.evento_id=? AND c.status='vendida' ORDER BY c.numero""", (evento['id'],)).fetchall()
    if rodada:
        for card in vendidas:
            if cartela_status_rodada(card,sorteados,rodada):
                ja=conn.execute("SELECT COUNT(*) c FROM ganhadores WHERE rodada_id=? AND cartela_id=? AND confirmado=1", (rodada['id'],card['id'])).fetchone()['c']
                possiveis.append({'numero':card['numero'],'padrao':padrao_label(rodada['padrao']),'comprador':card['comprador'],'telefone':card['telefone'],'vendedor':card['vendedor'],'lote':card['lote'],'confirmado':bool(ja)})
    proximas=detectar_proximas_cartelas(conn,evento['id'],sorteados,rodada)
    ganhadores=conn.execute("""SELECT g.*,c.numero,c.comprador,c.telefone,v.nome vendedor,l.codigo lote FROM ganhadores g
        JOIN cartelas c ON c.id=g.cartela_id
        LEFT JOIN vendedores v ON v.id=c.vendedor_id
        LEFT JOIN lotes l ON l.id=c.lote_id
        WHERE g.evento_id=? AND g.confirmado=1 ORDER BY g.id DESC LIMIT 10""", (evento['id'],)).fetchall()
    conn.close(); return render_template('sorteio.html', evento=evento, sorteados=sorteados, ultimos=list(reversed(sorteados[-8:])), possiveis=possiveis, proximas=proximas, rodada=rodada, ganhadores=ganhadores, padrao_label=padrao_label)


@app.route('/conferir', methods=['POST'])
def conferir():
    conn=get_db(); evento=evento_ativo(conn)
    try: numero=int(request.form['numero'])
    except ValueError: numero=0
    card=conn.execute("""SELECT c.*,v.nome vendedor FROM cartelas c LEFT JOIN vendedores v ON v.id=c.vendedor_id
        WHERE c.evento_id=? AND c.numero=?""", (evento['id'],numero)).fetchone()
    rodada=rodada_ativa(conn,evento['id'])
    if not card:
        flash('Cartela não encontrada.','danger'); conn.close(); return redirect(url_for('sorteio'))
    sorteados=[r['numero'] for r in conn.execute("SELECT numero FROM sorteios WHERE evento_id=?", (evento['id'],)).fetchall()]
    if card['status']!='vendida': flash(f'Cartela {numero:04d}: NÃO VENDIDA. Não é válida para prêmio.','danger')
    elif not rodada: flash('Nenhuma rodada está ativa. Ative uma rodada para conferir.','warning')
    elif cartela_status_rodada(card,sorteados,rodada): flash(f"Cartela {numero:04d}: {padrao_label(rodada['padrao']).upper()} CONFIRMADO para {rodada['nome']}.",'success')
    else: flash(f"Cartela {numero:04d}: ainda não atende ao padrão da rodada ({padrao_label(rodada['padrao'])}).",'warning')
    conn.close(); return redirect(url_for('sorteio'))


@app.route('/confirmar-ganhador/<int:numero>', methods=['POST'])
def confirmar_ganhador(numero):
    conn=get_db(); evento=evento_ativo(conn); rodada=rodada_ativa(conn,evento['id'])
    card=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=?", (evento['id'],numero)).fetchone()
    sorteados=[r['numero'] for r in conn.execute("SELECT numero FROM sorteios WHERE evento_id=?", (evento['id'],)).fetchall()]
    if not rodada or not card or card['status']!='vendida' or not cartela_status_rodada(card,sorteados,rodada):
        conn.close(); flash('Não foi possível confirmar este ganhador.','danger'); return redirect(url_for('sorteio'))
    existe=conn.execute("SELECT COUNT(*) c FROM ganhadores WHERE rodada_id=? AND cartela_id=? AND confirmado=1", (rodada['id'],card['id'])).fetchone()['c']
    if not existe:
        conn.execute("INSERT INTO ganhadores (evento_id,cartela_id,padrao,confirmado,rodada_id) VALUES (?,?,?,?,?)", (evento['id'],card['id'],rodada['padrao'],1,rodada['id']))
        conn.commit(); flash(f'Ganhador confirmado: cartela {numero:04d}.','success')
    else: flash('Este ganhador já estava confirmado.','warning')
    conn.close(); return redirect(url_for('sorteio'))


@app.route('/reiniciar-sorteio', methods=['POST'])
def reiniciar_sorteio():
    conn=get_db(); evento=evento_ativo(conn); conn.execute("DELETE FROM sorteios WHERE evento_id=?", (evento['id'],)); conn.commit(); conn.close(); flash('Sorteio reiniciado.','warning'); return redirect(url_for('sorteio'))


@app.route('/telao')
def telao():
    conn=get_db(); evento=evento_ativo(conn); rodada=rodada_ativa(conn,evento['id']); conn.close(); return render_template('telao.html', evento=evento, rodada=rodada, padrao_label=padrao_label)


@app.route('/api/estado-sorteio')
def api_estado_sorteio():
    conn=get_db(); evento=evento_ativo(conn); rodada=rodada_ativa(conn,evento['id'])
    rows=conn.execute("SELECT numero FROM sorteios WHERE evento_id=? ORDER BY ordem", (evento['id'],)).fetchall(); nums=[r['numero'] for r in rows]
    rodada_data=None
    if rodada:
        rodada_data={'id':rodada['id'],'nome':rodada['nome'],'padrao':padrao_label(rodada['padrao']),'premio':float(rodada['premio'])}

    todas_proximas = detectar_proximas_cartelas(conn, evento['id'], nums, rodada) if rodada else {k: [] for k in [5,4,3,2,1]}
    proximas_json = {str(k): {'total': len(todas_proximas.get(k, [])), 'cartelas': todas_proximas.get(k, [])[:8]} for k in [5,4,3,2,1]}

    winner = None
    if rodada:
        winner = conn.execute("""SELECT g.id,c.numero,c.comprador,c.telefone,c.numeros,v.nome vendedor,l.codigo lote,r.nome rodada,r.premio
            FROM ganhadores g
            JOIN cartelas c ON c.id=g.cartela_id
            LEFT JOIN vendedores v ON v.id=c.vendedor_id
            LEFT JOIN lotes l ON l.id=c.lote_id
            LEFT JOIN rodadas r ON r.id=g.rodada_id
            WHERE g.evento_id=? AND g.rodada_id=? AND g.confirmado=1
            ORDER BY g.id DESC LIMIT 1""", (evento['id'],rodada['id'])).fetchone()
    ganhador=None
    if winner:
        ganhador={
            'id':winner['id'], 'numero':winner['numero'], 'comprador':winner['comprador'] or 'Não informado',
            'telefone':winner['telefone'] or 'Não informado', 'vendedor':winner['vendedor'] or 'Não informado',
            'lote':winner['lote'] or 'Sem lote', 'rodada':winner['rodada'] or '', 'premio':float(winner['premio'] or 0),
            'grade':json.loads(winner['numeros']), 'numeros_chamados':len(nums),
        }
    conn.close(); ultimo=nums[-1] if nums else None
    return jsonify({'evento':evento['nome'],'status_evento':evento['status'],'ultimo':ultimo,'letra':letra_numero(ultimo) if ultimo else '',
                    'sorteados':nums,'ultimos':list(reversed(nums[-7:])), 'total':len(nums), 'rodada':rodada_data,
                    'proximas':proximas_json,'ganhador':ganhador})


# ===== V4: múltiplos eventos, operação, relatórios e backup =====

def coletar_relatorio(conn, evento):
    eid = evento['id']
    valor_cartela = float(evento['valor_cartela'])
    total = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=?", (eid,)).fetchone()['c']
    vendidas = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='vendida'", (eid,)).fetchone()['c']
    distribuidas = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id IS NOT NULL", (eid,)).fetchone()['c']
    inutilizadas = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='inutilizada'", (eid,)).fetchone()['c']
    impressas = conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND impressa_em IS NOT NULL", (eid,)).fetchone()['c']
    lotes = conn.execute("SELECT COUNT(*) c FROM lotes WHERE evento_id=?", (eid,)).fetchone()['c']
    pagamentos = conn.execute("""SELECT COALESCE(NULLIF(pagamento,''),'Não informado') forma, COUNT(*) qtd
        FROM cartelas WHERE evento_id=? AND status='vendida' GROUP BY COALESCE(NULLIF(pagamento,''),'Não informado') ORDER BY qtd DESC""", (eid,)).fetchall()
    vendedores = conn.execute("SELECT * FROM vendedores ORDER BY nome").fetchall()
    por_vendedor=[]
    total_recebido=0
    for v in vendedores:
        dist=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id=?", (eid,v['id'])).fetchone()['c']
        sold=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id=? AND status='vendida'", (eid,v['id'])).fetchone()['c']
        rec=conn.execute("SELECT COALESCE(SUM(valor),0) s FROM acertos WHERE evento_id=? AND vendedor_id=?", (eid,v['id'])).fetchone()['s']
        if dist or sold or rec:
            devido=sold*valor_cartela
            por_vendedor.append({'nome':v['nome'],'distribuidas':dist,'vendidas':sold,'devido':devido,'recebido':float(rec),'saldo':devido-float(rec)})
            total_recebido += float(rec)
    rodadas=conn.execute("""SELECT r.*,
        (SELECT COUNT(*) FROM ganhadores g WHERE g.rodada_id=r.id AND g.confirmado=1) vencedores
        FROM rodadas r WHERE r.evento_id=? ORDER BY r.ordem,r.id""", (eid,)).fetchall()
    ganhadores=conn.execute("""SELECT g.*,c.numero,c.comprador,v.nome vendedor,r.nome rodada,r.premio
        FROM ganhadores g JOIN cartelas c ON c.id=g.cartela_id
        LEFT JOIN vendedores v ON v.id=c.vendedor_id LEFT JOIN rodadas r ON r.id=g.rodada_id
        WHERE g.evento_id=? AND g.confirmado=1 ORDER BY g.id""", (eid,)).fetchall()
    premios=sum(float(r['premio'] or 0) for r in rodadas if r['status']=='finalizada' or r['vencedores'])
    arrecadacao=vendidas*valor_cartela
    estornos=conn.execute("SELECT COUNT(*) c FROM movimentacoes_vendas WHERE evento_id=? AND tipo='cancelamento'", (eid,)).fetchone()['c']
    caixa_resumo=conn.execute("""SELECT COUNT(*) qtd,COALESCE(SUM(diferenca),0) diferenca FROM caixas
        WHERE evento_id=? AND status='fechado'""", (eid,)).fetchone()
    ultimo_caixa=conn.execute("SELECT * FROM caixas WHERE evento_id=? AND status='fechado' ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
    return {
        'total':total,'vendidas':vendidas,'nao_vendidas':max(total-vendidas-inutilizadas,0),'distribuidas':distribuidas,'inutilizadas':inutilizadas,'impressas':impressas,'lotes':lotes,
        'arrecadacao':arrecadacao,'total_recebido':total_recebido,'saldo_receber':arrecadacao-total_recebido,
        'pagamentos':pagamentos,'vendedores':por_vendedor,'rodadas':rodadas,'ganhadores':ganhadores,
        'premios':premios,'resultado_estimado':arrecadacao-premios,'estornos':estornos,
        'caixa_fechamentos':caixa_resumo['qtd'],'caixa_diferenca':float(caixa_resumo['diferenca'] or 0),'ultimo_caixa':ultimo_caixa
    }


# ===== V6: estoque físico, busca, comprovantes e estatísticas =====
def status_cartela_label(status):
    return {
        'disponivel': 'Disponível',
        'vendida': 'Vendida',
        'inutilizada': 'Inutilizada',
    }.get(status or 'disponivel', (status or 'disponivel').replace('_',' ').title())


def _normalizar_fone(valor):
    return ''.join(ch for ch in (valor or '') if ch.isdigit())


def _comprovante_venda_pdf(evento, mov, vendedor=None, usuario=None, cancelada=False):
    buf=BytesIO(); pdf=canvas.Canvas(buf,pagesize=A4); pw,ph=A4
    x=22*mm; y=ph-26*mm
    pdf.setFillColor(PRIMARY); pdf.setFont('Helvetica-Bold',22); pdf.drawString(x,y,'Comprovante de venda'); y-=9*mm
    pdf.setFillColor(TEXT); pdf.setFont('Helvetica-Bold',13); pdf.drawString(x,y,evento['nome'][:70]); y-=7*mm
    pdf.setFillColor(MUTED); pdf.setFont('Helvetica',9); pdf.drawString(x,y,f"Cartela #{int(mov['numero']):04d} • Referência B{evento['id']}-V{mov['id']:06d}"); y-=13*mm
    if cancelada:
        pdf.setFillColor(HexColor('#B02A3B')); pdf.setFont('Helvetica-Bold',12); pdf.drawString(x,y,'VENDA CANCELADA / ESTORNADA'); y-=10*mm
    dados=[
        ('Comprador', mov['comprador'] or 'Não informado'),
        ('Telefone', mov['telefone'] or 'Não informado'),
        ('Pagamento', mov['pagamento'] or 'Não informado'),
        ('Vendedor', vendedor['nome'] if vendedor else 'Venda direta / não informado'),
        ('Registrado por', usuario['nome'] if usuario else ('Acesso pelo celular' if (mov['origem'] or '')=='celular' else 'Sistema local')),
        ('Data e hora', (mov['criado_em'] or '').replace('T',' ')),
        ('Valor da cartela', _pdf_money(evento['valor_cartela'])),
    ]
    for label,value in dados:
        pdf.setFillColor(MUTED); pdf.setFont('Helvetica-Bold',8); pdf.drawString(x,y,label.upper());
        pdf.setFillColor(TEXT); pdf.setFont('Helvetica',11); pdf.drawString(x,y-5*mm,str(value)[:85]); y-=14*mm
    payload=f"{base_url_rede(evento)}/m/{evento['id']}/{int(mov['numero'])}"
    qr=qr_image(payload); qbuf=BytesIO(); qr.save(qbuf,format='PNG'); qbuf.seek(0)
    pdf.drawImage(ImageReader(qbuf),pw-58*mm,ph-82*mm,32*mm,32*mm,mask='auto')
    pdf.setFillColor(MUTED); pdf.setFont('Helvetica',7); pdf.drawString(x,24*mm,'Este comprovante confirma o registro da venda no Bingo Comunidade. A cartela física continua sendo o documento de participação.')
    pdf.drawString(x,18*mm,f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} • Bingo Comunidade V11")
    pdf.save(); buf.seek(0); return buf


def _comprovante_acerto_pdf(evento, acerto, vendedor):
    buf=BytesIO(); pdf=canvas.Canvas(buf,pagesize=A4); pw,ph=A4
    x=22*mm; y=ph-28*mm
    pdf.setFillColor(PRIMARY); pdf.setFont('Helvetica-Bold',22); pdf.drawString(x,y,'Recibo de acerto'); y-=10*mm
    pdf.setFillColor(TEXT); pdf.setFont('Helvetica-Bold',13); pdf.drawString(x,y,evento['nome'][:70]); y-=15*mm
    itens=[('Vendedor / equipe',vendedor['nome']),('Valor recebido',_pdf_money(acerto['valor'])),('Forma de pagamento',acerto['forma_pagamento'] or 'Não informada'),('Data e hora',(acerto['criado_em'] or '').replace('T',' ')),('Observação',acerto['observacao'] or '—'),('Referência',f"B{evento['id']}-A{acerto['id']:06d}")]
    for label,value in itens:
        pdf.setFillColor(MUTED); pdf.setFont('Helvetica-Bold',8); pdf.drawString(x,y,label.upper());
        pdf.setFillColor(TEXT); pdf.setFont('Helvetica',11); pdf.drawString(x,y-5*mm,str(value)[:90]); y-=15*mm
    pdf.setFillColor(MUTED); pdf.setFont('Helvetica',7); pdf.drawString(x,18*mm,f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} • Bingo Comunidade V11")
    pdf.save(); buf.seek(0); return buf


@app.route('/estoque', methods=['GET','POST'])
def estoque():
    conn=get_db(); evento=evento_ativo(conn); eid=evento['id']
    if request.method=='POST':
        acao=request.form.get('acao','')
        if acao=='criar_lote':
            codigo=request.form.get('codigo','').strip()
            try: inicio=int(request.form.get('inicio','0')); fim=int(request.form.get('fim','0'))
            except ValueError: inicio=fim=0
            if fim<inicio: inicio,fim=fim,inicio
            if not codigo: codigo=f"L{inicio:04d}-{fim:04d}"
            existentes=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND numero BETWEEN ? AND ?",(eid,inicio,fim)).fetchone()['c']
            ocupadas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND numero BETWEEN ? AND ? AND lote_id IS NOT NULL",(eid,inicio,fim)).fetchone()['c']
            duplicado=conn.execute("SELECT 1 FROM lotes WHERE evento_id=? AND codigo=?",(eid,codigo)).fetchone()
            if inicio<=0 or existentes==0:
                flash('Informe uma faixa de cartelas existente.','warning')
            elif ocupadas:
                flash(f'Existem {ocupadas} cartelas dessa faixa já vinculadas a outro lote.','warning')
            elif duplicado:
                flash('Já existe um lote com esse código neste evento.','warning')
            else:
                cur=conn.execute("INSERT INTO lotes (evento_id,codigo,inicio,fim,status,observacao,criado_por,criado_em) VALUES (?,?,?,?, 'preparado',?,?,?)",(eid,codigo,inicio,fim,request.form.get('observacao','').strip(),usuario_atual_id(),datetime.now().isoformat(timespec='seconds')))
                conn.execute("UPDATE cartelas SET lote_id=? WHERE evento_id=? AND numero BETWEEN ? AND ?",(cur.lastrowid,eid,inicio,fim))
                conn.commit(); flash(f'Lote {codigo} criado com {existentes} cartelas.','success')
        elif acao in {'marcar_impresso','entregar_lote','devolver_lote','fechar_lote'}:
            try: lote_id=int(request.form.get('lote_id','0'))
            except ValueError: lote_id=0
            lote=conn.execute("SELECT * FROM lotes WHERE id=? AND evento_id=?",(lote_id,eid)).fetchone()
            if not lote:
                flash('Lote não encontrado.','danger')
            elif acao=='marcar_impresso':
                agora=datetime.now().isoformat(timespec='seconds')
                conn.execute("UPDATE lotes SET status=CASE WHEN status='preparado' THEN 'impresso' ELSE status END, impresso_em=COALESCE(impresso_em,?) WHERE id=?",(agora,lote_id))
                conn.execute("UPDATE cartelas SET impressa_em=COALESCE(impressa_em,?) WHERE evento_id=? AND lote_id=?",(agora,eid,lote_id)); conn.commit(); flash('Lote marcado como impresso.','success')
            elif acao=='entregar_lote':
                try: vendedor_id=int(request.form.get('vendedor_id','0'))
                except ValueError: vendedor_id=0
                vendedor=conn.execute("SELECT * FROM vendedores WHERE id=?",(vendedor_id,)).fetchone()
                if not vendedor: flash('Selecione um vendedor válido.','warning')
                else:
                    conn.execute("UPDATE lotes SET vendedor_id=?,status='distribuido' WHERE id=?",(vendedor_id,lote_id))
                    cur=conn.execute("UPDATE cartelas SET vendedor_id=? WHERE evento_id=? AND lote_id=? AND status='disponivel'",(vendedor_id,eid,lote_id)); conn.commit(); flash(f"Lote entregue a {vendedor['nome']} ({cur.rowcount} cartelas disponíveis).",'success')
            elif acao=='devolver_lote':
                cur=conn.execute("UPDATE cartelas SET vendedor_id=NULL WHERE evento_id=? AND lote_id=? AND status='disponivel'",(eid,lote_id))
                conn.execute("UPDATE lotes SET vendedor_id=NULL,status=CASE WHEN impresso_em IS NULL THEN 'preparado' ELSE 'impresso' END WHERE id=?",(lote_id,)); conn.commit(); flash(f'{cur.rowcount} cartelas disponíveis retornaram ao estoque.','success')
            elif acao=='fechar_lote':
                conn.execute("UPDATE lotes SET status='fechado' WHERE id=?",(lote_id,)); conn.commit(); flash('Lote fechado para organização do histórico.','success')
        elif acao=='inutilizar':
            try: numero=int(request.form.get('numero','0'))
            except ValueError: numero=0
            motivo=request.form.get('motivo','').strip() or 'Danificada/perdida'
            card=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=?",(eid,numero)).fetchone()
            if not card: flash('Cartela não encontrada.','danger')
            elif card['status']=='vendida': flash('Uma cartela vendida não pode ser inutilizada. Primeiro estorne a venda, se necessário.','warning')
            elif card['status']=='inutilizada': flash('Esta cartela já está inutilizada.','warning')
            else:
                conn.execute("UPDATE cartelas SET status='inutilizada',vendedor_id=NULL,inutilizada_em=?,inutilizada_motivo=? WHERE id=?",(datetime.now().isoformat(timespec='seconds'),motivo,card['id'])); conn.commit(); flash(f'Cartela {numero:04d} inutilizada.','success')
        elif acao=='reativar':
            try: numero=int(request.form.get('numero','0'))
            except ValueError: numero=0
            card=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=? AND status='inutilizada'",(eid,numero)).fetchone()
            if card:
                conn.execute("UPDATE cartelas SET status='disponivel',inutilizada_em=NULL,inutilizada_motivo=NULL WHERE id=?",(card['id'],)); conn.commit(); flash(f'Cartela {numero:04d} reativada e devolvida ao estoque.','success')
            else: flash('Cartela inutilizada não encontrada.','warning')
        return redirect(url_for('estoque'))

    resumo={}
    resumo['total']=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=?",(eid,)).fetchone()['c']
    resumo['loteadas']=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND lote_id IS NOT NULL",(eid,)).fetchone()['c']
    resumo['impressas']=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND impressa_em IS NOT NULL",(eid,)).fetchone()['c']
    resumo['estoque']=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='disponivel' AND vendedor_id IS NULL",(eid,)).fetchone()['c']
    resumo['distribuidas']=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='disponivel' AND vendedor_id IS NOT NULL",(eid,)).fetchone()['c']
    resumo['vendidas']=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='vendida'",(eid,)).fetchone()['c']
    resumo['inutilizadas']=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='inutilizada'",(eid,)).fetchone()['c']
    lotes=conn.execute("""SELECT l.*,v.nome vendedor,
        COUNT(c.id) qtd,
        SUM(CASE WHEN c.status='vendida' THEN 1 ELSE 0 END) vendidas,
        SUM(CASE WHEN c.status='disponivel' THEN 1 ELSE 0 END) disponiveis,
        SUM(CASE WHEN c.status='inutilizada' THEN 1 ELSE 0 END) inutilizadas
        FROM lotes l LEFT JOIN vendedores v ON v.id=l.vendedor_id LEFT JOIN cartelas c ON c.lote_id=l.id
        WHERE l.evento_id=? GROUP BY l.id ORDER BY l.id DESC""",(eid,)).fetchall()
    vendedores=conn.execute("SELECT * FROM vendedores ORDER BY nome").fetchall()
    inutilizadas=conn.execute("""SELECT c.numero,c.inutilizada_em,c.inutilizada_motivo,l.codigo lote FROM cartelas c
        LEFT JOIN lotes l ON l.id=c.lote_id WHERE c.evento_id=? AND c.status='inutilizada' ORDER BY c.numero LIMIT 80""",(eid,)).fetchall()
    minimo=conn.execute("SELECT MIN(numero) n FROM cartelas WHERE evento_id=?",(eid,)).fetchone()['n'] or 1
    maximo=conn.execute("SELECT MAX(numero) n FROM cartelas WHERE evento_id=?",(eid,)).fetchone()['n'] or 1
    conn.close(); return render_template('estoque.html',evento=evento,resumo=resumo,lotes=lotes,vendedores=vendedores,inutilizadas=inutilizadas,minimo=minimo,maximo=maximo)


@app.route('/estoque/lote/<int:lote_id>/pdf')
def lote_pdf(lote_id):
    conn=get_db(); evento=evento_ativo(conn); lote=conn.execute("SELECT * FROM lotes WHERE id=? AND evento_id=?",(lote_id,evento['id'])).fetchone()
    if not lote:
        conn.close(); flash('Lote não encontrado.','danger'); return redirect(url_for('estoque'))
    cards=conn.execute("""SELECT c.*, l.codigo AS lote_codigo
        FROM cartelas c
        LEFT JOIN lotes l ON l.id=c.lote_id
        WHERE c.evento_id=? AND c.lote_id=? AND c.status<>'inutilizada'
        ORDER BY c.numero""",(evento['id'],lote_id)).fetchall(); conn.close()
    if not cards:
        flash('Este lote não possui cartelas.','warning'); return redirect(url_for('estoque'))

    buf=BytesIO()
    page=landscape(A4); pdf=canvas.Canvas(buf,pagesize=page); pw,ph=page
    card_h=190*mm
    card_w=card_h*(1024/1536)
    gap=5*mm
    total_w=2*card_w+gap
    left=(pw-total_w)/2
    bottom=(ph-card_h)/2
    positions=[(left,bottom),(left+card_w+gap,bottom)]
    for i,card in enumerate(cards):
        if i>0 and i%2==0: pdf.showPage()
        draw_card_pdf(pdf,evento,card,*positions[i%2],card_w,card_h)
    pdf.save(); buf.seek(0)
    return send_file(buf,mimetype='application/pdf',as_attachment=True,
                     download_name=f"lote_{lote['codigo']}_TEMPLATE_OFICIAL.pdf")


@app.route('/busca')
def busca():
    conn=get_db(); evento=evento_ativo(conn); q=request.args.get('q','').strip(); todos=request.args.get('todos')=='1' and g.usuario['perfil'] in {'admin','coordenador','auditor'}
    resultados=[]
    if q:
        sql="""SELECT c.*,e.nome evento_nome,v.nome vendedor,l.codigo lote FROM cartelas c
            JOIN eventos e ON e.id=c.evento_id LEFT JOIN vendedores v ON v.id=c.vendedor_id LEFT JOIN lotes l ON l.id=c.lote_id WHERE 1=1"""
        params=[]
        if not todos:
            sql+=' AND c.evento_id=?'; params.append(evento['id'])
        termos=[]
        if q.isdigit():
            termos.append('c.numero=?'); params.append(int(q))
        termos += ['c.comprador LIKE ?','c.telefone LIKE ?']
        params += [f'%{q}%',f'%{q}%']
        digits=_normalizar_fone(q)
        if digits:
            termos.append("REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(c.telefone,'(',''),')',''),'-',''),' ',''),'+','') LIKE ?")
            params.append(f'%{digits}%')
        sql += ' AND ('+' OR '.join(termos)+') ORDER BY c.evento_id DESC,c.numero LIMIT 150'
        resultados=conn.execute(sql,params).fetchall()
    conn.close(); return render_template('busca.html',evento=evento,q=q,todos=todos,resultados=resultados,status_cartela_label=status_cartela_label)


@app.route('/comprovantes/venda/<int:mov_id>.pdf')
def comprovante_venda(mov_id):
    conn=get_db(); mov=conn.execute("SELECT * FROM movimentacoes_vendas WHERE id=? AND tipo='venda'",(mov_id,)).fetchone()
    if not mov:
        conn.close(); flash('Registro de venda não encontrado.','warning'); return redirect(url_for('vendas'))
    evento=conn.execute("SELECT * FROM eventos WHERE id=?",(mov['evento_id'],)).fetchone()
    vendedor=conn.execute("SELECT * FROM vendedores WHERE id=?",(mov['vendedor_id'],)).fetchone() if mov['vendedor_id'] else None
    usuario=conn.execute("SELECT * FROM usuarios WHERE id=?",(mov['usuario_id'],)).fetchone() if mov['usuario_id'] else None
    cancelada=bool(conn.execute("SELECT 1 FROM movimentacoes_vendas WHERE cartela_id=? AND tipo='cancelamento' AND id>? LIMIT 1",(mov['cartela_id'],mov_id)).fetchone())
    conn.close(); buf=_comprovante_venda_pdf(evento,mov,vendedor,usuario,cancelada)
    return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=f"comprovante_cartela_{int(mov['numero']):04d}.pdf")


@app.route('/m/<int:evento_id>/<int:numero>/comprovante.pdf')
def mobile_comprovante(evento_id,numero):
    conn=get_db(); evento=conn.execute("SELECT * FROM eventos WHERE id=?",(evento_id,)).fetchone()
    card=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=? AND status='vendida'",(evento_id,numero)).fetchone()
    if not evento or not card:
        conn.close(); return Response('Comprovante não disponível.',status=404)
    mov=conn.execute("SELECT * FROM movimentacoes_vendas WHERE cartela_id=? AND tipo='venda' ORDER BY id DESC LIMIT 1",(card['id'],)).fetchone()
    if not mov:
        conn.close(); return Response('Comprovante não disponível.',status=404)
    vendedor=conn.execute("SELECT * FROM vendedores WHERE id=?",(mov['vendedor_id'],)).fetchone() if mov['vendedor_id'] else None
    usuario=conn.execute("SELECT * FROM usuarios WHERE id=?",(mov['usuario_id'],)).fetchone() if mov['usuario_id'] else None
    conn.close(); buf=_comprovante_venda_pdf(evento,mov,vendedor,usuario,False)
    return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=f"comprovante_cartela_{numero:04d}.pdf")


@app.route('/comprovantes/acerto/<int:acerto_id>.pdf')
def comprovante_acerto(acerto_id):
    conn=get_db(); acerto=conn.execute("SELECT * FROM acertos WHERE id=?",(acerto_id,)).fetchone()
    if not acerto:
        conn.close(); flash('Acerto não encontrado.','warning'); return redirect(url_for('financeiro'))
    evento=conn.execute("SELECT * FROM eventos WHERE id=?",(acerto['evento_id'],)).fetchone(); vendedor=conn.execute("SELECT * FROM vendedores WHERE id=?",(acerto['vendedor_id'],)).fetchone(); conn.close()
    buf=_comprovante_acerto_pdf(evento,acerto,vendedor)
    return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=f"recibo_acerto_{acerto_id:05d}.pdf")


def coletar_estatisticas(conn,evento):
    eid=evento['id']; valor=float(evento['valor_cartela'])
    total=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=?",(eid,)).fetchone()['c']
    vendidas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='vendida'",(eid,)).fetchone()['c']
    impressas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND impressa_em IS NOT NULL",(eid,)).fetchone()['c']
    loteadas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND lote_id IS NOT NULL",(eid,)).fetchone()['c']
    distribuidas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id IS NOT NULL",(eid,)).fetchone()['c']
    inutilizadas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='inutilizada'",(eid,)).fetchone()['c']
    pagamentos=[dict(r) for r in conn.execute("""SELECT COALESCE(NULLIF(pagamento,''),'Não informado') nome,COUNT(*) qtd
        FROM cartelas WHERE evento_id=? AND status='vendida' GROUP BY COALESCE(NULLIF(pagamento,''),'Não informado') ORDER BY qtd DESC""",(eid,)).fetchall()]
    max_pay=max([x['qtd'] for x in pagamentos],default=1)
    for x in pagamentos: x['pct']=x['qtd']/max_pay*100; x['valor']=x['qtd']*valor
    vendedores=[dict(r) for r in conn.execute("""SELECT v.nome,COUNT(*) qtd FROM cartelas c JOIN vendedores v ON v.id=c.vendedor_id
        WHERE c.evento_id=? AND c.status='vendida' GROUP BY v.id ORDER BY qtd DESC,v.nome LIMIT 12""",(eid,)).fetchall()]
    max_v=max([x['qtd'] for x in vendedores],default=1)
    for x in vendedores: x['pct']=x['qtd']/max_v*100; x['valor']=x['qtd']*valor
    dias=[dict(r) for r in conn.execute("""SELECT substr(vendido_em,1,10) dia,COUNT(*) qtd FROM cartelas
        WHERE evento_id=? AND status='vendida' AND vendido_em IS NOT NULL GROUP BY substr(vendido_em,1,10) ORDER BY dia DESC LIMIT 14""",(eid,)).fetchall()]
    dias=list(reversed(dias)); max_d=max([x['qtd'] for x in dias],default=1)
    for x in dias: x['pct']=x['qtd']/max_d*100
    origens=[dict(r) for r in conn.execute("""SELECT CASE WHEN vendedor_id IS NULL THEN 'Venda direta' ELSE 'Com vendedor' END nome,COUNT(*) qtd
        FROM cartelas WHERE evento_id=? AND status='vendida' GROUP BY CASE WHEN vendedor_id IS NULL THEN 'Venda direta' ELSE 'Com vendedor' END ORDER BY qtd DESC""",(eid,)).fetchall()]
    compradores=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='vendida' AND (COALESCE(comprador,'')<>'' OR COALESCE(telefone,'')<>'')",(eid,)).fetchone()['c']
    return {'total':total,'vendidas':vendidas,'impressas':impressas,'loteadas':loteadas,'distribuidas':distribuidas,'inutilizadas':inutilizadas,
            'taxa':(vendidas/total*100 if total else 0),'arrecadacao':vendidas*valor,'pagamentos':pagamentos,'vendedores':vendedores,'dias':dias,'origens':origens,'compradores':compradores}


@app.route('/estatisticas')
def estatisticas():
    conn=get_db(); evento=evento_ativo(conn); dados=coletar_estatisticas(conn,evento); conn.close()
    return render_template('estatisticas.html',evento=evento,dados=dados)


@app.route('/eventos', methods=['GET','POST'])
def eventos():
    conn=get_db(); atual=evento_ativo(conn)
    if request.method=='POST':
        nome=request.form.get('nome','').strip()
        data=request.form.get('data','')
        try: valor=float(request.form.get('valor_cartela','15').replace(',','.'))
        except ValueError: valor=15
        organizador=request.form.get('organizador_cartela',COMMUNITY_NAME).strip() or COMMUNITY_NAME
        horario=request.form.get('horario_cartela',DEFAULT_CARD_TIME).strip() or DEFAULT_CARD_TIME
        premios=request.form.get('premios_cartela','').strip() or '\n'.join(DEFAULT_CARD_PRIZES)
        if nome:
            conn.execute("UPDATE eventos SET ativo=0")
            cur=conn.execute("""INSERT INTO eventos (nome,data,valor_cartela,modalidade,ativo,status,criado_em,organizador_cartela,horario_cartela,premios_cartela)
                VALUES (?,?,?,?,1,'preparacao',?,?,?,?)""", (nome,data,valor,75,datetime.now().isoformat(timespec='seconds'),organizador,horario,premios))
            criar_rodadas_padrao(conn, cur.lastrowid)
            conn.commit(); flash('Novo evento criado e selecionado.', 'success')
            return redirect(url_for('dashboard'))
    rows=conn.execute("""SELECT e.*,
        (SELECT COUNT(*) FROM cartelas c WHERE c.evento_id=e.id) cartelas,
        (SELECT COUNT(*) FROM cartelas c WHERE c.evento_id=e.id AND c.status='vendida') vendidas,
        (SELECT COUNT(*) FROM ganhadores g WHERE g.evento_id=e.id AND g.confirmado=1) ganhadores
        FROM eventos e ORDER BY e.ativo DESC, COALESCE(e.data,'' ) DESC, e.id DESC""").fetchall()
    conn.close(); return render_template('eventos.html', evento=atual, eventos=rows, status_evento_label=status_evento_label)


@app.route('/eventos/<int:evento_id>/editar', methods=['GET','POST'])
def evento_editar(evento_id):
    conn=get_db(); alvo=conn.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone()
    if not alvo:
        conn.close(); flash('Evento não encontrado.', 'danger'); return redirect(url_for('eventos'))
    if request.method=='POST':
        nome=request.form.get('nome','').strip()
        data=request.form.get('data','')
        try: valor=float(request.form.get('valor_cartela','10').replace(',','.'))
        except ValueError: valor=float(alvo['valor_cartela'])
        url_rede=request.form.get('url_rede', alvo['url_rede'] or '').strip().rstrip('/')
        organizador=request.form.get('organizador_cartela',evento_cartela_campo(alvo,'organizador_cartela',COMMUNITY_NAME)).strip() or COMMUNITY_NAME
        horario=request.form.get('horario_cartela',evento_cartela_campo(alvo,'horario_cartela',DEFAULT_CARD_TIME)).strip() or DEFAULT_CARD_TIME
        premios=request.form.get('premios_cartela',evento_cartela_campo(alvo,'premios_cartela','\n'.join(DEFAULT_CARD_PRIZES))).strip() or '\n'.join(DEFAULT_CARD_PRIZES)
        if nome:
            conn.execute("UPDATE eventos SET nome=?,data=?,valor_cartela=?,url_rede=?,organizador_cartela=?,horario_cartela=?,premios_cartela=? WHERE id=?",
                         (nome,data,valor,url_rede,organizador,horario,premios,evento_id))
            conn.commit(); flash('Evento e modelo da cartela atualizados com sucesso.', 'success')
            conn.close(); return redirect(url_for('eventos'))
    atual=evento_ativo(conn)
    conn.close(); return render_template('evento_editar.html', evento=atual, alvo=alvo)


@app.route('/eventos/<int:evento_id>/excluir', methods=['POST'])
def evento_excluir(evento_id):
    conn=get_db(); alvo=conn.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone()
    if not alvo:
        conn.close(); flash('Evento não encontrado.', 'danger'); return redirect(url_for('eventos'))
    era_ativo=bool(alvo['ativo'])
    # Remove somente dados pertencentes ao evento; vendedores e usuários são cadastros globais.
    for tabela in ['caixa_movimentos','caixas','movimentacoes_vendas','acertos','ganhadores','sorteios','rodadas','cartelas','lotes','auditoria']:
        conn.execute(f"DELETE FROM {tabela} WHERE evento_id=?", (evento_id,))
    conn.execute("DELETE FROM eventos WHERE id=?", (evento_id,))
    if era_ativo:
        proximo=conn.execute("SELECT id FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
        if proximo:
            conn.execute("UPDATE eventos SET ativo=0"); conn.execute("UPDATE eventos SET ativo=1 WHERE id=?", (proximo['id'],)); criar_rodadas_padrao(conn,proximo['id'])
        else:
            cur=conn.execute("""INSERT INTO eventos (nome,data,valor_cartela,modalidade,ativo,status,criado_em,organizador_cartela,horario_cartela,premios_cartela)
                VALUES (?,?,?,75,1,'preparacao',?,?,?,?)""",
                ('Ação Entre Amigos','2026-11-07',15.0,datetime.now().isoformat(timespec='seconds'),COMMUNITY_NAME,DEFAULT_CARD_TIME,'\n'.join(DEFAULT_CARD_PRIZES)))
            criar_rodadas_padrao(conn,cur.lastrowid)
    conn.commit(); conn.close(); flash(f"Evento ‘{alvo['nome']}’ excluído.", 'warning'); return redirect(url_for('eventos'))


@app.route('/eventos/<int:evento_id>/ativar', methods=['POST'])
def evento_ativar(evento_id):
    conn=get_db(); alvo=conn.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone()
    if alvo:
        conn.execute("UPDATE eventos SET ativo=0")
        conn.execute("UPDATE eventos SET ativo=1 WHERE id=?", (evento_id,))
        criar_rodadas_padrao(conn, evento_id)
        conn.commit(); flash(f"Evento selecionado: {alvo['nome']}.", 'success')
    else:
        flash('Evento não encontrado.', 'danger')
    conn.close(); return redirect(url_for('eventos'))


@app.route('/eventos/<int:evento_id>/status', methods=['POST'])
def evento_status(evento_id):
    conn=get_db(); alvo=conn.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone()
    acao=request.form.get('acao')
    if not alvo:
        flash('Evento não encontrado.', 'danger')
    elif acao=='iniciar':
        conn.execute("UPDATE eventos SET status='em_andamento', encerrado_em=NULL WHERE id=?", (evento_id,))
        conn.commit(); flash('Evento colocado em andamento.', 'success')
    elif acao=='encerrar':
        caixa_aberto=conn.execute("SELECT * FROM caixas WHERE evento_id=? AND status='aberto' ORDER BY id DESC LIMIT 1", (evento_id,)).fetchone()
        if caixa_aberto:
            flash('Existe um caixa aberto. Faça o fechamento do caixa antes de encerrar oficialmente o evento.', 'warning')
            conn.close(); return redirect(url_for('caixa'))
        conn.execute("UPDATE eventos SET status='encerrado', encerrado_em=? WHERE id=?", (datetime.now().isoformat(timespec='seconds'),evento_id))
        conn.commit()
        try:
            pasta=Path(__file__).with_name('backups'); pasta.mkdir(exist_ok=True)
            destino=pasta/f"fechamento_evento_{evento_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            origem_db=sqlite3.connect(DB_PATH); copia_db=sqlite3.connect(destino)
            try: origem_db.backup(copia_db)
            finally: copia_db.close(); origem_db.close()
            flash(f'Evento encerrado oficialmente. Backup de fechamento criado: {destino.name}.', 'success')
        except Exception:
            flash('Evento encerrado oficialmente. Alterações operacionais foram bloqueadas.', 'success')
    elif acao=='reabrir':
        conn.execute("UPDATE eventos SET status='em_andamento', encerrado_em=NULL WHERE id=?", (evento_id,))
        conn.commit(); flash('Evento reaberto para operação.', 'warning')
    elif acao=='preparacao':
        conn.execute("UPDATE eventos SET status='preparacao', encerrado_em=NULL WHERE id=?", (evento_id,))
        conn.commit(); flash('Evento voltou para preparação.', 'warning')
    conn.close(); return redirect(request.referrer or url_for('operacao'))


@app.route('/operacao')
def operacao():
    conn=get_db(); evento=evento_ativo(conn); eid=evento['id']
    total=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=?", (eid,)).fetchone()['c']
    vendidas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='vendida'", (eid,)).fetchone()['c']
    distribuidas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND vendedor_id IS NOT NULL", (eid,)).fetchone()['c']
    vendedores=conn.execute("SELECT COUNT(*) c FROM vendedores").fetchone()['c']
    rodadas=conn.execute("SELECT COUNT(*) c FROM rodadas WHERE evento_id=?", (eid,)).fetchone()['c']
    lotes=conn.execute("SELECT COUNT(*) c FROM lotes WHERE evento_id=?", (eid,)).fetchone()['c']
    impressas=conn.execute("SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND impressa_em IS NOT NULL", (eid,)).fetchone()['c']
    sorteados=conn.execute("SELECT COUNT(*) c FROM sorteios WHERE evento_id=?", (eid,)).fetchone()['c']
    pendencias=[
        {'ok':bool(evento['nome']),'titulo':'Nome do evento','texto':'Identificação principal configurada.'},
        {'ok':bool(evento['data']),'titulo':'Data do evento','texto':'Defina a data para organizar o histórico.'},
        {'ok':total>0,'titulo':'Cartelas geradas','texto':f'{total} cartelas preparadas.'},
        {'ok':lotes>0 or total==0,'titulo':'Lotes físicos','texto':f'{lotes} lotes organizados no estoque.'},
        {'ok':impressas>0 or total==0,'titulo':'Impressão','texto':f'{impressas} cartelas marcadas como impressas.'},
        {'ok':vendedores>0,'titulo':'Vendedores cadastrados','texto':f'{vendedores} vendedores/equipes no cadastro.'},
        {'ok':rodadas>0,'titulo':'Rodadas e prêmios','texto':f'{rodadas} rodadas configuradas.'},
        {'ok':distribuidas>0 or total==0,'titulo':'Distribuição','texto':f'{distribuidas} cartelas atribuídas a vendedores.'},
    ]
    prontos=sum(1 for x in pendencias if x['ok'])
    conn.close(); return render_template('operacao.html', evento=evento, total=total, vendidas=vendidas, distribuidas=distribuidas, sorteados=sorteados, pendencias=pendencias, prontos=prontos, status_evento_label=status_evento_label)


@app.route('/relatorios')
def relatorios():
    conn=get_db(); evento=evento_ativo(conn); dados=coletar_relatorio(conn,evento); conn.close()
    return render_template('relatorios.html', evento=evento, dados=dados, padrao_label=padrao_label, status_evento_label=status_evento_label)


def _pdf_money(v):
    return f"R$ {float(v):,.2f}".replace(',', 'X').replace('.', ',').replace('X','.')


@app.route('/relatorios/pdf')
def relatorio_pdf():
    conn=get_db(); evento=evento_ativo(conn); dados=coletar_relatorio(conn,evento); conn.close()
    buf=BytesIO(); pdf=canvas.Canvas(buf,pagesize=A4); pw,ph=A4
    y=ph-22*mm
    def title(txt,size=17):
        nonlocal y
        pdf.setFillColor(PRIMARY); pdf.setFont('Helvetica-Bold',size); pdf.drawString(18*mm,y,txt); y-=9*mm
    def line(label,value,bold=False):
        nonlocal y
        if y<20*mm:
            pdf.showPage(); y=ph-20*mm
        pdf.setFillColor(TEXT); pdf.setFont('Helvetica-Bold' if bold else 'Helvetica',9.5)
        pdf.drawString(18*mm,y,str(label)[:62]); pdf.drawRightString(pw-18*mm,y,str(value)[:32]); y-=6*mm
    title('Relatório final do bingo',20)
    pdf.setFillColor(TEXT); pdf.setFont('Helvetica-Bold',13); pdf.drawString(18*mm,y,evento['nome']); y-=6*mm
    pdf.setFillColor(MUTED); pdf.setFont('Helvetica',8.5); pdf.drawString(18*mm,y,f"Data: {evento['data'] or 'não informada'}  |  Situação: {status_evento_label(evento['status'])}"); y-=11*mm
    title('Resumo financeiro',13)
    line('Cartelas geradas',dados['total']); line('Cartelas impressas',dados['impressas']); line('Lotes físicos',dados['lotes']); line('Cartelas vendidas',dados['vendidas']); line('Cartelas inutilizadas',dados['inutilizadas']); line('Arrecadação bruta',_pdf_money(dados['arrecadacao']),True); line('Recebido nos acertos',_pdf_money(dados['total_recebido'])); line('Saldo a receber',_pdf_money(dados['saldo_receber'])); line('Prêmios configurados/realizados',_pdf_money(dados['premios'])); line('Resultado estimado',_pdf_money(dados['resultado_estimado']),True); line('Estornos registrados na V5',dados['estornos']); line('Fechamentos de caixa',dados['caixa_fechamentos']); line('Diferença acumulada de caixa',_pdf_money(dados['caixa_diferenca']))
    y-=4*mm; title('Prestação de contas por vendedor',13)
    for v in dados['vendedores']:
        line(f"{v['nome']} — {v['vendidas']} vendidas", f"Devido {_pdf_money(v['devido'])} | Saldo {_pdf_money(v['saldo'])}")
    y-=4*mm; title('Rodadas e ganhadores',13)
    if dados['ganhadores']:
        for g in dados['ganhadores']:
            line(f"Cartela {g['numero']:04d} — {g['rodada'] or g['padrao']}", g['comprador'] or 'Comprador não informado')
    else:
        line('Ganhadores confirmados','Nenhum')
    pdf.setFillColor(MUTED); pdf.setFont('Helvetica',7); pdf.drawString(18*mm,10*mm,f"Gerado pelo Bingo Comunidade V11 em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    pdf.save(); buf.seek(0)
    safe=''.join(ch if ch.isalnum() else '_' for ch in evento['nome'])[:45]
    return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=f'relatorio_{safe}.pdf')


BACKUP_DIR = Path(__file__).with_name('backups')

def listar_backups():
    BACKUP_DIR.mkdir(exist_ok=True)
    rows=[]
    for p in sorted(BACKUP_DIR.glob('*.db'), key=lambda x:x.stat().st_mtime, reverse=True):
        st=p.stat(); rows.append({'nome':p.name,'tamanho':st.st_size,'data':datetime.fromtimestamp(st.st_mtime).strftime('%d/%m/%Y %H:%M')})
    return rows


@app.route('/backups')
def backups():
    conn=get_db(); evento=evento_ativo(conn); conn.close()
    return render_template('backups.html', evento=evento, backups=listar_backups())


@app.route('/backups/criar', methods=['POST'])
def backup_criar():
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
    destino=BACKUP_DIR/f'bingo_backup_{stamp}.db'
    src=sqlite3.connect(DB_PATH); dst=sqlite3.connect(destino)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    flash(f'Backup criado: {destino.name}', 'success')
    return redirect(url_for('backups'))


def _backup_path(nome):
    nome=secure_filename(nome)
    if not nome.lower().endswith('.db'):
        return None
    p=(BACKUP_DIR/nome).resolve(); base=BACKUP_DIR.resolve()
    if p.parent != base or not p.exists():
        return None
    return p


@app.route('/backups/<nome>/download')
def backup_download(nome):
    p=_backup_path(nome)
    if not p:
        flash('Backup não encontrado.','danger'); return redirect(url_for('backups'))
    return send_file(p,as_attachment=True,download_name=p.name)


@app.route('/backups/<nome>/restaurar', methods=['POST'])
def backup_restaurar(nome):
    p=_backup_path(nome)
    if not p:
        flash('Backup não encontrado.','danger'); return redirect(url_for('backups'))
    BACKUP_DIR.mkdir(exist_ok=True)
    seguranca=BACKUP_DIR/f"antes_da_restauracao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    if DB_PATH.exists():
        src=sqlite3.connect(DB_PATH); dst=sqlite3.connect(seguranca)
        try: src.backup(dst)
        finally: dst.close(); src.close()
    origem=sqlite3.connect(p); destino=sqlite3.connect(DB_PATH)
    try: origem.backup(destino)
    finally: destino.close(); origem.close()
    init_db(); flash(f'Backup {p.name} restaurado. Uma cópia de segurança foi feita antes da restauração.', 'success')
    return redirect(url_for('backups'))


@app.route('/backups/upload', methods=['POST'])
def backup_upload():
    arq=request.files.get('arquivo')
    if not arq or not arq.filename:
        flash('Selecione um arquivo .db.','warning'); return redirect(url_for('backups'))
    nome=secure_filename(arq.filename)
    if not nome.lower().endswith('.db'):
        flash('O arquivo precisa ter extensão .db.','danger'); return redirect(url_for('backups'))
    BACKUP_DIR.mkdir(exist_ok=True)
    destino=BACKUP_DIR/f"importado_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{nome}"
    arq.save(destino)
    try:
        teste=sqlite3.connect(destino); teste.execute('SELECT name FROM sqlite_master LIMIT 1').fetchone(); teste.close()
    except Exception:
        destino.unlink(missing_ok=True); flash('O arquivo enviado não parece ser um banco SQLite válido.','danger'); return redirect(url_for('backups'))
    flash('Backup importado. Agora você pode restaurá-lo pela lista.', 'success')
    return redirect(url_for('backups'))


# ===== Rotas V5 =====
@app.route('/login', methods=['GET','POST'])
def login():
    if getattr(g, 'usuario', None):
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        usuario = request.form.get('usuario','').strip().lower()
        senha = request.form.get('senha','')
        conn=get_db(); user=conn.execute("SELECT * FROM usuarios WHERE lower(usuario)=? AND ativo=1", (usuario,)).fetchone(); conn.close()
        if user and check_password_hash(user['senha_hash'], senha):
            session.clear(); session['usuario_id']=user['id']
            gravar_auditoria('login','sessao','Login realizado',user['id'],user['nome'],evento_atual_id_safe(),request.remote_addr)
            prox=request.args.get('next')
            if user['obrigar_troca']:
                flash('Primeiro acesso: crie uma nova senha.', 'warning')
                return redirect(url_for('minha_senha'))
            return redirect(prox if prox and prox.startswith('/') else url_for('dashboard'))
        flash('Usuário ou senha inválidos.', 'danger')
    conn=get_db(); first_access=bool(conn.execute("SELECT COUNT(*) c FROM usuarios WHERE usuario='admin' AND obrigar_troca=1 AND ativo=1").fetchone()['c']); conn.close()
    return render_template('login.html', first_access=first_access)


@app.route('/logout')
def logout():
    if getattr(g,'usuario',None):
        gravar_auditoria('logout','sessao','Logout realizado',g.usuario['id'],g.usuario['nome'],evento_atual_id_safe(),request.remote_addr)
    session.clear(); return redirect(url_for('login'))


@app.route('/minha-senha', methods=['GET','POST'])
def minha_senha():
    if not getattr(g,'usuario',None):
        return redirect(url_for('login'))
    conn=get_db(); evento=evento_ativo(conn)
    if request.method=='POST':
        atual=request.form.get('senha_atual',''); nova=request.form.get('nova_senha',''); confirma=request.form.get('confirmar_senha','')
        user=conn.execute("SELECT * FROM usuarios WHERE id=?", (g.usuario['id'],)).fetchone()
        if not check_password_hash(user['senha_hash'], atual):
            flash('A senha atual não confere.', 'danger')
        elif len(nova) < 6:
            flash('A nova senha precisa ter pelo menos 6 caracteres.', 'warning')
        elif nova != confirma:
            flash('A confirmação da nova senha não confere.', 'warning')
        else:
            conn.execute("UPDATE usuarios SET senha_hash=?, obrigar_troca=0 WHERE id=?", (generate_password_hash(nova), user['id']))
            conn.commit(); flash('Senha alterada com sucesso.', 'success')
            conn.close(); return redirect(url_for('dashboard'))
    conn.close(); return render_template('minha_senha.html', evento=evento)


@app.route('/usuarios', methods=['GET','POST'])
def usuarios():
    conn=get_db(); evento=evento_ativo(conn)
    if request.method=='POST':
        nome=request.form.get('nome','').strip(); usuario=request.form.get('usuario','').strip().lower(); senha=request.form.get('senha',''); perfil=request.form.get('perfil','operador')
        if perfil not in PERFIL_LABELS: perfil='operador'
        if not nome or not usuario or len(senha)<6:
            flash('Informe nome, usuário e uma senha com pelo menos 6 caracteres.', 'warning')
        else:
            try:
                conn.execute("""INSERT INTO usuarios (nome,usuario,senha_hash,perfil,ativo,obrigar_troca,criado_em)
                    VALUES (?,?,?,?,1,1,?)""", (nome,usuario,generate_password_hash(senha),perfil,datetime.now().isoformat(timespec='seconds')))
                conn.commit(); flash('Usuário criado. A senha informada será temporária e deverá ser trocada no primeiro acesso.', 'success')
            except sqlite3.IntegrityError:
                flash('Esse nome de usuário já está em uso.', 'danger')
    rows=conn.execute("SELECT * FROM usuarios ORDER BY ativo DESC,nome").fetchall(); conn.close()
    return render_template('usuarios.html', evento=evento, usuarios=rows, perfil_label=perfil_label)


@app.route('/usuarios/<int:usuario_id>/acao', methods=['POST'])
def usuario_acao(usuario_id):
    conn=get_db(); alvo=conn.execute("SELECT * FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
    if not alvo:
        conn.close(); flash('Usuário não encontrado.', 'danger'); return redirect(url_for('usuarios'))
    acao=request.form.get('acao')
    if acao=='desativar':
        if usuario_id==g.usuario['id']:
            flash('Você não pode desativar o próprio usuário.', 'warning')
        elif alvo['perfil']=='admin' and conn.execute("SELECT COUNT(*) c FROM usuarios WHERE perfil='admin' AND ativo=1").fetchone()['c']<=1:
            flash('É necessário manter pelo menos um administrador ativo.', 'warning')
        else:
            conn.execute("UPDATE usuarios SET ativo=0 WHERE id=?", (usuario_id,)); conn.commit(); flash('Usuário desativado.', 'success')
    elif acao=='ativar':
        conn.execute("UPDATE usuarios SET ativo=1 WHERE id=?", (usuario_id,)); conn.commit(); flash('Usuário ativado.', 'success')
    elif acao=='redefinir':
        nova=request.form.get('nova_senha','')
        if len(nova)<6:
            flash('A senha temporária precisa ter pelo menos 6 caracteres.', 'warning')
        else:
            conn.execute("UPDATE usuarios SET senha_hash=?, obrigar_troca=1 WHERE id=?", (generate_password_hash(nova),usuario_id)); conn.commit(); flash('Senha redefinida. O usuário deverá trocá-la no próximo acesso.', 'success')
    elif acao=='perfil':
        perfil=request.form.get('perfil','operador')
        if perfil not in PERFIL_LABELS:
            flash('Perfil inválido.', 'danger')
        elif alvo['perfil']=='admin' and perfil!='admin' and conn.execute("SELECT COUNT(*) c FROM usuarios WHERE perfil='admin' AND ativo=1").fetchone()['c']<=1:
            flash('É necessário manter pelo menos um administrador ativo.', 'warning')
        else:
            conn.execute("UPDATE usuarios SET perfil=? WHERE id=?", (perfil,usuario_id)); conn.commit(); flash('Perfil atualizado.', 'success')
    conn.close(); return redirect(url_for('usuarios'))


@app.route('/vendas/<int:numero>/cancelar', methods=['POST'])
def venda_cancelar(numero):
    conn=get_db(); evento=evento_ativo(conn)
    card=conn.execute("SELECT * FROM cartelas WHERE evento_id=? AND numero=?", (evento['id'],numero)).fetchone()
    if not card or card['status']!='vendida':
        conn.close(); flash('A cartela informada não possui uma venda ativa.', 'warning'); return redirect(url_for('vendas'))
    motivo=request.form.get('motivo','').strip() or 'Cancelamento/estorno'
    agora=datetime.now().isoformat(timespec='seconds'); suid=_novo_sync_uuid()
    conn.execute("""INSERT INTO movimentacoes_vendas (evento_id,cartela_id,numero,tipo,comprador,telefone,pagamento,vendedor_id,usuario_id,motivo,criado_em,origem,sync_uuid,sync_enviado)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (evento['id'],card['id'],numero,'cancelamento',card['comprador'],card['telefone'],card['pagamento'],card['vendedor_id'],usuario_atual_id(),motivo,agora,'painel',suid,0 if BINGO_MODE=='local' else 1))
    conn.execute("""UPDATE cartelas SET status='disponivel',comprador=NULL,telefone=NULL,pagamento=NULL,vendido_em=NULL,vendido_por_usuario_id=NULL WHERE id=?""", (card['id'],))
    if BINGO_MODE=='cloud':
        payload={'sync_uuid':suid,'evento_id':evento['id'],'numero':numero,'tipo':'cancelamento','comprador':card['comprador'],'telefone':card['telefone'],'pagamento':card['pagamento'],'vendedor_id':card['vendedor_id'],'motivo':motivo,'criado_em':agora}
        _registrar_evento_sync(conn,suid,'cancelamento',evento['id'],numero,payload,'nuvem')
    conn.commit(); conn.close(); flash(f'Venda da cartela {numero:04d} cancelada e cartela liberada novamente.', 'success')
    return redirect(url_for('vendas'))


def _caixa_valor_sistema(conn, caixa, evento):
    inicio=caixa['aberto_em']; fim=caixa['fechado_em'] if caixa['fechado_em'] else '9999-12-31T23:59:59'
    vendas=conn.execute("""SELECT COUNT(*) c FROM cartelas WHERE evento_id=? AND status='vendida'
        AND pagamento='Dinheiro' AND vendedor_id IS NULL AND vendido_em IS NOT NULL AND vendido_em BETWEEN ? AND ?""", (evento['id'],inicio,fim)).fetchone()['c']
    venda_valor=vendas*float(evento['valor_cartela'])
    acertos_cash=conn.execute("""SELECT COALESCE(SUM(valor),0) s FROM acertos WHERE evento_id=?
        AND forma_pagamento='Dinheiro' AND criado_em BETWEEN ? AND ?""", (evento['id'],inicio,fim)).fetchone()['s']
    movimentos=conn.execute("""SELECT
        COALESCE(SUM(CASE WHEN tipo='entrada' THEN valor ELSE 0 END),0) entradas,
        COALESCE(SUM(CASE WHEN tipo='saida' THEN valor ELSE 0 END),0) saidas
        FROM caixa_movimentos WHERE caixa_id=?""", (caixa['id'],)).fetchone()
    esperado=float(caixa['valor_inicial'])+venda_valor+float(acertos_cash)+float(movimentos['entradas'])-float(movimentos['saidas'])
    return esperado, vendas, float(acertos_cash), float(movimentos['entradas']), float(movimentos['saidas'])


@app.route('/caixa', methods=['GET','POST'])
def caixa():
    conn=get_db(); evento=evento_ativo(conn); eid=evento['id']
    aberto=conn.execute("SELECT * FROM caixas WHERE evento_id=? AND status='aberto' ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
    if request.method=='POST':
        acao=request.form.get('acao')
        if acao=='abrir' and not aberto:
            try: inicial=float(request.form.get('valor_inicial','0').replace(',','.'))
            except ValueError: inicial=0
            conn.execute("INSERT INTO caixas (evento_id,aberto_por,aberto_em,valor_inicial,status) VALUES (?,?,?,?, 'aberto')", (eid,usuario_atual_id(),datetime.now().isoformat(timespec='seconds'),max(inicial,0)))
            conn.commit(); flash('Caixa aberto.', 'success')
        elif acao=='movimento' and aberto:
            tipo=request.form.get('tipo','entrada'); descricao=request.form.get('descricao','').strip()
            try: valor=float(request.form.get('valor','0').replace(',','.'))
            except ValueError: valor=0
            if tipo not in {'entrada','saida'} or valor<=0 or not descricao:
                flash('Informe tipo, descrição e um valor válido.', 'warning')
            else:
                conn.execute("INSERT INTO caixa_movimentos (caixa_id,evento_id,tipo,descricao,valor,usuario_id,criado_em) VALUES (?,?,?,?,?,?,?)", (aberto['id'],eid,tipo,descricao,valor,usuario_atual_id(),datetime.now().isoformat(timespec='seconds')))
                conn.commit(); flash('Movimento registrado no caixa.', 'success')
        elif acao=='fechar' and aberto:
            try: contado=float(request.form.get('valor_informado','0').replace(',','.'))
            except ValueError: contado=0
            obs=request.form.get('observacao','').strip(); esperado,_,_,_,_=_caixa_valor_sistema(conn,aberto,evento); dif=contado-esperado
            conn.execute("""UPDATE caixas SET status='fechado',fechado_por=?,fechado_em=?,valor_informado=?,valor_sistema=?,diferenca=?,observacao=? WHERE id=?""", (usuario_atual_id(),datetime.now().isoformat(timespec='seconds'),contado,esperado,dif,obs,aberto['id']))
            conn.commit(); flash(f'Caixa fechado. Diferença: R$ {dif:.2f}.', 'success')
        return redirect(url_for('caixa'))
    aberto=conn.execute("SELECT * FROM caixas WHERE evento_id=? AND status='aberto' ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
    esperado=vendas_dinheiro=acertos_dinheiro=entradas=saidas=0
    movimentos=[]
    if aberto:
        esperado,vendas_dinheiro,acertos_dinheiro,entradas,saidas=_caixa_valor_sistema(conn,aberto,evento)
        movimentos=conn.execute("SELECT * FROM caixa_movimentos WHERE caixa_id=? ORDER BY id DESC", (aberto['id'],)).fetchall()
    historico=conn.execute("""SELECT c.*,ua.nome aberto_nome,uf.nome fechado_nome FROM caixas c
        LEFT JOIN usuarios ua ON ua.id=c.aberto_por LEFT JOIN usuarios uf ON uf.id=c.fechado_por
        WHERE c.evento_id=? AND c.status='fechado' ORDER BY c.id DESC LIMIT 15""", (eid,)).fetchall()
    conn.close(); return render_template('caixa.html',evento=evento,aberto=aberto,esperado=esperado,vendas_dinheiro=vendas_dinheiro,acertos_dinheiro=acertos_dinheiro,entradas=entradas,saidas=saidas,movimentos=movimentos,historico=historico)


@app.route('/auditoria')
def auditoria():
    conn=get_db(); evento=evento_ativo(conn)
    q=request.args.get('q','').strip(); usuario=request.args.get('usuario','').strip(); acao=request.args.get('acao','').strip(); todos=request.args.get('todos')=='1' and g.usuario['perfil']=='admin'
    sql="SELECT a.*,e.nome evento_nome FROM auditoria a LEFT JOIN eventos e ON e.id=a.evento_id WHERE 1=1"; params=[]
    if not todos:
        sql += " AND a.evento_id=?"; params.append(evento['id'])
    if q:
        sql += " AND (a.detalhes LIKE ? OR a.entidade LIKE ? OR a.usuario_nome LIKE ?)"; params += [f'%{q}%']*3
    if usuario:
        sql += " AND a.usuario_nome LIKE ?"; params.append(f'%{usuario}%')
    if acao:
        sql += " AND a.acao LIKE ?"; params.append(f'%{acao}%')
    sql += " ORDER BY a.id DESC LIMIT 300"
    rows=conn.execute(sql,params).fetchall(); conn.close()
    return render_template('auditoria.html',evento=evento,registros=rows,q=q,usuario=usuario,acao=acao,todos=todos)


if __name__ == '__main__':
    init_db()
    print('='*72)
    print(f'BINGO COMUNIDADE - {SYSTEM_BUILD}')
    print(f'TEMPLATE OFICIAL: {CARD_TEMPLATE_PATH}')
    print(f'PORTA DESTA VERSAO: {SYSTEM_PORT}')
    print('='*72)
    start_sync_worker()
    app.run(host='0.0.0.0', port=SYSTEM_PORT, debug=False, use_reloader=False)
