from __future__ import annotations

import os
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Porta fixa para facilitar o acesso pelos demais computadores.
PORTA = 8787

# O computador servidor deve se chamar BINGO-ADMIN.
# O nome pode ser alterado no Windows em:
# Configurações > Sistema > Sobre > Renomear este computador.
NOME_SERVIDOR = "BINGO-ADMIN"

os.environ["BINGO_PORT"] = str(PORTA)
os.environ["BINGO_MODE"] = "local"

# Importa o aplicativo somente depois de definir as variáveis de ambiente.
import app as bingo  # noqa: E402


def verificar_porta():
    """Evita iniciar silenciosamente se a porta fixa já estiver ocupada."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", PORTA))
        except OSError as exc:
            raise RuntimeError(
                f"A porta {PORTA} já está sendo usada por outro programa.\n"
                f"Feche o programa que está usando essa porta e tente novamente."
            ) from exc


def ips_locais():
    ips = []
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        for item in infos:
            ip = item[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    # Descobre o IP usado pela rota de saída sem alterar nenhuma configuração de rede.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if not ip.startswith("127.") and ip not in ips:
                ips.insert(0, ip)
    except Exception:
        pass

    return ips


def aguardar_servidor_e_abrir():
    url_local = f"http://127.0.0.1:{PORTA}/cartelas"

    for _ in range(80):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORTA}/health", timeout=1
            ) as resposta:
                if resposta.status == 200:
                    print("\n" + "=" * 68)
                    print("BINGO COMUNIDADE - SERVIDOR LOCAL")
                    print("=" * 68)
                    print(f"Computador servidor : {NOME_SERVIDOR}")
                    print(f"Porta fixa          : {PORTA}")
                    print(f"Acesso neste PC     : {url_local}")
                    print(f"Acesso pela rede    : http://{NOME_SERVIDOR}:{PORTA}/cartelas")

                    ips = ips_locais()
                    if ips:
                        print("\nIP atual (alternativa):")
                        for ip in ips:
                            print(f"  http://{ip}:{PORTA}/cartelas")

                    print("\nO navegador será aberto automaticamente.")
                    print("=" * 68 + "\n")

                    webbrowser.open(url_local, new=1)
                    return
        except Exception:
            time.sleep(0.25)

    print("\nERRO: o servidor não respondeu a tempo.")
    print(f"Tente abrir: http://{NOME_SERVIDOR}:{PORTA}/cartelas")


if __name__ == "__main__":
    print("=" * 68)
    print("BINGO COMUNIDADE - INICIANDO SERVIDOR LOCAL")
    print("=" * 68)
    print(f"Nome de rede esperado: {NOME_SERVIDOR}")
    print(f"Porta fixa: {PORTA}")
    print("Acesso de outros computadores:")
    print(f"  http://{NOME_SERVIDOR}:{PORTA}/cartelas")
    print("=" * 68)

    verificar_porta()

    bingo.init_db()
    bingo.start_sync_worker()

    threading.Thread(
        target=aguardar_servidor_e_abrir,
        daemon=True,
    ).start()

    bingo.app.run(
        host="0.0.0.0",
        port=PORTA,
        debug=False,
        use_reloader=False,
    )
