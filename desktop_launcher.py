from __future__ import annotations
import os
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


def runtime_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = runtime_dir()
DB_PATH = BASE_DIR / 'bingo.db'
PORT_FILE = BASE_DIR / '.porta_ativa.txt'
SECRET_FILE = BASE_DIR / '.secret_key'
PORTA_PADRAO = 8765

os.environ['BINGO_DB_PATH'] = str(DB_PATH)
os.environ['BINGO_MODE'] = 'local'
if SECRET_FILE.exists() and not os.environ.get('BINGO_SECRET_KEY'):
    try:
        os.environ['BINGO_SECRET_KEY'] = SECRET_FILE.read_text(encoding='utf-8').strip()
    except Exception:
        pass


def servidor_bingo_ativo(porta: int) -> bool:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{porta}/health', timeout=.8) as r:
            return r.status == 200
    except Exception:
        return False


def porta_servidor_existente():
    candidatos = []
    try:
        if PORT_FILE.exists():
            candidatos.append(int(PORT_FILE.read_text(encoding='utf-8').strip()))
    except Exception:
        pass
    candidatos.append(PORTA_PADRAO)
    vistos = set()
    for porta in candidatos:
        if porta in vistos:
            continue
        vistos.add(porta)
        if servidor_bingo_ativo(porta):
            return porta
    return None


def porta_livre(inicio=PORTA_PADRAO, fim=8899):
    for porta in range(inicio, fim + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', porta))
                return porta
            except OSError:
                continue
    raise RuntimeError('Nenhuma porta livre encontrada entre 8765 e 8899.')


def ip_rede_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'


def abrir_janela_app(porta: int):
    """Abre o Bingo como aplicativo Windows, sem barra/endereço do navegador."""
    import webview

    url = f'http://127.0.0.1:{porta}/'
    webview.create_window(
        'Bingo Comunidade',
        url,
        width=1380,
        height=860,
        min_size=(960, 640),
        resizable=True,
        fullscreen=False,
        confirm_close=False,
    )
    # No Windows o pywebview usa preferencialmente o Microsoft Edge WebView2.
    webview.start(debug=False)


PORTA_EXISTENTE = porta_servidor_existente()
PORTA = PORTA_EXISTENTE or porta_livre()
os.environ['BINGO_PORT'] = str(PORTA)

import app as bingo  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


class ServidorBingo(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.httpd = make_server('0.0.0.0', PORTA, bingo.app, threaded=True)

    def run(self):
        self.httpd.serve_forever()

    def parar(self):
        self.httpd.shutdown()


class JanelaCentral(tk.Tk):
    def __init__(self, servidor=None):
        super().__init__()
        self.servidor = servidor
        self.title('Bingo Comunidade — Central')
        self.geometry('570x430')
        self.minsize(540, 410)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.url_local = f'http://127.0.0.1:{PORTA}'
        self.url_rede = f'http://{ip_rede_local()}:{PORTA}'
        frame = tk.Frame(self, padx=28, pady=24)
        frame.pack(fill='both', expand=True)
        tk.Label(frame, text='Bingo Comunidade', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        tk.Label(frame, text='Central administrativa do servidor local', font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 20))
        tk.Label(frame, text=f'● Servidor ativo na porta {PORTA}', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 12))
        tk.Label(frame, text='Banco oficial:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        tk.Label(frame, text=str(DB_PATH), wraplength=500, justify='left', font=('Segoe UI', 9)).pack(anchor='w', pady=(0, 12))
        tk.Label(frame, text='Acesso neste computador:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        tk.Label(frame, text=self.url_local, font=('Segoe UI', 10)).pack(anchor='w')
        tk.Label(frame, text='Acesso na mesma rede Wi-Fi:', font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(10, 0))
        tk.Label(frame, text=self.url_rede, font=('Segoe UI', 10)).pack(anchor='w')
        tk.Label(frame, text='Esta central é opcional. O uso normal é pelo atalho do Bingo Comunidade, que abre a janela do aplicativo diretamente.', font=('Segoe UI', 9), wraplength=500, justify='left').pack(anchor='w', pady=(18, 0))


def preparar_bingo():
    banco_existia = DB_PATH.exists()
    bingo.init_db()
    try:
        import v114_patch
        v114_patch.install(bingo)
    except Exception:
        pass
    try:
        import pwa_patch
        pwa_patch.install(bingo)
    except Exception:
        pass
    bingo.start_sync_worker()
    return banco_existia


def iniciar_servidor():
    banco_existia = preparar_bingo()
    servidor = ServidorBingo()
    servidor.start()
    for _ in range(80):
        if servidor_bingo_ativo(PORTA):
            PORT_FILE.write_text(str(PORTA), encoding='utf-8')
            return servidor, banco_existia
        time.sleep(.25)
    servidor.parar()
    raise RuntimeError('O servidor não respondeu a tempo.')


def mostrar_erro(texto):
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror('Bingo Comunidade', texto)
    root.destroy()


def avisar_banco_novo():
    root = tk.Tk()
    root.withdraw()
    messagebox.showwarning(
        'Bingo Comunidade',
        'ATENÇÃO: não foi encontrado bingo.db ao lado do EXE. Um banco novo foi criado.\n\n'
        'Se este computador possui o banco oficial das 500 cartelas, feche o programa e coloque o bingo.db correto ao lado do EXE.'
    )
    root.destroy()


def main():
    # Central administrativa opcional: Bingo Comunidade.exe --central
    if '--central' in sys.argv:
        servidor = None
        if PORTA_EXISTENTE is None:
            try:
                servidor, _ = iniciar_servidor()
            except Exception as exc:
                mostrar_erro(str(exc))
                return
        JanelaCentral(servidor).mainloop()
        return

    # Se já existe um servidor do Bingo rodando, apenas abre uma nova janela nativa.
    if PORTA_EXISTENTE is not None:
        try:
            abrir_janela_app(PORTA_EXISTENTE)
        except Exception as exc:
            mostrar_erro(f'Não foi possível abrir a janela do aplicativo.\n\n{exc}')
        return

    servidor = None
    try:
        servidor, banco_existia = iniciar_servidor()
        if not banco_existia:
            avisar_banco_novo()
        abrir_janela_app(PORTA)
    except Exception as exc:
        mostrar_erro(str(exc))
    finally:
        # Fechar a janela principal encerra o servidor local, como um programa normal.
        if servidor:
            try:
                servidor.parar()
            except Exception:
                pass
        try:
            PORT_FILE.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == '__main__':
    main()
