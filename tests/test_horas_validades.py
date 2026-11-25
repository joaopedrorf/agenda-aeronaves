"""Junção da agenda com o controle de horas e validades."""
from datetime import timedelta

from conftest import entrar
from modelos import Aeronave, Documento, Reserva, Usuario, Voo, db
import regras

AMANHA = (regras.hoje_local() + timedelta(days=1)).isoformat()


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


def documento(email, tipo):
    return Documento.query.join(Usuario).filter(Usuario.email == email, Documento.tipo == tipo).one()


# ---------- Bloqueio por documento vencido ----------

def test_aluno_com_cma_vencido_nao_reserva(client):
    entrar(client, 'felipe@demo.com')
    resposta = reservar(client)
    assert resposta.status_code == 400
    assert 'Felipe Costa está com CMA (certificado médico) (2ª classe) vencido' in resposta.text
    assert not Reserva.query.filter_by(observacao='teste').first()


def test_renovou_o_cma_volta_a_reservar(client):
    documento('felipe@demo.com', 'cma').vencimento = regras.hoje_local() + timedelta(days=365)
    db.session.commit()
    entrar(client, 'felipe@demo.com')
    assert reservar(client).status_code == 302


def test_documento_que_vence_antes_do_voo_bloqueia(client):
    # Ainda vale hoje, mas já estará vencido no dia do voo
    documento('carla@demo.com', 'cma').vencimento = regras.hoje_local()
    db.session.commit()
    entrar(client, 'carla@demo.com')
    assert reservar(client).status_code == 400
    # Vencendo no próprio dia do voo ainda vale
    documento('carla@demo.com', 'cma').vencimento = regras.hoje_local() + timedelta(days=1)
    db.session.commit()
    assert reservar(client).status_code == 302


def test_instrutor_com_inva_vencido_bloqueia(client):
    documento('ana@demo.com', 'instrutor').vencimento = regras.hoje_local() - timedelta(days=1)
    db.session.commit()
    entrar(client, 'carla@demo.com')
    resposta = reservar(client, instrutor_id=id_de(Usuario, email='ana@demo.com'))
    assert resposta.status_code == 400
    assert 'Cmte. Ana Souza' in resposta.text


def test_ingles_vencido_nao_trava_a_agenda(client):
    documento('ana@demo.com', 'ingles').vencimento = regras.hoje_local() - timedelta(days=1)
    db.session.commit()
    entrar(client, 'carla@demo.com')
    assert reservar(client, instrutor_id=id_de(Usuario, email='ana@demo.com')).status_code == 302


# ---------- Reserva realizada vira hora de voo ----------

def reserva_de_ontem():
    return Reserva.query.filter_by(observacao='Instrução: decolagem e pouso').one()


def test_registrar_voo_da_reserva_lanca_para_aluno_e_instrutor(client):
    entrar(client, 'carla@demo.com')
    reserva = reserva_de_ontem()
    assert 'Registrar voo' in client.get('/reservas/minhas').text
    resposta = client.post(f'/reservas/{reserva.id}/voo', data={'tempo': '1:06', 'pousos': '5'})
    assert resposta.status_code == 302
    voos = Voo.query.filter_by(reserva_id=reserva.id).all()
    assert {(v.piloto.email, v.funcao, v.minutos, v.pousos) for v in voos} == {
        ('carla@demo.com', 'instrucao', 66, 5),
        ('ana@demo.com', 'instrutor', 66, 5),
    }
    assert all(v.matricula == 'PR-ABC' and v.data == reserva.inicio.date() for v in voos)
    assert 'Voo registrado' in client.get('/reservas/minhas').text


def test_nao_registra_o_mesmo_voo_duas_vezes(client):
    entrar(client, 'carla@demo.com')
    reserva = reserva_de_ontem()
    client.post(f'/reservas/{reserva.id}/voo', data={'tempo': '1:00', 'pousos': '1'})
    client.post(f'/reservas/{reserva.id}/voo', data={'tempo': '1:00', 'pousos': '1'})
    assert Voo.query.filter_by(reserva_id=reserva.id).count() == 2  # aluno + instrutor, uma vez só


def test_nao_registra_voo_de_outra_pessoa_nem_futuro(client):
    entrar(client, 'diego@demo.com')
    client.post(f'/reservas/{reserva_de_ontem().id}/voo', data={'tempo': '1:00', 'pousos': '1'})
    futura = Reserva.query.filter_by(observacao='Voo solo').one()
    client.post(f'/reservas/{futura.id}/voo', data={'tempo': '1:00', 'pousos': '1'})
    assert Voo.query.filter(Voo.reserva_id.isnot(None)).count() == 0


def test_tempo_invalido_nao_registra(client):
    entrar(client, 'carla@demo.com')
    client.post(f'/reservas/{reserva_de_ontem().id}/voo', data={'tempo': '30:00', 'pousos': '1'})
    assert Voo.query.filter(Voo.reserva_id.isnot(None)).count() == 0


# ---------- Documentos, horas e secretaria ----------

def test_aluno_cadastra_e_ve_os_proprios_documentos(client):
    entrar(client, 'diego@demo.com')
    client.post('/documentos', data={'tipo': 'habilitacao', 'descricao': 'MNTE',
                                     'vencimento': (regras.hoje_local() + timedelta(days=200)).isoformat()})
    pagina = client.get('/documentos').text
    assert 'MNTE' in pagina and 'Habilitação de classe/tipo' in pagina


def test_aluno_nao_mexe_em_documento_de_outro(client):
    entrar(client, 'diego@demo.com')
    doc = documento('carla@demo.com', 'cma')
    antes = doc.vencimento
    client.post(f'/documentos/{doc.id}/renovar', data={'vencimento': '2030-01-01'})
    client.post(f'/documentos/{doc.id}/excluir')
    assert db.session.get(Documento, doc.id).vencimento == antes


def test_lancar_horas_anteriores(client):
    entrar(client, 'diego@demo.com')
    resposta = client.post('/voos', data={'data': regras.hoje_local().isoformat(), 'matricula': 'pr-abc',
                                          'funcao': 'solo', 'tempo': '1,5', 'pousos': '3'})
    assert resposta.status_code == 302
    assert Voo.query.filter_by(matricula='PR-ABC', minutos=90).count() == 1


def test_secretaria_ve_painel_e_aluno_nao(client):
    entrar(client, 'carla@demo.com')
    assert client.get('/secretaria').status_code == 302
    client.post('/sair')
    entrar(client, 'admin@demo.com')
    pagina = client.get('/secretaria').text
    assert 'Felipe Costa' in pagina                 # CMA vencido na lista de atenção
    assert 'Navegação curta' in pagina              # voo de ontem ainda sem horas lançadas
    assert 'PR-ABC' in pagina                       # horas por aeronave


def test_secretaria_ve_perfil_da_pessoa(client):
    entrar(client, 'admin@demo.com')
    pagina = client.get(f"/usuarios/{id_de(Usuario, email='felipe@demo.com')}").text
    assert 'Felipe Costa' in pagina and '2ª classe' in pagina


def test_tarefa_de_avisos_exige_token(app, client):
    assert client.post('/tarefas/avisos').status_code == 404
    app.config['AVISOS_TOKEN'] = 'segredo-de-teste'
    assert client.post('/tarefas/avisos', headers={'Authorization': 'Bearer errado'}).status_code == 404
    resposta = client.post('/tarefas/avisos', headers={'Authorization': 'Bearer segredo-de-teste'})
    assert resposta.status_code == 200 and resposta.json['enviados'] > 0
