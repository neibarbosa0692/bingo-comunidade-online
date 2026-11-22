"""Ponto de entrada para hospedagem do servidor ONLINE da V11."""
import os
os.environ.setdefault('BINGO_MODE','cloud')
if os.environ.get('PORT') and not os.environ.get('BINGO_PORT'):
    os.environ['BINGO_PORT']=os.environ['PORT']

import app as bingo

bingo.init_db()
app = bingo.app

if __name__ == '__main__':
    port=int(os.environ.get('PORT') or os.environ.get('BINGO_PORT') or '8080')
    app.run(host='0.0.0.0',port=port,debug=False,use_reloader=False)
