"""Pós-bingo: histórico imutável das rodadas e consulta pública pelo QR já impresso.

Este módulo é deliberadamente aditivo: NÃO altera numeros, numero ou id das cartelas.
Os 500 QR Codes existentes continuam apontando para /m/<evento>/<numero>.
"""
from __future__ import annotations

from functools import wraps
import json
import threading

from flask import jsonify, request


def install(bingo):
    if getattr(bingo.app, '_post_bingo_installed', False):
        return

    conn = bingo.get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resultado_rodadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento_id INTEGER NOT NULL,
            rodada_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            padrao TEXT NOT NULL,
            premio REAL NOT NULL DEFAULT 0,
            numeros_json TEXT NOT NULL,
            finalizada_em TEXT NOT NULL,
            UNIQUE(evento_id, rodada_id)
        )
    """)
    conn.commit(); conn.close()

    def salvar_snapshot_rodada(rodada_id):
        conn = bingo.get_db()
        rodada = conn.execute("SELECT * FROM rodadas WHERE id=?", (rodada_id,)).fetchone()
        if not rodada:
            conn.close(); return
        numeros = [r['numero'] for r in conn.execute(
            "SELECT numero FROM sorteios WHERE evento_id=? ORDER BY ordem,id", (rodada['evento_id'],)
        ).fetchall()]
        conn.execute("""INSERT INTO resultado_rodadas
            (evento_id,rodada_id,nome,padrao,premio,numeros_json,finalizada_em)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(evento_id,rodada_id) DO UPDATE SET
              nome=excluded.nome,padrao=excluded.padrao,premio=excluded.premio,
              numeros_json=excluded.numeros_json,finalizada_em=excluded.finalizada_em""",
            (rodada['evento_id'], rodada['id'], rodada['nome'], rodada['padrao'],
             float(rodada['premio'] or 0), json.dumps(numeros), bingo.iso_brasilia()))
        conn.commit(); conn.close()

    # Captura os números ANTES de a rodada ser finalizada. Nada é escrito em cartelas.
    original_rodada_acao = bingo.app.view_functions.get('rodada_acao')
    if original_rodada_acao:
        @wraps(original_rodada_acao)
        def rodada_acao_pos_bingo(rodada_id):
            if request.method == 'POST' and request.form.get('acao') == 'finalizar':
                salvar_snapshot_rodada(rodada_id)
            resposta = original_rodada_acao(rodada_id)
            if request.method == 'POST' and request.form.get('acao') == 'finalizar' and bingo.BINGO_MODE == 'local':
                # Envia também o histórico à nuvem quando a sincronização estiver configurada.
                def sincronizar():
                    try: bingo.sync_cycle(full=True)
                    except Exception: pass
                threading.Thread(target=sincronizar, daemon=True).start()
            return resposta
        bingo.app.view_functions['rodada_acao'] = rodada_acao_pos_bingo

    # Acrescenta o histórico ao snapshot já existente. Não muda o tratamento das cartelas.
    original_snapshot = bingo._snapshot_local
    def snapshot_com_resultados():
        snap = original_snapshot()
        evento = snap.get('evento') or {}
        eid = evento.get('id')
        if eid:
            conn = bingo.get_db()
            snap['resultados_rodadas'] = [dict(r) for r in conn.execute(
                "SELECT * FROM resultado_rodadas WHERE evento_id=? ORDER BY rodada_id,id", (eid,)
            ).fetchall()]
            # Rodadas/ganhadores são pequenos e necessários para a consulta pública.
            snap['rodadas_resultado'] = [dict(r) for r in conn.execute(
                "SELECT * FROM rodadas WHERE evento_id=? ORDER BY ordem,id", (eid,)
            ).fetchall()]
            snap['ganhadores_resultado'] = [dict(r) for r in conn.execute(
                "SELECT * FROM ganhadores WHERE evento_id=? AND confirmado=1 ORDER BY id", (eid,)
            ).fetchall()]
            conn.close()
        return snap
    bingo._snapshot_local = snapshot_com_resultados

    original_cloud_apply = bingo._cloud_aplicar_snapshot
    def cloud_apply_com_resultados(snapshot):
        resultado = original_cloud_apply(snapshot)
        if not resultado.get('ok'):
            return resultado
        evento = snapshot.get('evento') or {}; eid = int(evento.get('id') or 0)
        if not eid: return resultado
        conn = bingo.get_db()
        for r in snapshot.get('rodadas_resultado') or []:
            rid = int(r.get('id') or 0)
            if not rid: continue
            atual = conn.execute("SELECT id FROM rodadas WHERE id=?", (rid,)).fetchone()
            vals=(eid,r.get('nome') or 'Rodada',r.get('padrao') or 'cartela_cheia',float(r.get('premio') or 0),int(r.get('ordem') or 1),r.get('status') or 'pendente')
            if atual:
                conn.execute("UPDATE rodadas SET evento_id=?,nome=?,padrao=?,premio=?,ordem=?,status=? WHERE id=?", vals+(rid,))
            else:
                conn.execute("INSERT INTO rodadas (id,evento_id,nome,padrao,premio,ordem,status) VALUES (?,?,?,?,?,?,?)", (rid,)+vals)
        for h in snapshot.get('ganhadores_resultado') or []:
            hid=int(h.get('id') or 0); cid=int(h.get('cartela_id') or 0)
            if not hid or not cid: continue
            if not conn.execute("SELECT id FROM ganhadores WHERE id=?", (hid,)).fetchone():
                conn.execute("INSERT INTO ganhadores (id,evento_id,cartela_id,padrao,confirmado,rodada_id) VALUES (?,?,?,?,?,?)",
                             (hid,eid,cid,h.get('padrao') or 'cartela_cheia',1,h.get('rodada_id')))
        for r in snapshot.get('resultados_rodadas') or []:
            conn.execute("""INSERT INTO resultado_rodadas
                (evento_id,rodada_id,nome,padrao,premio,numeros_json,finalizada_em)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(evento_id,rodada_id) DO UPDATE SET
                  nome=excluded.nome,padrao=excluded.padrao,premio=excluded.premio,
                  numeros_json=excluded.numeros_json,finalizada_em=excluded.finalizada_em""",
                (eid,int(r.get('rodada_id') or 0),r.get('nome') or 'Rodada',r.get('padrao') or 'cartela_cheia',
                 float(r.get('premio') or 0),r.get('numeros_json') or '[]',r.get('finalizada_em') or bingo.iso_brasilia()))
        conn.commit(); conn.close()
        return resultado
    bingo._cloud_aplicar_snapshot = cloud_apply_com_resultados

    def api_resultado_cartela(evento_id, numero):
        conn=bingo.get_db()
        evento=conn.execute("SELECT * FROM eventos WHERE id=?",(evento_id,)).fetchone()
        card=conn.execute("""SELECT c.*,v.nome vendedor FROM cartelas c LEFT JOIN vendedores v ON v.id=c.vendedor_id
                             WHERE c.evento_id=? AND c.numero=?""",(evento_id,numero)).fetchone()
        if not evento or not card:
            conn.close(); return jsonify({'ok':False,'message':'Cartela não encontrada.'}),404
        grade=json.loads(card['numeros'])
        snapshots=conn.execute("SELECT * FROM resultado_rodadas WHERE evento_id=? ORDER BY rodada_id,id",(evento_id,)).fetchall()
        rodadas=[]
        for r in snapshots:
            nums=json.loads(r['numeros_json'] or '[]'); chamados=set(nums)
            marcados=sorted({n for row in grade for n in row if n and n in chamados})
            vencedor=bool(conn.execute("SELECT 1 FROM ganhadores WHERE evento_id=? AND rodada_id=? AND cartela_id=? AND confirmado=1 LIMIT 1",
                                      (evento_id,r['rodada_id'],card['id'])).fetchone())
            rodadas.append({'id':r['rodada_id'],'nome':r['nome'],'padrao':bingo.padrao_label(r['padrao']),
                            'premio':float(r['premio'] or 0),'numeros':nums,'marcados':marcados,
                            'quantidade_marcados':len(marcados),'vencedora':vencedor,'finalizada_em':r['finalizada_em']})
        pagamento=(card['pagamento'] or '').strip()
        conn.close()
        return jsonify({'ok':True,'evento':evento['nome'],'cartela':{'numero':card['numero'],'status':card['status'],
            'valida':card['status']=='vendida','comprador':card['comprador'] or 'Não informado','vendedor':card['vendedor'] or 'Não informado',
            'pagamento':pagamento or 'Não informado','pagamento_registrado':bool(pagamento),'grade':grade},'rodadas':rodadas})

    endpoint='api_publica_resultado_cartela'
    if endpoint not in bingo.app.view_functions:
        bingo.app.add_url_rule('/api/publico/cartela/<int:evento_id>/<int:numero>/resultados', endpoint, api_resultado_cartela)
    try: bingo.PUBLIC_ENDPOINTS.add(endpoint)
    except Exception: pass

    # A própria página do QR recebe a seção pós-bingo. Os QR Codes impressos não mudam.
    if not getattr(bingo.app, '_post_bingo_html', False):
        @bingo.app.after_request
        def injetar_pos_bingo(response):
            if response.status_code==200 and request.path.startswith('/m/') and 'text/html' in (response.content_type or '').lower() and not response.direct_passthrough:
                try:
                    partes=request.path.strip('/').split('/')
                    if len(partes)==3 and partes[0]=='m':
                        eid=int(partes[1]); numero=int(partes[2])
                        html=response.get_data(as_text=True)
                        bloco=f'''<section id="posBingoResultado" class="mobile-card" style="display:none"><span class="eyebrow">RESULTADO OFICIAL</span><h2>Resultado da minha cartela</h2><div id="posBingoConteudo"></div></section>
<script>(async()=>{{try{{const r=await fetch('/api/publico/cartela/{eid}/{numero}/resultados',{{cache:'no-store'}});const d=await r.json();if(!d.ok||!d.rodadas||!d.rodadas.length)return;const box=document.getElementById('posBingoResultado'),c=document.getElementById('posBingoConteudo');box.style.display='block';const status=d.cartela.valida?'✓ Cartela oficial válida para premiação':'⚠ Cartela não registrada como vendida';let h=`<div style="padding:12px;border-radius:12px;background:#f5f7fb;margin-bottom:14px"><b>${{status}}</b><br><small>Comprador: ${{d.cartela.comprador}} • Vendedor: ${{d.cartela.vendedor}} • Pagamento: ${{d.cartela.pagamento}}</small></div>`;for(const rd of d.rodadas){{const set=new Set(rd.numeros),g=d.cartela.grade;h+=`<div style="border-top:1px solid #e4e8f0;padding-top:14px;margin-top:14px"><b>${{rd.nome}}</b><br><small>${{rd.padrao}} • ${{rd.numeros.length}} números chamados</small>${{rd.vencedora?'<div class="mobile-winner" style="margin-top:8px">🏆 CARTELA VENCEDORA</div>':'<div class="mobile-notwinner" style="margin-top:8px">Não premiada nesta rodada</div>'}}<div class="mobile-bingo-grid" style="margin-top:10px"><div class="mobile-bingo-head"><b>B</b><b>I</b><b>N</b><b>G</b><b>O</b></div>${{g.map(row=>`<div class="mobile-bingo-row">${{row.map(n=>`<span class="${{n===0?'free logo-free':(set.has(n)?'hit':'')}}" style="${{set.has(n)&&n!==0?'background:#dff7e9;color:#087443;font-weight:800':''}}">${{n===0?'★':n}}</span>`).join('')}}</div>`).join('')}}</div><details style="margin-top:8px"><summary>Ver números chamados nesta rodada</summary><p style="line-height:1.7">${{rd.numeros.join(' • ')}}</p></details></div>`}}c.innerHTML=h}}catch(e){{}}}})();</script>'''
                        html=html.replace('</main>',bloco+'</main>',1)
                        response.set_data(html); response.headers['Content-Length']=len(response.get_data())
                except Exception: pass
            return response
        bingo.app._post_bingo_html=True

    # V2 pós-bingo: reconstrução manual segura para eventos já encerrados.\n    # Não altera cartelas, vendas, sorteios ou ganhadores; apenas registra o snapshot histórico.\n    def _normalizar_numeros_historico(raw):\n        vals=[]\n        for parte in str(raw or '').replace(';',',').replace('\\n',',').split(','):\n            parte=parte.strip()\n            if not parte: continue\n            try: n=int(parte)\n            except ValueError: continue\n            if 1 <= n <= 75 and n not in vals: vals.append(n)\n        return vals\n\n    @bingo.app.route('/pos-bingo', methods=['GET','POST'])\n    def pos_bingo_admin():\n        conn=bingo.get_db(); evento=bingo.evento_ativo(conn)\n        if not evento:\n            conn.close(); return 'Nenhum evento ativo.', 404\n        if request.method=='POST':\n            rodada_id=int(request.form.get('rodada_id') or 0)\n            rodada=conn.execute('SELECT * FROM rodadas WHERE id=? AND evento_id=?',(rodada_id,evento['id'])).fetchone()\n            if not rodada:\n                conn.close(); return 'Rodada não encontrada.',404\n            nums=_normalizar_numeros_historico(request.form.get('numeros',''))\n            if not nums:\n                conn.close(); return 'Informe pelo menos um número sorteado.',400\n            conn.execute('''INSERT INTO resultado_rodadas (evento_id,rodada_id,nome,padrao,premio,numeros_json,finalizada_em)\n                VALUES (?,?,?,?,?,?,?) ON CONFLICT(evento_id,rodada_id) DO UPDATE SET\n                nome=excluded.nome,padrao=excluded.padrao,premio=excluded.premio,\n                numeros_json=excluded.numeros_json,finalizada_em=excluded.finalizada_em''',\n                (evento['id'],rodada['id'],rodada['nome'],rodada['padrao'],float(rodada['premio'] or 0),json.dumps(nums),request.form.get('finalizada_em') or bingo.iso_brasilia()))\n            conn.commit()\n        rodadas=conn.execute('SELECT r.*,h.numeros_json,h.finalizada_em historico_em FROM rodadas r LEFT JOIN resultado_rodadas h ON h.rodada_id=r.id AND h.evento_id=r.evento_id WHERE r.evento_id=? ORDER BY r.ordem,r.id',(evento['id'],)).fetchall()\n        conn.close()\n        linhas=[]\n        for r in rodadas:\n            nums=json.loads(r['numeros_json'] or '[]') if r['numeros_json'] else []\n            linhas.append(f'''<section style="background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:18px;margin:14px 0;box-shadow:0 4px 16px rgba(15,23,42,.06)"><h2 style="margin:0 0 6px">{r['ordem']}ª — {r['nome']}</h2><p style="margin:0 0 12px;color:#64748b">{bingo.padrao_label(r['padrao'])} • Prêmio: R$ {float(r['premio'] or 0):.2f}</p><form method="post"><input type="hidden" name="rodada_id" value="{r['id']}"><label style="font-weight:700">Números sorteados nesta rodada</label><textarea name="numeros" rows="4" style="width:100%;box-sizing:border-box;margin-top:8px;padding:12px;border:1px solid #cbd5e1;border-radius:10px" placeholder="Ex.: 03, 08, 12, 17, 21">{', '.join(f'{n:02d}' for n in nums)}</textarea><button style="margin-top:10px;padding:11px 16px;border:0;border-radius:10px;background:#0f766e;color:#fff;font-weight:700">Salvar histórico desta rodada</button></form>{'<p style="color:#0f766e;font-weight:700;margin-bottom:0">✓ Histórico registrado</p>' if nums else '<p style="color:#b45309;margin-bottom:0">⚠ Histórico ainda não registrado</p>'}</section>''')\n        html=f'''<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pós-bingo</title></head><body style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:#f8fafc;margin:0;color:#0f172a"><main style="max-width:820px;margin:0 auto;padding:28px 18px"><div style="background:#0f172a;color:#fff;border-radius:18px;padding:22px"><div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.75">Bingo Comunidade • Pós-bingo</div><h1 style="margin:8px 0">Histórico oficial — {evento['nome']}</h1><p style="margin:0;opacity:.85">Registre os números de cada rodada sem alterar cartelas, vendas ou resultados financeiros.</p></div>{''.join(linhas)}<p style="color:#64748b;font-size:13px">Os QR Codes já impressos continuam válidos. Depois de salvar, o comprador poderá consultar o histórico pelo QR da própria cartela.</p></main></body></html>'''
        return html\n\n    try: bingo.PUBLIC_ENDPOINTS.add('pos_bingo_admin')\n    except Exception: pass\n\n    bingo.app._post_bingo_installed=True
