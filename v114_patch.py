"""Ajustes V11.4 aplicados ao servidor online sem reescrever o app principal.

- escolha entre sorteador do sistema e globo físico;
- bloqueio do sorteio automático quando o globo estiver ativo;
- lista completa de ganhadores no estado enviado ao telão.
"""
from functools import wraps

from flask import request, redirect, url_for, flash, jsonify


def install(bingo):
    """Instala os ajustes V11.4 sobre as rotas já existentes."""
    conn = bingo.get_db()
    cols = {r['name'] for r in conn.execute("PRAGMA table_info(eventos)").fetchall()}
    if 'modo_sorteio' not in cols:
        conn.execute("ALTER TABLE eventos ADD COLUMN modo_sorteio TEXT")
        conn.commit()
    conn.close()

    original_evento_acao = bingo.app.view_functions.get('sorteio_evento_acao')
    if original_evento_acao:
        @wraps(original_evento_acao)
        def sorteio_evento_acao_v114(evento_id):
            acao = request.form.get('acao')
            if acao == 'iniciar':
                conn = bingo.get_db()
                alvo = conn.execute("SELECT * FROM eventos WHERE id=?", (evento_id,)).fetchone()
                if alvo and alvo['status'] == 'preparacao':
                    modo = (request.form.get('modo_sorteio') or '').strip().lower()
                    if modo not in ('sistema', 'globo'):
                        conn.close()
                        flash('Escolha como os números serão sorteados antes de iniciar o evento.', 'warning')
                        return redirect(url_for('sorteio'))
                    conn.execute(
                        "UPDATE eventos SET status='em_andamento',encerrado_em=NULL,modo_sorteio=? WHERE id=?",
                        (modo, evento_id),
                    )
                    conn.commit()
                    conn.close()
                    if modo == 'globo':
                        flash('Evento iniciado no modo Globo físico. O botão “Sortear número” ficará oculto.', 'success')
                    else:
                        flash('Evento iniciado usando o sorteador do sistema. Bom bingo!', 'success')
                    return redirect(url_for('sorteio'))
                conn.close()
            return original_evento_acao(evento_id)

        bingo.app.view_functions['sorteio_evento_acao'] = sorteio_evento_acao_v114

    original_sorteio = bingo.app.view_functions.get('sorteio')
    if original_sorteio:
        @wraps(original_sorteio)
        def sorteio_v114():
            if request.method == 'POST' and request.form.get('acao') == 'sortear':
                conn = bingo.get_db()
                evento = bingo.evento_ativo(conn)
                modo = evento['modo_sorteio'] if evento and 'modo_sorteio' in evento.keys() else None
                conn.close()
                if modo == 'globo':
                    flash('Sorteio automático bloqueado: este evento foi iniciado no modo Globo físico.', 'warning')
                    return redirect(url_for('sorteio'))
            return original_sorteio()

        bingo.app.view_functions['sorteio'] = sorteio_v114

    original_api = bingo.app.view_functions.get('api_estado_sorteio')
    if original_api:
        @wraps(original_api)
        def api_estado_sorteio_v114():
            resposta = original_api()
            try:
                dados = resposta.get_json()
            except Exception:
                return resposta

            conn = bingo.get_db()
            evento = bingo.evento_ativo(conn)
            rows = conn.execute(
                """SELECT g.id,c.numero,c.comprador,r.nome rodada,r.ordem,r.premio
                   FROM ganhadores g
                   JOIN cartelas c ON c.id=g.cartela_id
                   LEFT JOIN rodadas r ON r.id=g.rodada_id
                   WHERE g.evento_id=? AND g.confirmado=1
                   ORDER BY COALESCE(r.ordem,9999),g.id""",
                (evento['id'],),
            ).fetchall()
            conn.close()
            dados['ganhadores'] = [
                {
                    'id': w['id'],
                    'numero': w['numero'],
                    'comprador': w['comprador'] or 'Comprador não informado',
                    'rodada': w['rodada'] or 'Prêmio',
                    'ordem': w['ordem'],
                    'premio': float(w['premio'] or 0),
                }
                for w in rows
            ]
            return jsonify(dados)

        bingo.app.view_functions['api_estado_sorteio'] = api_estado_sorteio_v114
