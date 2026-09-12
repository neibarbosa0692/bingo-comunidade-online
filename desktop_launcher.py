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

os.environ['BINGO_DB_PATH'] = str(DB_PATH)
os.environ['BINGO_MODE'] = 'local'
if SECRET_FILE.exists() and not os.environ.get('BINGO_SECRET_KEY'):
    try:
        os.environ['BINGO_SECRET_KEY'] = SECRET_FILE.read_text(encoding='utf-8').strip()
    except Exception:
        pass


def porta_livre(inicio=8765, fim=8899):
    for porta in range(inicio, fim + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', porta))
                return porta
            except OSError:
                continue
    raise RuntimeError('Nenhuma porta livre encontrada entre 8765 e 8899.')


PORTA = porta_livre()
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


class JanelaBingo(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Bingo Comunidade')
        self.geometry('570x430')
        self.minsize(540, 410)
        self.protocol('WM_DELETE_WINDOW', self.encerrar)
        self.servidor = None
        self.url_local = f'http://127.0.0.1:{PORTA}'
        self.url_rede = f'http://{ip_rede_local()}:{PORTA}'

        frame = tk.Frame(self, padx=28, pady=24)
        frame.pack(fill='both', expand=True)
        tk.Label(frame, text='Bingo Comunidade', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        tk.Label(frame, text='Central do servidor local • PWA + Online/Offline', font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 20))
        self.status = tk.StringVar(value='Iniciando servidor...')
        tk.Label(frame, textvariable=self.status, font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 12))
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
        tk.Label(frame, text='Mantenha esta janela aberta durante a operação. O banco bingo.db fica ao lado do EXE e não é embutido nele.', font=('Segoe UI', 9), wraplength=500, justify='left').pack(anchor='w', pady=(18, 0))
        threading.Thread(target=self.iniciar, daemon=True).start()

    def iniciar(self):
        try:
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
            self.servidor = ServidorBingo()
            self.servidor.start()
            for _ in range(80):
                try:
                    with urllib.request.urlopen(self.url_local + '/health', timeout=1) as r:
                        if r.status == 200:
                            PORT_FILE.write_text(str(PORTA), encoding='utf-8')
                            texto = f'● Servidor ativo na porta {PORTA}'
                            if not banco_existia:
                                texto += ' — ATENÇÃO: novo bingo.db criado'
                            self.after(0, lambda t=texto: self.status.set(t))
                            self.after(200, lambda: webbrowser.open(self.url_local + '/'))
                            return
                except Exception:
                    time.sleep(.25)
            raise RuntimeError('O servidor não respondeu a tempo.')
        except Exception as exc:
            self.after(0, lambda: self.status.set('Falha ao iniciar'))
            self.after(0, lambda: messagebox.showerror('Bingo Comunidade', str(exc)))

    def encerrar(self):
        if messagebox.askyesno('Encerrar', 'Deseja encerrar o servidor do Bingo Comunidade?'):
            try:
                if self.servidor:
                    self.servidor.parar()
            finally:
                self.destroy()


if __name__ == '__main__':
    JanelaBingo().mainloop()
