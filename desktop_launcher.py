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
STOP_FILE = BASE_DIR / '.encerrar_servidor'
PORTA_PADRAO = 8765
DISCOVERY_PORT = 8764
DISCOVERY_MAGIC = b'BINGO_COMUNIDADE_DISCOVER_V1'

os.environ['BINGO_DB_PATH'] = str(DB_PATH)
os.environ['BINGO_MODE'] = 'local'
if SECRET_FILE.exists() and not os.environ.get('BINGO_SECRET_KEY'):
    try:
        os.environ['BINGO_SECRET_KEY'] = SECRET_FILE.read_text(encoding='utf-8').strip()
    except Exception:
        pass


def servidor_bingo_ativo(porta: int, host='127.0.0.1') -> bool:
    try:
        with urllib.request.urlopen(f'http://{host}:{porta}/health', timeout=.8) as r:
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


PORTA_EXISTENTE = porta_servidor_existente()
PORTA = PORTA_EXISTENTE or porta_livre()
os.environ['BINGO_PORT'] = str(PORTA)

import app as bingo  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


class ServidorBingo(threading.Thread):
    def __init__(self):
        # Nao-daemon: o servidor continua ativo mesmo depois de fechar a janela principal.
        super().__init__(daemon=False)
        self.httpd = make_server('0.0.0.0', PORTA, bingo.app, threaded=True)

    def run(self):
        self.httpd.serve_forever()

    def parar(self):
        self.httpd.shutdown()


