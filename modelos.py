"""Tabelas do banco de dados (SQLAlchemy).

Tabelas:
- Usuario: aluno, instrutor ou administrador (secretaria do aeroclube)
- Aeronave: matrícula e modelo de cada avião da frota
- Reserva: quem vai voar, em qual aeronave, com qual instrutor e quando
- Documento: CMA, habilitações, proficiência em inglês... com a data de vencimento
- Voo: tempo de voo e pousos (vindo de uma reserva realizada ou lançado à mão)
- Aviso: lembretes de vencimento já enviados, para não mandar o mesmo duas vezes
"""
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

PAPEIS = ('aluno', 'instrutor', 'admin')

# O sistema não calcula validade: a pessoa digita a data que está no documento.
# (A validade do CMA, por exemplo, muda com a classe e a idade.)
TIPOS_DOCUMENTO = ('cma', 'habilitacao', 'ifr', 'ingles', 'instrutor', 'outro')

# Função a bordo, como na caderneta (CIV)
FUNCOES = ('instrucao', 'solo', 'comando', 'instrutor')


class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default='aluno')
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    documentos = db.relationship('Documento', back_populates='dono', order_by='Documento.vencimento',
                                 cascade='all, delete-orphan')
    voos = db.relationship('Voo', back_populates='piloto', order_by='Voo.data.desc()',
                           cascade='all, delete-orphan')

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
    voos = db.relationship('Voo', back_populates='reserva')

    @property
    def voo_registrado(self):
        return bool(self.voos)


class Documento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    descricao = db.Column(db.String(80), default='')  # Ex: "MNTE", "1ª classe", "Nível 4"
    vencimento = db.Column(db.Date, nullable=False)

    dono = db.relationship('Usuario', back_populates='documentos')
    avisos = db.relationship('Aviso', back_populates='documento', cascade='all, delete-orphan')


class Voo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    # Preenchido quando o voo vem de uma reserva da agenda (vazio = lançado à mão)
    reserva_id = db.Column(db.Integer, db.ForeignKey('reserva.id'), nullable=True)
    data = db.Column(db.Date, nullable=False)
    matricula = db.Column(db.String(10), nullable=False)   # Ex: PR-ABC
    funcao = db.Column(db.String(20), nullable=False, default='instrucao')
    minutos = db.Column(db.Integer, nullable=False)        # Guardado em minutos: 1:30 = 90
    pousos = db.Column(db.Integer, nullable=False, default=1)
    observacao = db.Column(db.String(200), default='')

    piloto = db.relationship('Usuario', back_populates='voos')
    reserva = db.relationship('Reserva', back_populates='voos')


class Aviso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    documento_id = db.Column(db.Integer, db.ForeignKey('documento.id'), nullable=False)
    marco = db.Column(db.Integer, nullable=False)          # 30, 7 ou 0 dias antes do vencimento
    vencimento = db.Column(db.Date, nullable=False)        # Se o documento for renovado, avisa de novo
    enviado_em = db.Column(db.DateTime, nullable=False)
    simulado = db.Column(db.Boolean, nullable=False, default=False)  # Sem servidor de e-mail configurado

    documento = db.relationship('Documento', back_populates='avisos')
