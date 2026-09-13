from __future__ import annotations
import socket
import sys
import urllib.request
import tkinter as tk
from tkinter import messagebox, simpledialog

DISCOVERY_PORT = 8764
DISCOVERY_MAGIC = b'BINGO_COMUNIDADE_DISCOVER_V1'
DISCOVERY_PREFIX = 'BINGO_COMUNIDADE_SERVER_V1|'
DEFAULT_PORT = 8765

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
    if (abrirNativo(a.href)) { ev.preventDefault(); ev.stopPropagation(); }
  }, true);
  const originalOpen = window.open;
  window.open = function(url, target, features) {
    if ((!target || target === '_blank') && abrirNativo(url)) return null;
    return originalOpen.call(window, url, target, features);
  };
})();
"""


def health_ok(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url.rstrip('/') + '/health', timeout=1.2) as r:
            return r.status == 200
    except Exception:
        return False


def descobrir_servidor(timeout=2.5):
    destinos = [('255.255.255.255', DISCOVERY_PORT)]
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(0.7)
    try:
        for _ in range(3):
            for destino in destinos:
                try:
                    sock.sendto(DISCOVERY_MAGIC, destino)
                except Exception:
                    pass
            limite = timeout / 3
            inicio = __import__('time').time()
            while __import__('time').time() - inicio < limite:
                try:
                    data, _ = sock.recvfrom(1024)
                except socket.timeout:
                    break
                try:
                    texto = data.decode('utf-8').strip()
                except Exception:
                    continue
                if not texto.startswith(DISCOVERY_PREFIX):
                    continue
                partes = texto.split('|')
                if len(partes) != 3:
                    continue
                ip, porta = partes[1], partes[2]
                base = f'http://{ip}:{int(porta)}'
                if health_ok(base):
                    return base
    finally:
        sock.close()
    return None


def pedir_endereco_manual():
    root = tk.Tk(); root.withdraw()
    resposta = simpledialog.askstring(
        'Bingo Comunidade — Coordenação',
        'Não encontrei automaticamente o notebook principal.\n\nDigite o IP do notebook principal (ex.: 192.168.1.50):',
        parent=root,
    )
    root.destroy()
    if not resposta:
        return None
    resposta = resposta.strip().replace('http://', '').replace('https://', '').strip('/')
    if ':' in resposta:
        base = 'http://' + resposta
    else:
        base = f'http://{resposta}:{DEFAULT_PORT}'
    return base if health_ok(base) else None


def titulo_para_url(url: str) -> str:
    u = (url or '').lower()
    if '/telao' in u:
        return 'Bingo Comunidade — Telão'
    if '/sorteio' in u:
        return 'Bingo Comunidade — Sorteio'
    return 'Bingo Comunidade — Coordenação'


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


class CoordApi:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    def abrir_janela_nativa(self, url: str):
        import webview
        try:
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


def abrir_app(base_url: str):
    import webview
    api = CoordApi(base_url)
    janela = webview.create_window(
        'Bingo Comunidade — Coordenação',
        base_url.rstrip('/') + '/',
        width=1380, height=860, min_size=(960, 640),
        resizable=True, fullscreen=False, confirm_close=False,
        js_api=api,
    )
    instalar_interceptador_popup(janela)
    webview.start(debug=False)


def erro(msg):
    root = tk.Tk(); root.withdraw()
    messagebox.showerror('Bingo Comunidade — Coordenação', msg)
    root.destroy()


def main():
    base = descobrir_servidor()
    if not base:
        base = pedir_endereco_manual()
    if not base:
        erro('Não foi possível localizar o servidor do Bingo.\n\nVerifique se:\n• o Bingo Comunidade está aberto/ativo no notebook principal;\n• os dois notebooks estão na mesma rede Wi-Fi;\n• a rede está marcada como Privada no Windows;\n• o Firewall permitiu o Bingo Comunidade em redes privadas.')
        return
    try:
        abrir_app(base)
    except Exception as exc:
        erro(f'Não foi possível abrir o Bingo Comunidade.\n\n{exc}')


if __name__ == '__main__':
    main()
