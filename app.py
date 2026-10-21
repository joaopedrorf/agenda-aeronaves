import os
import secrets
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from modelos import PAPEIS, Aeronave, Reserva, Usuario, db
import regras
from textos import TEXTOS

load_dotenv()


def endereco_banco():
    """SQLite local por padrão; no Render, usa o DATABASE_URL do Postgres se existir."""
    url = os.getenv('DATABASE_URL', 'sqlite:///agendamento.db')
    # O Render entrega 'postgres://', mas o SQLAlchemy só aceita 'postgresql://'
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


def create_app(config=None):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'troque-esta-chave-em-producao')
    app.config['SQLALCHEMY_DATABASE_URI'] = endereco_banco()
    app.config['DEMO'] = os.getenv('DEMO', '1') == '1'
    if config:
        app.config.update(config)

    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = 'login'

    @login_manager.user_loader
    def carregar_usuario(usuario_id):
        return db.session.get(Usuario, int(usuario_id))

    @login_manager.unauthorized_handler
    def sem_login():
        flash(textos()['precisa_login'], 'erro')
        return redirect(url_for('login'))

    with app.app_context():
        db.create_all()
        if app.config['DEMO']:
            from demo import criar_demo
            criar_demo()

    registrar_rotas(app)

    @app.cli.command('criar-demo')
    def comando_criar_demo():
        """flask --app app criar-demo: preenche o banco com dados de exemplo."""
        from demo import criar_demo
        print('Dados criados.' if criar_demo() else 'O banco já tem dados.')

    return app


# ---------- Idioma e segurança ----------

def idioma_atual():
    idioma = session.get('idioma', 'pt')
    return idioma if idioma in TEXTOS else 'pt'


def textos():
    return TEXTOS[idioma_atual()]


def token_csrf():
    """Token secreto por sessão: impede que outro site envie formulários em nome do usuário."""
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(16)
    return session['csrf']


def somente(*papeis):
    if current_user.papel not in papeis:
        abort(403)