class DescobertaRede(threading.Thread):
    def __init__(self, porta_http: int):
        super().__init__(daemon=True)
        self.porta_http = porta_http
        self.rodando = True
        self.sock = None

    def parar(self):
        self.rodando = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass

    def run(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock = sock
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', DISCOVERY_PORT))
            sock.settimeout(1.0)
            while self.rodando:
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if data.strip() != DISCOVERY_MAGIC:
                    continue
                try:
                    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    probe.connect((addr[0], 9))
                    ip = probe.getsockname()[0]
                    probe.close()
                except Exception:
                    ip = ip_rede_local()
                resposta = f'BINGO_COMUNIDADE_SERVER_V1|{ip}|{self.porta_http}'.encode('utf-8')
                try:
                    sock.sendto(resposta, addr)
                except Exception:
                    pass
        except Exception:
            pass


POPUP_SCRIPT = r"""
(() => {
  if (window.__bingoNativePopupsInstalled) return;
  window.__bingoNativePopupsInstalled = true;

  const abrirNativo = (url) => {
    try {
      if (!url) return false;
      const absoluto = new URL(url, window.location.href);
      if (absoluto.origin !== window.location.origin) return false;
      if (window.pywebview && window.pywebview.api && window.pywebview.api.abrir_janela_nativa) {
        window.pywebview.api.abrir_janela_nativa(absoluto.href);
        return true;
      }
    } catch (_) {}
    return false;
  };

  document.addEventListener('click', (ev) => {
    const a = ev.target.closest && ev.target.closest('a[target="_blank"]');
    if (!a) return;
    if (abrirNativo(a.href)) {
      ev.preventDefault();
      ev.stopPropagation();
    }
  }, true);

  const originalOpen = window.open;
  window.open = function(url, target, features) {
    if ((!target || target === '_blank') && abrirNativo(url)) return null;
    return originalOpen.call(window, url, target, features);
  };
})();
"""


def titulo_para_url(url: str) -> str:
    u = (url or '').lower()
    if '/telao' in u:
        return 'Bingo Comunidade — Telão'
    if '/sorteio' in u:
        return 'Bingo Comunidade — Sorteio'
    return 'Bingo Comunidade'


def tamanho_para_url(url: str):
    u = (url or '').lower()
    if '/telao' in u:
        return 1500, 900, (1000, 650)
    if '/sorteio' in u:
        return 1450, 900, (1000, 680)
    return 1380, 860, (960, 640)


def instalar_interceptador_popup(janela):
    def ao_carregar():
        try:
            janela.evaluate_js(POPUP_SCRIPT)
        except Exception:
            pass
    try:
        janela.events.loaded += ao_carregar
    except Exception:
        pass


class DesktopApi:
    def __init__(self, porta: int):
        self.base_url = f'http://127.0.0.1:{porta}'

    def abrir_janela_nativa(self, url: str):
        import webview
        try:
            if not url:
                return False
            if url.startswith('/'):
                url = self.base_url + url
            if not url.startswith(self.base_url):
                return False
            largura, altura, minimo = tamanho_para_url(url)
            janela = webview.create_window(
                titulo_para_url(url), url,
                width=largura, height=altura, min_size=minimo,
                resizable=True, fullscreen=False, confirm_close=False,
                js_api=self,
            )
            instalar_interceptador_popup(janela)
            return True
        except Exception:
            return False


def abrir_janela_app(porta: int):
    import webview
    api = DesktopApi(porta)
    url = f'http://127.0.0.1:{porta}/'
    janela = webview.create_window(
        'Bingo Comunidade', url,
        width=1380, height=860, min_size=(960, 640),
        resizable=True, fullscreen=False, confirm_close=False,
        js_api=api,
    )
    instalar_interceptador_popup(janela)
    webview.start(debug=False)


class JanelaCentral(tk.Tk):
    def __init__(self, servidor=None):
        super().__init__()
        self.servidor = servidor
        self.title('Bingo Comunidade — Central')
        self.geometry('610x500')
        self.minsize(570, 460)
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.url_local = f'http://127.0.0.1:{PORTA}'
        self.url_rede = f'http://{ip_rede_local()}:{PORTA}'
        frame = tk.Frame(self, padx=28, pady=24)
        frame.pack(fill='both', expand=True)
        tk.Label(frame, text='Bingo Comunidade', font=('Segoe UI', 22, 'bold')).pack(anchor='w')
        tk.Label(frame, text='Servidor principal da rede local', font=('Segoe UI', 10)).pack(anchor='w', pady=(0, 20))
        tk.Label(frame, text=f'● Servidor ativo na porta {PORTA}', font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 12))
        tk.Label(frame, text='Banco oficial:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        tk.Label(frame, text=str(DB_PATH), wraplength=540, justify='left', font=('Segoe UI', 9)).pack(anchor='w', pady=(0, 12))
        tk.Label(frame, text='Acesso neste computador:', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        tk.Label(frame, text=self.url_local, font=('Segoe UI', 10)).pack(anchor='w')
        tk.Label(frame, text='Acesso para outros notebooks/celulares na mesma rede:', font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(10, 0))
        tk.Label(frame, text=self.url_rede, font=('Segoe UI', 10, 'bold')).pack(anchor='w')
        tk.Label(frame, text='O aplicativo Coordenação encontra este servidor automaticamente. Fechar a janela principal do Bingo não derruba mais o servidor.', font=('Segoe UI', 9), wraplength=540, justify='left').pack(anchor='w', pady=(18, 12))
        tk.Button(frame, text='Encerrar servidor do Bingo', command=self.encerrar_servidor, padx=14, pady=9).pack(anchor='w', pady=(8, 0))

    def encerrar_servidor(self):
        if not messagebox.askyesno('Encerrar servidor', 'Isso desconectará o notebook da coordenação, celulares e telão. Deseja continuar?'):
            return
        try:
            if self.servidor:
                self.servidor.parar()
            else:
                STOP_FILE.write_text('1', encoding='utf-8')
        except Exception as exc:
            messagebox.showerror('Bingo Comunidade', str(exc))
            return
        self.destroy()


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


def vigiar_encerramento(servidor, descoberta):
    def worker():
        while servidor.is_alive():
            if STOP_FILE.exists():
                try:
                    STOP_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    descoberta.parar()
                except Exception:
                    pass
                try:
                    servidor.parar()
                except Exception:
                    pass
                try:
                    PORT_FILE.unlink(missing_ok=True)
                except Exception:
                    pass
                break
            time.sleep(.5)
    threading.Thread(target=worker, daemon=True).start()


def iniciar_servidor():
    banco_existia = preparar_bingo()
    try:
        STOP_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    servidor = ServidorBingo()
    servidor.start()
    for _ in range(80):
        if servidor_bingo_ativo(PORTA):
            PORT_FILE.write_text(str(PORTA), encoding='utf-8')
            descoberta = DescobertaRede(PORTA)
            descoberta.start()
            vigiar_encerramento(servidor, descoberta)
            return servidor, descoberta, banco_existia
        time.sleep(.25)
    servidor.parar()
    raise RuntimeError('O servidor não respondeu a tempo.')


def mostrar_erro(texto):
    root = tk.Tk(); root.withdraw()
    messagebox.showerror('Bingo Comunidade', texto)
    root.destroy()


def avisar_banco_novo():
    root = tk.Tk(); root.withdraw()
    messagebox.showwarning(
        'Bingo Comunidade',
        'ATENÇÃO: não foi encontrado bingo.db ao lado do EXE. Um banco novo foi criado.\n\n'
        'Se este computador possui o banco oficial das 500 cartelas, feche o programa e coloque o bingo.db correto ao lado do EXE.'
    )
    root.destroy()


def main():
    if '--central' in sys.argv:
        servidor = None
        if PORTA_EXISTENTE is None:
            try:
                servidor, _, _ = iniciar_servidor()
            except Exception as exc:
                mostrar_erro(str(exc)); return
        JanelaCentral(servidor).mainloop()
        return

    if PORTA_EXISTENTE is not None:
        try:
            abrir_janela_app(PORTA_EXISTENTE)
        except Exception as exc:
            mostrar_erro(f'Não foi possível abrir a janela do aplicativo.\n\n{exc}')
        return

    servidor = None
    try:
        servidor, descoberta, banco_existia = iniciar_servidor()
        if not banco_existia:
            avisar_banco_novo()
        abrir_janela_app(PORTA)
        # Ao fechar a janela principal, o processo continua como servidor em segundo plano.
        # Um novo clique no EXE reabre a janela. Para encerrar, use --central.
    except Exception as exc:
        mostrar_erro(str(exc))
        if servidor:
            try:
                servidor.parar()
            except Exception:
                pass


if __name__ == '__main__':
    main()
