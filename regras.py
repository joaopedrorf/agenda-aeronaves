"""Regras de agendamento, separadas das rotas para ficarem fáceis de testar.

Cada função de validação devolve uma lista de chaves de erro (ver textos.py).
Lista vazia = reserva válida.
"""
from datetime import datetime, timedelta

from modelos import Reserva

# Horário de funcionamento do aeroclube e tamanho dos blocos da agenda.
# Cada aeroclube tem o seu: basta mudar aqui.
HORA_ABERTURA = 7
HORA_FECHAMENTO = 19
MINUTOS_BLOCO = 30
DURACAO_MAXIMA = timedelta(hours=4)


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
    agora = agora or datetime.now()
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


def montar_grade(dia, aeronaves, reservas):
    """Monta a tabela da agenda: uma linha por aeronave, uma coluna por bloco.

    Cada célula é ('livre', 1, hora) ou ('reserva', quantos_blocos, reserva),
    para o template desenhar com colspan.
    """
    blocos = horarios_do_dia()
    abertura = datetime.combine(dia, datetime.min.time()).replace(hour=HORA_ABERTURA)
    passo = timedelta(minutes=MINUTOS_BLOCO)

    grade = []
    for aeronave in aeronaves:
        da_aeronave = [r for r in reservas if r.aeronave_id == aeronave.id]
        celulas = []
        i = 0
        while i < len(blocos):
            momento = abertura + i * passo
            reserva = next((r for r in da_aeronave if r.inicio <= momento < r.fim), None)
            if reserva:
                tamanho = 0
                while i + tamanho < len(blocos) and abertura + (i + tamanho) * passo < reserva.fim:
                    tamanho += 1
                celulas.append(('reserva', tamanho, reserva))
                i += tamanho
            else:
                celulas.append(('livre', 1, blocos[i]))
                i += 1
        grade.append((aeronave, celulas))
    return grade