def ler_data(texto, padrao=None):
    try:
        return datetime.strptime(texto, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return padrao


def data_por_extenso(dia):
    """Ex: 'Quarta, 22 de outubro' / 'Wednesday, October 22'."""
    t = textos()
    return t['formato_dia'].format(semana=t['semana'][dia.weekday()],
                                   dia=dia.day, mes=t['meses'][dia.month - 1])


def data_curta(dia):
    """Ex: 'Qua 22/10' / 'Wed 10/22'."""
    t = textos()
    return t['formato_curto'].format(semana=t['semana_curta'][dia.weekday()],
                                     dia=dia.day, mes=dia.month)


def reservas_do_dia(dia):
    inicio_dia = datetime.combine(dia, datetime.min.time())
    return Reserva.query.filter(
        Reserva.cancelada.is_(False),
        Reserva.inicio >= inicio_dia,
        Reserva.inicio < inicio_dia + timedelta(days=1),
    ).order_by(Reserva.inicio).all()


def minhas_proximas():
    """Reservas futuras de quem está logado (a secretaria vê as de todos)."""
    consulta = Reserva.query.filter(Reserva.fim >= datetime.now(), Reserva.cancelada.is_(False))
    if not current_user.is_admin:
        consulta = consulta.filter(
            (Reserva.aluno_id == current_user.id) | (Reserva.instrutor_id == current_user.id))
    return consulta.order_by(Reserva.inicio)


def iniciais(nome):
    nome = nome.removeprefix('Cmte.').strip()  # 'Cmte. Ana Souza' vira 'AS'
    partes = nome.split()
    return ''.join(p[0] for p in (partes[:1] + partes[-1:] if len(partes) > 1 else partes)) or '?'


def registrar_rotas(app):

    @app.before_request
    def conferir_csrf():
        if request.method == 'POST' and not app.config.get('TESTING_SEM_CSRF'):
            enviado = request.form.get('csrf')
            if not enviado or enviado != session.get('csrf'):
                abort(400)

    @app.context_processor
    def variaveis_do_template():
        return {
            't': textos(),
            'idioma': idioma_atual(),
            'csrf': token_csrf(),
            'demo': app.config['DEMO'],
            'iniciais': iniciais,
            'data_curta': data_curta,
            'pagina': request.endpoint,
            'abertura': regras.HORA_ABERTURA,
            'fechamento': regras.HORA_FECHAMENTO,
        }

    @app.errorhandler(403)
    def proibido(_erro):
        flash(textos()['sem_permissao'], 'erro')
        return redirect(url_for('agenda'))

    @app.route('/idioma/<codigo>')
    def trocar_idioma(codigo):
        if codigo in TEXTOS:
            session['idioma'] = codigo
        destino = request.referrer or url_for('agenda')
        # Só volta para páginas do próprio site
        if not destino.startswith(request.host_url):
            destino = url_for('agenda')
        return redirect(destino)

    # ---------- Login ----------

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('agenda'))
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            usuario = Usuario.query.filter_by(email=email).first()
            if usuario and usuario.ativo and usuario.conferir_senha(request.form.get('senha', '')):
                login_user(usuario)
                return redirect(url_for('agenda'))
            flash(textos()['login_invalido'], 'erro')
        from demo import USUARIOS
        return render_template('login.html', contas_demo=USUARIOS)

    @app.route('/sair', methods=['POST'])
    @login_required
    def sair():
        logout_user()
        return redirect(url_for('login'))

    # ---------- Agenda ----------

    @app.route('/')
    @login_required
    def agenda():
        dia = ler_data(request.args.get('dia'), date.today())
        aeronaves = Aeronave.query.filter_by(ativa=True).order_by(Aeronave.matricula).all()
        reservas = reservas_do_dia(dia)
        agora = datetime.now()
        proximos = minhas_proximas().limit(3).all()
        resumo = regras.resumo_do_dia(reservas, aeronaves)
        horas_texto = f"{resumo['horas']:g}"
        if idioma_atual() == 'pt':
            horas_texto = horas_texto.replace('.', ',')  # 5,5 h
        return render_template(
            'agenda.html',
            dia=dia,
            titulo_dia=data_por_extenso(dia),
            anterior=dia - timedelta(days=1),
            proximo=dia + timedelta(days=1),
            dias=[{'data': d, 'semana': textos()['semana_curta'][d.weekday()]}
                  for d in (dia + timedelta(days=n) for n in range(-1, 4))],
            horas=list(range(regras.HORA_ABERTURA, regras.HORA_FECHAMENTO)),
            grade=regras.montar_grade(dia, aeronaves, reservas, agora),
            resumo=resumo,
            horas_texto=horas_texto,
            proximos=proximos,
            hoje=date.today(),
        )

    @app.route('/reservas/nova', methods=['GET', 'POST'])
    @login_required
    def nova_reserva():
        t = textos()
        aeronaves = Aeronave.query.filter_by(ativa=True).order_by(Aeronave.matricula).all()
        alunos = Usuario.query.filter_by(papel='aluno', ativo=True).order_by(Usuario.nome).all()
        instrutores = Usuario.query.filter_by(papel='instrutor', ativo=True).order_by(Usuario.nome).all()

        def tela(form, erros=(), sugestao=None, status=200):
            """Desenha o formulário com o quadro de disponibilidade da aeronave escolhida."""
            dia = ler_data(form.get('data'), date.today())
            escolhida = next((a for a in aeronaves if str(a.id) == str(form.get('aeronave_id'))),
                             aeronaves[0] if aeronaves else None)
            trechos = []
            if escolhida:
                trechos = regras.disponibilidade(
                    dia, [r for r in reservas_do_dia(dia) if r.aeronave_id == escolhida.id])
            return render_template(
                'nova_reserva.html', aeronaves=aeronaves, alunos=alunos, instrutores=instrutores,
                form=form, erros=list(erros), sugestao=sugestao, escolhida=escolhida,
                trechos=trechos, dia=dia, dia_curto=data_curta(dia),
            ), status

        if request.method == 'GET':
            # A agenda manda aeronave, dia e hora quando o usuário clica num horário livre
            form = {
                'aeronave_id': request.args.get('aeronave', ''),
                'data': request.args.get('dia', date.today().isoformat()),
                'inicio': request.args.get('hora', '08:00'),
                'instrutor_id': request.args.get('instrutor', ''),
                'aluno_id': request.args.get('aluno', ''),
                'observacao': request.args.get('obs', ''),
            }
            try:
                inicio = datetime.strptime(form['inicio'], '%H:%M')
            except ValueError:
                inicio = datetime.strptime('08:00', '%H:%M')
                form['inicio'] = '08:00'
            form['fim'] = request.args.get('fim') or (inicio + timedelta(hours=1)).strftime('%H:%M')
            return tela(form)

        form = request.form
        erros = []
        try:
            dia = datetime.strptime(form['data'], '%Y-%m-%d').date()
            inicio = datetime.combine(dia, datetime.strptime(form['inicio'], '%H:%M').time())
            fim = datetime.combine(dia, datetime.strptime(form['fim'], '%H:%M').time())
            aeronave = db.session.get(Aeronave, int(form['aeronave_id']))
            instrutor_id = int(form['instrutor_id']) if form.get('instrutor_id') else None
            # Aluno só reserva para si mesmo; instrutor e secretaria escolhem o aluno
            if current_user.papel == 'aluno':
                aluno_id = current_user.id
            else:
                aluno_id = int(form['aluno_id'])
        except (KeyError, ValueError):
            erros = ['dados_invalidos']
        else:
            aluno = db.session.get(Usuario, aluno_id)
            instrutor = db.session.get(Usuario, instrutor_id) if instrutor_id else None
            if not aluno or aluno.papel != 'aluno' or (instrutor_id and (not instrutor or instrutor.papel != 'instrutor')):
                erros = ['dados_invalidos']
            elif not aeronave or not aeronave.ativa:
                erros = ['aeronave_inativa']
            else:
                erros = regras.validar_horario(inicio, fim)
                if not erros:
                    erros = regras.conflitos(inicio, fim, aeronave.id, aluno_id, instrutor_id)

        if erros:
            mensagens = [t[e].format(abertura=regras.HORA_ABERTURA, fechamento=regras.HORA_FECHAMENTO)
                         for e in erros]
            sugestao = None
            if any(e.startswith('conflito_') for e in erros):
                sugestao = regras.sugerir(inicio, fim, aeronave.id, aluno_id, instrutor_id, aeronaves)
            return tela(form, mensagens, sugestao, status=400)

        db.session.add(Reserva(
            aeronave_id=aeronave.id, aluno_id=aluno_id, instrutor_id=instrutor_id,
            inicio=inicio, fim=fim, observacao=form.get('observacao', '').strip()[:200],
            criada_por_id=current_user.id,
        ))
        db.session.commit()
        flash(t['reserva_criada'], 'ok')
        return redirect(url_for('agenda', dia=dia.isoformat()))

    @app.route('/reservas/<int:reserva_id>/cancelar', methods=['POST'])
    @login_required
    def cancelar_reserva(reserva_id):
        reserva = db.session.get(Reserva, reserva_id) or abort(404)
        if not regras.pode_cancelar(current_user, reserva):
            abort(403)
        reserva.cancelada = True
        db.session.commit()
        flash(textos()['reserva_cancelada'], 'ok')
        voltar = request.form.get('voltar', '')
        # Só aceita caminhos do próprio site (ex: /?dia=2026-10-21)
        if not voltar.startswith('/') or voltar.startswith('//'):
            voltar = url_for('minhas_reservas')
        return redirect(voltar)

    @app.route('/reservas/minhas')
    @login_required
    def minhas_reservas():
        consulta = Reserva.query
        if not current_user.is_admin:
            consulta = consulta.filter(
                (Reserva.aluno_id == current_user.id) | (Reserva.instrutor_id == current_user.id)
            )
        agora = datetime.now()
        proximas = minhas_proximas().all()
        historico = consulta.filter((Reserva.fim < agora) | Reserva.cancelada.is_(True)) \
            .order_by(Reserva.inicio.desc()).limit(50).all()
        return render_template('minhas.html', proximas=proximas, historico=historico)

    # ---------- Administração ----------

    @app.route('/aeronaves', methods=['GET', 'POST'])
    @login_required
    def aeronaves():
        somente('admin')
        t = textos()
        if request.method == 'POST':
            matricula = request.form.get('matricula', '').strip().upper()
            modelo = request.form.get('modelo', '').strip()
            if not matricula or not modelo:
                flash(t['dados_invalidos'], 'erro')
            elif Aeronave.query.filter_by(matricula=matricula).first():
                flash(t['matricula_existe'], 'erro')
            else:
                db.session.add(Aeronave(matricula=matricula[:10], modelo=modelo[:60]))
                db.session.commit()
                flash(t['aeronave_salva'], 'ok')
            return redirect(url_for('aeronaves'))
        lista = Aeronave.query.order_by(Aeronave.matricula).all()
        return render_template('aeronaves.html', aeronaves=lista)

    @app.route('/aeronaves/<int:aeronave_id>/alternar', methods=['POST'])
    @login_required
    def alternar_aeronave(aeronave_id):
        somente('admin')
        aeronave = db.session.get(Aeronave, aeronave_id) or abort(404)
        aeronave.ativa = not aeronave.ativa
        db.session.commit()
        return redirect(url_for('aeronaves'))

    @app.route('/usuarios', methods=['GET', 'POST'])
    @login_required
    def usuarios():
        somente('admin')
        t = textos()
        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            email = request.form.get('email', '').strip().lower()
            senha = request.form.get('senha', '')
            papel = request.form.get('papel', 'aluno')
            if not nome or '@' not in email or papel not in PAPEIS:
                flash(t['dados_invalidos'], 'erro')
            elif len(senha) < 6:
                flash(t['senha_curta'], 'erro')
            elif Usuario.query.filter_by(email=email).first():
                flash(t['email_existe'], 'erro')
            else:
                u = Usuario(nome=nome[:100], email=email[:120], papel=papel)
                u.definir_senha(senha)
                db.session.add(u)
                db.session.commit()
                flash(t['usuario_salvo'], 'ok')
            return redirect(url_for('usuarios'))
        lista = Usuario.query.order_by(Usuario.papel, Usuario.nome).all()
        return render_template('usuarios.html', usuarios=lista, papeis=PAPEIS)

    @app.route('/usuarios/<int:usuario_id>/alternar', methods=['POST'])
    @login_required
    def alternar_usuario(usuario_id):
        somente('admin')
        usuario = db.session.get(Usuario, usuario_id) or abort(404)
        if usuario.id != current_user.id:  # Ninguém desativa a própria conta
            usuario.ativo = not usuario.ativo
            db.session.commit()
        return redirect(url_for('usuarios'))


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
