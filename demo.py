"""Dados de demonstração: um aeroclube fictício com frota, instrutores e alunos.

As reservas são criadas a partir de hoje, então a agenda nunca aparece vazia.
"""
from datetime import datetime, time, timedelta

from modelos import Aeronave, Reserva, Usuario, db
import regras

SENHA_DEMO = 'demo123'

USUARIOS = [
    ('Secretaria', 'admin@demo.com', 'admin'),
    ('Cmte. Ana Souza', 'ana@demo.com', 'instrutor'),
    ('Cmte. Bruno Lima', 'bruno@demo.com', 'instrutor'),
    ('Carla Mendes', 'carla@demo.com', 'aluno'),
    ('Diego Rocha', 'diego@demo.com', 'aluno'),
    ('Eduarda Alves', 'eduarda@demo.com', 'aluno'),
]

AERONAVES = [
    ('PR-ABC', 'Cessna 152'),
    ('PR-DEF', 'Cessna 172'),
    ('PR-GHI', 'Piper PA-28'),
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

    db.session.commit()
    return True
