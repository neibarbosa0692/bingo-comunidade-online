"""Recursos PWA do Bingo Comunidade."""
from flask import render_template


def install(bingo):
    def manifest():
        resp = bingo.app.send_static_file('manifest.webmanifest')
        resp.mimetype = 'application/manifest+json'
        return resp

    def service_worker():
        resp = bingo.app.send_static_file('sw.js')
        resp.mimetype = 'application/javascript'
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Service-Worker-Allowed'] = '/'
        return resp

    def offline():
        return render_template('offline.html')

    if 'pwa_manifest' not in bingo.app.view_functions:
        bingo.app.add_url_rule('/manifest.webmanifest', 'pwa_manifest', manifest)
    if 'pwa_service_worker' not in bingo.app.view_functions:
        bingo.app.add_url_rule('/sw.js', 'pwa_service_worker', service_worker)
    if 'pwa_offline' not in bingo.app.view_functions:
        bingo.app.add_url_rule('/offline', 'pwa_offline', offline)

    try:
        bingo.PUBLIC_ENDPOINTS.update({'pwa_manifest','pwa_service_worker','pwa_offline'})
    except Exception:
        pass
