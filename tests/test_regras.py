from datetime import date, datetime

from regras import horarios_do_dia, montar_grade, sobrepoe, validar_horario

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


def test_grade_junta_blocos_da_reserva():
    reserva = FakeReserva(1, dt(8), dt(9, 30))
    [(_, celulas)] = montar_grade(date(2026, 10, 21), [FakeAeronave()], [reserva])
    # 07:00 e 07:30 livres, depois a reserva ocupando 3 blocos (08:00 a 09:30)
    assert celulas[0] == ('livre', 1, '07:00')
    assert celulas[2] == ('reserva', 3, reserva)
    assert sum(tamanho for _, tamanho, _ in celulas) == 24
