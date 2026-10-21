from datetime import date, datetime

from regras import disponibilidade, horarios_do_dia, montar_grade, posicao, sobrepoe, validar_horario

AGORA = datetime(2026, 10, 20, 6, 0)


def dt(hora, minuto=0, dia=21):
    return datetime(2026, 10, dia, hora, minuto)


def test_sobrepoe():
    assert sobrepoe(dt(8), dt(10), dt(9), dt(11))
    assert sobrepoe(dt(8), dt(12), dt(9), dt(10))
    # Encostar não é conflito: um termina às 10h, o outro começa às 10h
    assert not sobrepoe(dt(8), dt(10), dt(10), dt(11))


def test_horario_valido():
    assert validar_horario(dt(8), dt(9, 30), AGORA) == []


def test_fim_antes_do_inicio():
    assert validar_horario(dt(10), dt(9), AGORA) == ['fim_antes_inicio']


def test_no_passado():
    assert 'no_passado' in validar_horario(dt(8, dia=19), dt(9, dia=19), AGORA)


def test_duracao_maxima():
    assert 'duracao_maxima' in validar_horario(dt(8), dt(12, 30), AGORA)


def test_fora_do_horario():
    assert 'fora_do_horario' in validar_horario(dt(6), dt(7), AGORA)
    assert 'fora_do_horario' in validar_horario(dt(18), dt(19, 30), AGORA)


def test_blocos_de_meia_hora():
    assert 'bloco_30' in validar_horario(dt(8, 15), dt(9), AGORA)


def test_horarios_do_dia():
    blocos = horarios_do_dia()
    assert blocos[0] == '07:00'
    assert blocos[-1] == '18:30'
    assert len(blocos) == 24


class FakeReserva:
    def __init__(self, aeronave_id, inicio, fim):
        self.aeronave_id, self.inicio, self.fim = aeronave_id, inicio, fim


class FakeAeronave:
    id = 1


def test_posicao_na_linha_do_tempo():
    # 08:00 é 1h depois da abertura (07h) num dia de 12h: começa em 8,333% e ocupa 12,5%
    assert posicao(FakeReserva(1, dt(8), dt(9, 30))) == (8.333, 12.5)


def test_grade_marca_blocos_ocupados_e_passados():
    reserva = FakeReserva(1, dt(8), dt(9, 30))
    [linha] = montar_grade(date(2026, 10, 21), [FakeAeronave()], [reserva], agora=dt(7, 15))
    livres = [b['hora'] for b in linha['blocos'] if b['livre']]
    assert '07:00' not in livres          # já passou
    assert '07:30' in livres
    assert '08:00' not in livres and '09:00' not in livres  # reservado
    assert '09:30' in livres
    assert linha['reservas'][0]['r'] is reserva


def test_disponibilidade_divide_o_dia():
    reservas = [FakeReserva(1, dt(10), dt(11, 30)), FakeReserva(1, dt(8), dt(9))]
    trechos = disponibilidade(date(2026, 10, 21), reservas)
    assert [(i.strftime('%H:%M'), f.strftime('%H:%M'), livre) for i, f, livre in trechos] == [
        ('07:00', '08:00', True), ('08:00', '09:00', False), ('09:00', '10:00', True),
        ('10:00', '11:30', False), ('11:30', '19:00', True),
    ]
