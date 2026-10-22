"""Regras de agendamento, separadas das rotas para ficarem fáceis de testar.

Cada função de validação devolve uma lista de chaves de erro (ver textos.py).
Lista vazia = reserva válida.
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from modelos import Reserva

# O servidor (Render) roda em UTC, mas o aeroclube vive no horário de Brasília.
# Todas as horas do sistema são "hora local do aeroclube", sem fuso gravado no banco.
FUSO = ZoneInfo(os.getenv('FUSO_HORARIO', 'America/Sao_Paulo'))

# Horário de funcionamento do aeroclube e tamanho dos blocos da agenda.
# Cada aeroclube tem o seu: basta mudar aqui.
HORA_ABERTURA = 7
HORA_FECHAMENTO = 19
MINUTOS_BLOCO = 30
DURACAO_MAXIMA = timedelta(hours=4)


def agora_local():
    """Data e hora atuais no fuso do aeroclube."""
    return datetime.now(FUSO).replace(tzinfo=None)


def hoje_local():
    return agora_local().date()


def sobrepoe(inicio_a, fim_a, inicio_b, fim_b):
    """Dois intervalos se cruzam? Encostar (um termina 10h, outro começa 10h) não conta."""
    return inicio_a < fim_b and inicio_b < fim_a


def conflitos(inicio, fim, aeronave_id, aluno_id, instrutor_id, ignorar_id=None):
    """Procura reservas ativas que batem com o horário pedido."""
    consulta = Reserva.query.filter(
        Reserva.cancelada.is_(False),
        Reserva.inicio < fim,
        Reserva.fim > inicio,
    )
    if ignorar_id:
        consulta = consulta.filter(Reserva.id != ignorar_id)

    erros = []
    for r in consulta.all():
        if r.aeronave_id == aeronave_id and 'conflito_aeronave' not in erros:
            erros.append('conflito_aeronave')
        if instrutor_id and instrutor_id in (r.instrutor_id, r.aluno_id) and 'conflito_instrutor' not in erros:
            erros.append('conflito_instrutor')
        if aluno_id in (r.aluno_id, r.instrutor_id) and 'conflito_aluno' not in erros:
            erros.append('conflito_aluno')
    return erros


def validar_horario(inicio, fim, agora=None):
    agora = agora or agora_local()
    erros = []
    if fim <= inicio:
        return ['fim_antes_inicio']
    if inicio < agora:
        erros.append('no_passado')
    if inicio.date() != fim.date():
        erros.append('mesmo_dia')
    if fim - inicio > DURACAO_MAXIMA:
        erros.append('duracao_maxima')
    abertura = inicio.replace(hour=HORA_ABERTURA, minute=0, second=0, microsecond=0)
    fechamento = inicio.replace(hour=HORA_FECHAMENTO, minute=0, second=0, microsecond=0)
    if inicio < abertura or fim > fechamento:
        erros.append('fora_do_horario')
    for momento in (inicio, fim):
        if momento.minute % MINUTOS_BLOCO or momento.second:
            erros.append('bloco_30')
            break
    return erros


def pode_cancelar(usuario, reserva):
    if reserva.cancelada:
        return False
    if usuario.is_admin:
        return True
    return usuario.id in (reserva.aluno_id, reserva.instrutor_id, reserva.criada_por_id)


def horarios_do_dia():
    """Lista os inícios de bloco do dia: 07:00, 07:30, ... 18:30."""
    blocos = []
    minutos = HORA_ABERTURA * 60
    while minutos < HORA_FECHAMENTO * 60:
        blocos.append(f'{minutos // 60:02d}:{minutos % 60:02d}')
        minutos += MINUTOS_BLOCO
    return blocos


def posicao(reserva):
    """Posição da reserva na linha do tempo da agenda, em % (left e width)."""
    total = (HORA_FECHAMENTO - HORA_ABERTURA) * 60
    abertura = reserva.inicio.replace(hour=HORA_ABERTURA, minute=0)
    inicio = (reserva.inicio - abertura).total_seconds() / 60
    duracao = (reserva.fim - reserva.inicio).total_seconds() / 60
    return round(inicio / total * 100, 3), round(duracao / total * 100, 3)


def montar_grade(dia, aeronaves, reservas, agora=None):
    """Monta a agenda: para cada aeronave, os blocos de 30 min e as reservas.

    Os blocos ficam por baixo (clicáveis quando livres e no futuro); as
    reservas são desenhadas por cima, posicionadas em % da linha do tempo.
    """
    agora = agora or agora_local()
    abertura = datetime.combine(dia, datetime.min.time()).replace(hour=HORA_ABERTURA)
    passo = timedelta(minutes=MINUTOS_BLOCO)

    grade = []
    for aeronave in aeronaves:
        da_aeronave = sorted((r for r in reservas if r.aeronave_id == aeronave.id), key=lambda r: r.inicio)
        blocos = []
        for i, hora in enumerate(horarios_do_dia()):
            momento = abertura + i * passo
            ocupado = any(r.inicio <= momento < r.fim for r in da_aeronave)
            blocos.append({'hora': hora, 'livre': not ocupado and momento > agora})
        grade.append({
            'aeronave': aeronave,
            'blocos': blocos,
            'reservas': [{'r': r, 'pos': posicao(r)} for r in da_aeronave],
        })
    return grade


def disponibilidade(dia, reservas):
    """Divide o dia de uma aeronave em trechos livres e ocupados, em ordem.

    Devolve [(inicio, fim, livre), ...] cobrindo do horário de abertura ao fechamento.
    """
    abertura = datetime.combine(dia, datetime.min.time()).replace(hour=HORA_ABERTURA)
    fechamento = abertura.replace(hour=HORA_FECHAMENTO)
    trechos = []
    cursor = abertura
    for r in sorted(reservas, key=lambda r: r.inicio):
        if r.inicio > cursor:
            trechos.append((cursor, r.inicio, True))
        trechos.append((max(r.inicio, cursor), r.fim, False))
        cursor = max(cursor, r.fim)
    if cursor < fechamento:
        trechos.append((cursor, fechamento, True))
    return trechos


def sugerir(inicio, fim, aeronave_id, aluno_id, instrutor_id, aeronaves, agora=None):
    """Quando o horário pedido não está livre, procura alternativas.

    - horario: o primeiro horário do mesmo dia, com a mesma duração, em que
      aeronave, aluno e instrutor estão livres (ou None)
    - aeronaves: outras aeronaves livres exatamente no horário pedido
    """
    agora = agora or agora_local()
    duracao = fim - inicio
    passo = timedelta(minutes=MINUTOS_BLOCO)
    candidato = inicio.replace(hour=HORA_ABERTURA, minute=0, second=0, microsecond=0)
    fechamento = candidato.replace(hour=HORA_FECHAMENTO)

    horario = None
    melhor_distancia = None
    while candidato + duracao <= fechamento:
        if candidato >= agora and candidato != inicio:
            if not conflitos(candidato, candidato + duracao, aeronave_id, aluno_id, instrutor_id):
                distancia = abs(candidato - inicio)
                if melhor_distancia is None or distancia < melhor_distancia:
                    horario, melhor_distancia = (candidato, candidato + duracao), distancia
        candidato += passo

    livres = [
        a for a in aeronaves
        if a.id != aeronave_id and not conflitos(inicio, fim, a.id, aluno_id, instrutor_id)
    ]
    return {'horario': horario, 'aeronaves': livres}


def resumo_do_dia(reservas, aeronaves):
    """Números do topo da agenda: quantos voos e quantas horas no dia."""
    horas = sum((r.fim - r.inicio).total_seconds() for r in reservas) / 3600
    return {'voos': len(reservas), 'horas': horas, 'aeronaves': len(aeronaves)}
