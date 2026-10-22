from datetime import datetime, timezone

from conftest import entrar
from modelos import Usuario
import regras
from seguranca import LimitadorDeTentativas


def test_senhas_ficam_guardadas_como_hash(app):
    carla = Usuario.query.filter_by(email='carla@demo.com').one()
    assert 'demo123' not in carla.senha_hash
    assert carla.senha_hash.startswith(('scrypt:', 'pbkdf2:'))


def test_limitador_bloqueia_e_libera_depois_da_janela():
    tempo = [0]
    limitador = LimitadorDeTentativas(maximo=3, janela=60, relogio=lambda: tempo[0])
    for _ in range(3):
        limitador.registrar_falha('x')
    assert limitador.bloqueado('x')
    tempo[0] = 61
    assert not limitador.bloqueado('x')


def test_login_bloqueia_apos_cinco_erros(client):
    for _ in range(5):
        entrar(client, 'carla@demo.com', 'errada')
    # Mesmo com a senha certa, fica bloqueado por um tempo
    resposta = client.post('/login', data={'email': 'carla@demo.com', 'senha': 'demo123'})
    assert resposta.status_code == 429
    assert 'Muitas tentativas' in resposta.text


def test_cabecalhos_de_seguranca(client):
    resposta = client.get('/login')
    assert resposta.headers['X-Frame-Options'] == 'DENY'
    assert resposta.headers['X-Content-Type-Options'] == 'nosniff'
    assert "frame-ancestors 'none'" in resposta.headers['Content-Security-Policy']


def test_cookie_de_sessao_protegido(client):
    entrar(client, 'carla@demo.com')
    cookie = client.get_cookie('session')
    assert cookie.http_only
    assert cookie.same_site == 'Lax'


def test_trocar_senha(client, app):
    app.config['DEMO'] = False
    entrar(client, 'carla@demo.com')
    dados = {'atual': 'demo123', 'nova': 'voo-solo-2026', 'confirmar': 'voo-solo-2026'}
    client.post('/conta/senha', data=dados)
    assert Usuario.query.filter_by(email='carla@demo.com').one().conferir_senha('voo-solo-2026')


def test_trocar_senha_exige_a_atual_e_8_caracteres(client, app):
    app.config['DEMO'] = False
    entrar(client, 'carla@demo.com')
    assert 'incorreta' in client.post('/conta/senha', data={'atual': 'x', 'nova': 'abcdefgh', 'confirmar': 'abcdefgh'}).text
    assert '8 caracteres' in client.post('/conta/senha', data={'atual': 'demo123', 'nova': 'curta', 'confirmar': 'curta'}).text


def test_demo_nao_deixa_trocar_senha_das_contas_de_exemplo(client, app):
    app.config['DEMO'] = True
    entrar(client, 'carla@demo.com')
    resposta = client.post('/conta/senha', data={'atual': 'demo123', 'nova': 'outra-senha', 'confirmar': 'outra-senha'})
    assert 'não podem ser trocadas' in resposta.text


def test_pagina_404_amigavel(client):
    resposta = client.get('/nao-existe')
    assert resposta.status_code == 404
    assert 'Página não encontrada' in resposta.text


def test_saude(client):
    assert client.get('/saude').json == {'status': 'ok'}


def test_hora_local_do_aeroclube_nao_e_utc():
    # 01:30 UTC ainda é o dia anterior em Brasília (UTC-3)
    utc = datetime(2026, 10, 22, 1, 30, tzinfo=timezone.utc)
    assert utc.astimezone(regras.FUSO).replace(tzinfo=None) == datetime(2026, 10, 21, 22, 30)
