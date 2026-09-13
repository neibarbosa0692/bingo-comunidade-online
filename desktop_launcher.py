from __future__ import annotations
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
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


def abrir_sistema(porta: int):
    webbrowser.open(f'http://127.0.0.1:{porta}/')


# Segundo clique: se o servidor já está ativo, apenas abre o sistema e termina.
PORTA_EXISTENTE = porta_servidor_existente()
if PORTA_EXISTENTE is not None and '--central' not in sys.argv:
    abrir_sistema(PORTA_EXISTENTE)
    raise SystemExit(0)

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
    def __init__(self, servidor):
        super().__init__()
        self.servidor = servidor
        self.title('Bingo Comunidade — Central')
        self.geometry('570x430')
        self.minsize(540, 410)
        self.protocol('WM_DELETE_WINDOW', self.ocultar)
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
        botoes = tk.Frame(frame)
        botoes.pack(fill='x', pady=(22, 8))
        for texto, rota in [('Abrir sistema', '/'), ('Abrir cartelas', '/cartelas'), ('Abrir telão', '/telao'), ('Backups', '/backups')]:
            tk.Button(botoes, text=texto, command=lambda r=rota: webbrowser.open(self.url_local+r), padx=12, pady=8).pack(side='left', padx=(0, 8))
        tk.Button(frame, text='Encerrar Bingo Comunidade', command=self.encerrar, padx=12, pady=8).pack(anchor='w', pady=(10, 0))
        tk.Label(frame, text='Fechar esta janela apenas a oculta. O servidor continua funcionando para o computador, celulares e telão.', font=('Segoe UI', 9), wraplength=500, justify='left').pack(anchor='w', pady=(18, 0))

    def ocultar(self):
        self.withdraw()

    def encerrar(self):
        if messagebox.askyesno('Encerrar', 'Deseja encerrar o servidor do Bingo Comunidade?'):
            try:
                self.servidor.parar()
                try:
                    PORT_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
            finally:
                self.destroy()


def iniciar_servidor():
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
    servidor = ServidorBingo()
    servidor.start()
    url = f'http://127.0.0.1:{PORTA}'
    for _ in range(80):
        if servidor_bingo_ativo(PORTA):
            PORT_FILE.write_text(str(PORTA), encoding='utf-8')
            return servidor, banco_existia
        time.sleep(.25)
    servidor.parar()
    raise RuntimeError('O servidor não respondeu a tempo.')


def main():
    # --central continua disponível para manutenção, mas não faz parte do uso normal.
    if PORTA_EXISTENTE is not None:
        abrir_sistema(PORTA_EXISTENTE)
        return
    try:
        servidor, banco_existia = iniciar_servidor()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror('Bingo Comunidade', str(exc))
        root.destroy()
        return

    abrir_sistema(PORTA)

    # Mantemos um loop Tk invisível para que o processo continue vivo sem janela.
    central = JanelaCentral(servidor)
    if '--central' not in sys.argv:
        central.withdraw()
    if not banco_existia:
        central.deiconify()
        messagebox.showwarning(
            'Bingo Comunidade',
            'ATENÇÃO: não foi encontrado bingo.db ao lado do EXE. Um banco novo foi criado.\n\n'
            'Se este computador possui o banco oficial das 500 cartelas, feche o programa e coloque o bingo.db correto ao lado do EXE.'
        )
    central.mainloop()


if __name__ == '__main__':
    main()
