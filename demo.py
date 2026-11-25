"""Dados de demonstração: um aeroclube fictício com frota, instrutores e alunos.

As reservas, os vencimentos e os voos são calculados a partir de hoje, então a
agenda nunca aparece vazia e o painel sempre mostra documentos vencidos, perto
de vencer e em dia.
"""
from datetime import datetime, time, timedelta

from modelos import Aeronave, Documento, Reserva, Usuario, Voo, db
import regras

SENHA_DEMO = 'demo123'

USUARIOS = [
    ('Secretaria', 'admin@demo.com', 'admin'),
    ('Cmte. Ana Souza', 'ana@demo.com', 'instrutor'),
    ('Cmte. Bruno Lima', 'bruno@demo.com', 'instrutor'),
    ('Carla Mendes', 'carla@demo.com', 'aluno'),
    ('Diego Rocha', 'diego@demo.com', 'aluno'),
    ('Eduarda Alves', 'eduarda@demo.com', 'aluno'),
    # Felipe está com o CMA vencido: a agenda não deixa reservar voo para ele
    ('Felipe Costa', 'felipe@demo.com', 'aluno'),
]

AERONAVES = [
    ('PR-ABC', 'Cessna 152'),
    ('PR-DEF', 'Cessna 172'),
    ('PR-GHI', 'Piper PA-28'),
    ('PR-JKL', 'Aero Boero AB-115'),
]

# (dias a partir de hoje, aeronave, aluno, instrutor ou None, hora início, duração em horas, observação)
RESERVAS = [
    (1, 'PR-ABC', 'carla', 'ana', 8, 1, 'Instrução: tráfego'),
    (1, 'PR-ABC', 'diego', 'bruno', 10, 1.5, 'Instrução: área'),
    (1, 'PR-DEF', 'eduarda', 'ana', 10, 2, 'Navegação'),
    (1, 'PR-GHI', 'diego', None, 14, 1, 'Voo solo'),
    (2, 'PR-ABC', 'eduarda', 'bruno', 9, 1, 'Toque e arremetida'),
    (2, 'PR-DEF', 'carla', 'ana', 13, 2, 'Navegação'),
    (3, 'PR-GHI', 'carla', 'bruno', 8, 1.5, 'Instrução: pane simulada'),
    (2, 'PR-JKL', 'diego', 'ana', 16, 1, 'Instrução: estol'),
    # Voos de ontem, já realizados: prontos para registrar o tempo voado
    (-1, 'PR-ABC', 'carla', 'ana', 9, 1, 'Instrução: decolagem e pouso'),
    (-1, 'PR-DEF', 'eduarda', 'bruno', 14, 1.5, 'Navegação curta'),
]

# (pessoa, tipo, descrição, vence daqui a quantos dias; negativo = já venceu)
DOCUMENTOS = [
    ('ana', 'cma', '2ª classe', 210),
    ('ana', 'habilitacao', 'MNTE', 45),
    ('ana', 'instrutor', 'INVA', 5),
    ('ana', 'ingles', 'Nível 4', 400),
    ('bruno', 'cma', '2ª classe', 150),
    ('bruno', 'habilitacao', 'MNTE', 240),
    ('bruno', 'instrutor', 'INVA', 90),
    ('carla', 'cma', '2ª classe', 25),
    ('diego', 'cma', '2ª classe', 120),
    ('eduarda', 'cma', '1ª classe', 160),
    ('eduarda', 'ingles', 'Nível 4', 0),
    ('felipe', 'cma', '2ª classe', -12),
]

# Voos de antes: (pessoa, quantos dias atrás, matrícula, função, minutos, pousos, observação)
VOOS = [
    ('ana', 40, 'PR-ABC', 'comando', 150, 2, 'Traslado'),
    ('ana', 130, 'PR-DEF', 'comando', 1260, 30, 'Horas anteriores'),
    ('bruno', 200, 'PR-DEF', 'comando', 2100, 40, 'Horas anteriores'),
    ('carla', 15, 'PR-ABC', 'instrucao', 72, 5, 'Toque e arremetida'),
    ('diego', 5, 'PR-GHI', 'solo', 54, 4, 'Primeiro solo de área'),
    ('diego', 100, 'PR-ABC', 'instrucao', 600, 40, 'Horas anteriores'),
    ('eduarda', 20, 'PR-DEF', 'instrucao', 126, 2, 'Navegação'),
]


def criar_demo():
    """Cria os dados só se o banco estiver vazio. Devolve True se criou."""
    if Usuario.query.first():
        return False

    pessoas = {}
    for nome, email, papel in USUARIOS:
        u = Usuario(nome=nome, email=email, papel=papel)
        u.definir_senha(SENHA_DEMO)
        db.session.add(u)
        pessoas[email.split('@')[0]] = u

    frota = {}
    for matricula, modelo in AERONAVES:
        a = Aeronave(matricula=matricula, modelo=modelo)
        db.session.add(a)
        frota[matricula] = a

    db.session.flush()  # Gera os ids antes de criar as reservas

    for dias, matricula, aluno, instrutor, hora, duracao, obs in RESERVAS:
        inicio = datetime.combine(regras.hoje_local() + timedelta(days=dias), time(hour=hora))
        db.session.add(Reserva(
            aeronave_id=frota[matricula].id,
            aluno_id=pessoas[aluno].id,
            instrutor_id=pessoas[instrutor].id if instrutor else None,
            inicio=inicio,
            fim=inicio + timedelta(hours=duracao),
            observacao=obs,
            criada_por_id=pessoas['admin'].id,
        ))

    hoje = regras.hoje_local()
    for pessoa, tipo, descricao, dias in DOCUMENTOS:
        db.session.add(Documento(dono=pessoas[pessoa], tipo=tipo, descricao=descricao,
                                 vencimento=hoje + timedelta(days=dias)))

    for pessoa, dias_atras, matricula, funcao, minutos, pousos, obs in VOOS:
        db.session.add(Voo(piloto=pessoas[pessoa], data=hoje - timedelta(days=dias_atras),
                           matricula=matricula, funcao=funcao, minutos=minutos,
                           pousos=pousos, observacao=obs))

    db.session.commit()
    return True
