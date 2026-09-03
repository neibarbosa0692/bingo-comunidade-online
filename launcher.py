from __future__ import annotations
import os
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PORT_FILE = BASE_DIR / '.porta_ativa.txt'


def porta_livre(inicio=8765, fim=8899):
    for porta in range(inicio, fim + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', porta))
            except OSError:
                continue
            return porta
    raise RuntimeError('Nenhuma porta livre encontrada entre 8765 e 8899.')


PORTA = porta_livre()
os.environ['BINGO_PORT'] = str(PORTA)
os.environ['BINGO_MODE'] = 'local'

# O import acontece só depois de definir BINGO_PORT.
import app as bingo  # noqa: E402


def abrir_navegador_quando_pronto():
    health = f'http://127.0.0.1:{PORTA}/health'
    destino = f'http://127.0.0.1:{PORTA}/cartelas'
    for _ in range(80):
        try:
            with urllib.request.urlopen(health, timeout=1.0) as r:
                if r.status == 200:
                    PORT_FILE.write_text(str(PORTA), encoding='utf-8')
                    print(f'\nSISTEMA PRONTO: {destino}')
                    print('O navegador será aberto agora.\n')
                    webbrowser.open(destino, new=1)
                    return
        except Exception:
            time.sleep(0.25)
    print('\nERRO: o servidor não respondeu a tempo.')
    print(f'Tente abrir manualmente: {destino}\n')


if __name__ == '__main__':
    print('=' * 72)
    print('BINGO COMUNIDADE - V11 HÍBRIDO ONLINE + OFFLINE')
    print(f'Porta livre escolhida automaticamente: {PORTA}')
    print(f'Template: {bingo.CARD_TEMPLATE_PATH}')
    print('O navegador só será aberto depois que /health responder OK.')
    print('=' * 72)
    threading.Thread(target=abrir_navegador_quando_pronto, daemon=True).start()
    bingo.init_db()
    bingo.start_sync_worker()
    bingo.app.run(host='0.0.0.0', port=PORTA, debug=False, use_reloader=False)
