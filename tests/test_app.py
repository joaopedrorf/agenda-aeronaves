from datetime import date, timedelta

from conftest import entrar
from modelos import Aeronave, Reserva, Usuario, db

AMANHA = (date.today() + timedelta(days=1)).isoformat()


def id_de(modelo, **filtro):
    return modelo.query.filter_by(**filtro).first().id


def reservar(client, **campos):
    dados = {
        'aeronave_id': id_de(Aeronave, matricula='PR-GHI'),
        'data': AMANHA, 'inicio': '16:00', 'fim': '17:00',
        'instrutor_id': '', 'observacao': 'teste',
    }
    dados.update(campos)
    return client.post('/reservas/nova', data=dados)


def test_agenda_exige_login(client):
    resposta = client.get('/')
    assert resposta.status_code == 302
    assert '/login' in resposta.headers['Location']


def test_login_errado(client):
    assert 'E-mail ou senha incorretos' in entrar(client, 'carla@demo.com', 'errada').text


def test_agenda_mostra_reservas_de_amanha(client):
    entrar(client, 'carla@demo.com')
    pagina = client.get(f'/?dia={AMANHA}').text
    assert 'PR-ABC' in pagina
    assert 'Carla Mendes' in pagina


def test_troca_de_idioma(client):
    entrar(client, 'carla@demo.com')
    client.get('/idioma/en')
    assert 'My bookings' in client.get('/').text


def test_aluno_reserva_para_si_mesmo(client, app):
    entrar(client, 'carla@demo.com')
    # Mesmo mandando outro aluno no formulário, a reserva fica no nome de quem está logado
    resposta = reservar(client, aluno_id=id_de(Usuario, email='diego@demo.com'))
    assert resposta.status_code == 302
    nova = Reserva.query.filter_by(observacao='teste').one()
    assert nova.aluno.email == 'carla@demo.com'


def test_conflito_de_aeronave(client):
    entrar(client, 'eduarda@demo.com')
    # Demo: PR-ABC amanhã das 08h às 09h com a Carla
    resposta = reservar(client, aeronave_id=id_de(Aeronave, matricula='PR-ABC'), inicio='08:30', fim='09:30')
    assert resposta.status_code == 400
    assert 'já está reservada' in resposta.text


def test_conflito_de_instrutor(client):
    entrar(client, 'eduarda@demo.com')
    # Demo: Cmte. Ana voa amanhã das 08h às 09h no PR-ABC
    resposta = reservar(client, inicio='08:00', fim='09:00',
                        instrutor_id=id_de(Usuario, email='ana@demo.com'))
    assert 'instrutor já tem outro voo' in resposta.text


def test_conflito_de_aluno(client):
    entrar(client, 'carla@demo.com')
    # Demo: Carla voa amanhã das 08h às 09h no PR-ABC; tenta outra aeronave no mesmo horário
    resposta = reservar(client, inicio='08:00', fim='09:00')
    assert 'aluno já tem outro voo' in resposta.text


def test_aeronave_inativa_nao_reserva(client, app):
    aeronave = Aeronave.query.filter_by(matricula='PR-GHI').one()
    aeronave.ativa = False
    db.session.commit()
    entrar(client, 'carla@demo.com')
    assert 'não está disponível' in reservar(client).text


def test_cancelar_somente_a_propria(client):
    entrar(client, 'eduarda@demo.com')
    da_carla = Reserva.query.filter_by(observacao='Instrução: tráfego').one()
    client.post(f'/reservas/{da_carla.id}/cancelar')
    assert not db.session.get(Reserva, da_carla.id).cancelada

    propria = Reserva.query.filter_by(observacao='Toque e arremetida').one()
    client.post(f'/reservas/{propria.id}/cancelar')
    assert db.session.get(Reserva, propria.id).cancelada


def test_horario_cancelado_volta_a_ficar_livre(client):
    entrar(client, 'admin@demo.com')
    reserva = Reserva.query.filter_by(observacao='Instrução: tráfego').one()
    client.post(f'/reservas/{reserva.id}/cancelar')
    client.post('/sair')
    entrar(client, 'eduarda@demo.com')
    resposta = reservar(client, aeronave_id=reserva.aeronave_id, inicio='08:00', fim='09:00')
    assert resposta.status_code == 302


def test_aluno_nao_acessa_administracao(client):
    entrar(client, 'carla@demo.com')
    assert client.get('/aeronaves').status_code == 302
    assert client.get('/usuarios').status_code == 302


def test_admin_cadastra_aeronave_e_usuario(client):
    entrar(client, 'admin@demo.com')
    client.post('/aeronaves', data={'matricula': 'pr-xyz', 'modelo': 'Aero Boero'})
    assert Aeronave.query.filter_by(matricula='PR-XYZ').one()
    client.post('/usuarios', data={'nome': 'Novo Aluno', 'email': 'novo@demo.com',
                                   'senha': 'segredo1', 'papel': 'aluno'})
    novo = Usuario.query.filter_by(email='novo@demo.com').one()
    assert novo.conferir_senha('segredo1')


def test_usuario_desativado_nao_entra(client):
    entrar(client, 'admin@demo.com')
    diego = Usuario.query.filter_by(email='diego@demo.com').one()
    client.post(f'/usuarios/{diego.id}/alternar')
    client.post('/sair')
    assert 'E-mail ou senha incorretos' in entrar(client, 'diego@demo.com').text


def test_formulario_sem_token_csrf_e_recusado(app):
    app.config['TESTING_SEM_CSRF'] = False
    resposta = app.test_client().post('/login', data={'email': 'x', 'senha': 'y'})
    assert resposta.status_code == 400
