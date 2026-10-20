"""Tabelas do banco de dados (SQLAlchemy).

Três tabelas:
- Usuario: aluno, instrutor ou administrador (secretaria do aeroclube)
- Aeronave: matrícula e modelo de cada avião da frota
- Reserva: quem vai voar, em qual aeronave, com qual instrutor e quando
"""
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

PAPEIS = ('aluno', 'instrutor', 'admin')


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default='aluno')
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    def definir_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def conferir_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)

    # O Flask-Login usa is_active para bloquear o login de quem foi desativado
    @property
    def is_active(self):
        return self.ativo

    @property
    def is_admin(self):
        return self.papel == 'admin'

    @property
    def is_instrutor(self):
        return self.papel == 'instrutor'


class Aeronave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    matricula = db.Column(db.String(10), unique=True, nullable=False)  # Ex: PR-ABC
    modelo = db.Column(db.String(60), nullable=False)                  # Ex: Cessna 152
    ativa = db.Column(db.Boolean, nullable=False, default=True)        # Em manutenção = inativa


class Reserva(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aeronave_id = db.Column(db.Integer, db.ForeignKey('aeronave.id'), nullable=False)
    aluno_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    instrutor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)  # Vazio = voo solo
    inicio = db.Column(db.DateTime, nullable=False)
    fim = db.Column(db.DateTime, nullable=False)
    observacao = db.Column(db.String(200), default='')
    # Cancelamentos ficam guardados no histórico em vez de apagar a linha
    cancelada = db.Column(db.Boolean, nullable=False, default=False)
    criada_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)

    aeronave = db.relationship('Aeronave')
    aluno = db.relationship('Usuario', foreign_keys=[aluno_id])
    instrutor = db.relationship('Usuario', foreign_keys=[instrutor_id])
    criada_por = db.relationship('Usuario', foreign_keys=[criada_por_id])
