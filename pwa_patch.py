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

    if not getattr(bingo.app, '_bingo_pwa_injector', False):
        @bingo.app.after_request
        def inject_pwa(response):
            ctype = (response.content_type or '').lower()
            if response.status_code == 200 and 'text/html' in ctype and not response.direct_passthrough:
                try:
                    html = response.get_data(as_text=True)
                    if 'rel="manifest"' not in html and '</head>' in html:
                        head = (
                            '<meta name="theme-color" content="#5b46e8">'
                            '<meta name="application-name" content="Bingo Comunidade">'
                            '<meta name="apple-mobile-web-app-capable" content="yes">'
                            '<meta name="apple-mobile-web-app-title" content="Bingo Comunidade">'
                            '<link rel="manifest" href="/manifest.webmanifest">'
                            '<link rel="apple-touch-icon" href="/static/apple-touch-icon.png">'
                        )
                        html = html.replace('</head>', head + '</head>', 1)
                    if '/static/pwa.js' not in html and '</body>' in html:
                        html = html.replace('</body>', '<script src="/static/pwa.js" defer></script></body>', 1)
                    response.set_data(html)
                    response.headers['Content-Length'] = len(response.get_data())
                except Exception:
                    pass
            return response
        bingo.app._bingo_pwa_injector = True
