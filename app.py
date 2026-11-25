import hmac
import os
import secrets
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user

from modelos import FUNCOES, PAPEIS, TIPOS_DOCUMENTO, Aeronave, Aviso, Documento, Reserva, Usuario, Voo, db
import avisos
import regras
import validades
from seguranca import LimitadorDeTentativas, aplicar_cabecalhos
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
    # Sem SECRET_KEY definida, cria uma aleatória: nunca usa uma chave fixa conhecida.
    # (No Render o render.yaml gera uma; localmente, o login só cai ao reiniciar.)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or secrets.token_hex(32)
    app.config['SQLALCHEMY_DATABASE_URI'] = endereco_banco()
    app.config['DEMO'] = os.getenv('DEMO', '1') == '1'
    # Senha que o agendador diário (GitHub Actions) usa para pedir o envio dos avisos
    app.config['AVISOS_TOKEN'] = os.getenv('AVISOS_TOKEN', '')
    # Cookie de sessão: invisível para JavaScript, não vai junto em links de outros
    # sites e, em produção (HTTPS), só trafega criptografado
    em_producao = bool(os.getenv('RENDER')) or os.getenv('COOKIE_SEGURO') == '1'
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=em_producao,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SECURE=em_producao,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    app.limitador = LimitadorDeTentativas()
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

    @app.cli.command('enviar-avisos')
    def comando_enviar_avisos():
        """flask --app app enviar-avisos: manda os lembretes de vencimento do dia."""
        print(f'{avisos.enviar_pendentes()} aviso(s) enviado(s).')

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


def mostrar_data(dia):
    """28/10/2026 em português, 2026-10-28 em inglês (sem confusão de mês e dia)."""
    return dia.strftime('%d/%m/%Y' if idioma_atual() == 'pt' else '%Y-%m-%d')


def pode_mexer(usuario_id):
    """Cada um mexe só nos próprios documentos e voos; a secretaria mexe em todos."""
    if usuario_id != current_user.id and not current_user.is_admin:
        abort(403)


def documentos_ativos():
    """Documentos de todas as pessoas ativas, do que vence primeiro ao último."""
    return Documento.query.join(Usuario).filter(Usuario.ativo.is_(True)) \
        .order_by(Documento.vencimento).all()


def nome_documento(doc):
    t = textos()
    nome = t['tipo_' + doc.tipo]
    return f"{nome} ({doc.descricao})" if doc.descricao else nome


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
    consulta = Reserva.query.filter(Reserva.fim >= regras.agora_local(), Reserva.cancelada.is_(False))
    if not current_user.is_admin:
        consulta = consulta.filter(
            (Reserva.aluno_id == current_user.id) | (Reserva.instrutor_id == current_user.id))
    return consulta.order_by(Reserva.inicio)


def iniciais(nome):
    nome = nome.removeprefix('Cmte.').strip()  # 'Cmte. Ana Souza' vira 'AS'
    partes = nome.split()
    return ''.join(p[0] for p in (partes[:1] + partes[-1:] if len(partes) > 1 else partes)) or '?'


def contas_demo():
    from demo import USUARIOS
    return USUARIOS


def eh_conta_demo(email):
    return any(email == e for _, e, _ in contas_demo())


def entrar_na_sessao(usuario):
    """Começa uma sessão nova no login (evita reaproveitar uma sessão antiga)."""
    idioma = idioma_atual()
    session.clear()
    session['idioma'] = idioma
    session.permanent = True
    login_user(usuario)


def registrar_rotas(app):

    @app.before_request
    def conferir_csrf():
        # A rota do agendador usa token próprio no cabeçalho, não formulário
        if request.endpoint == 'tarefa_avisos':
            return
        if request.method == 'POST' and not app.config.get('TESTING_SEM_CSRF'):
            enviado = request.form.get('csrf')
            if not enviado or enviado != session.get('csrf'):
                abort(400)

    @app.context_processor
    def variaveis_do_template():
        hoje = regras.hoje_local()
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
            'hoje': hoje,
            'data': mostrar_data,
            'horas': validades.formatar_horas,
            'situacao': lambda doc: validades.situacao(doc.vencimento, hoje),
            'dias': lambda doc: validades.dias_restantes(doc.vencimento, hoje),
            'tipos': TIPOS_DOCUMENTO,
            'funcoes': FUNCOES,
            'pode_registrar': lambda r: current_user.is_authenticated and regras.pode_registrar_voo(current_user, r),
        }

    @app.errorhandler(403)
    def proibido(_erro):
        flash(textos()['sem_permissao'], 'erro')
        return redirect(url_for('agenda'))

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def pagina_de_erro(erro):
        codigo = getattr(erro, 'code', 500)
        if codigo == 500:
            db.session.rollback()
        return render_template('erro.html', codigo=codigo), codigo

    @app.after_request
    def cabecalhos(resposta):
        return aplicar_cabecalhos(resposta)

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
            chave = (request.remote_addr, email)
            if app.limitador.bloqueado(chave):
                flash(textos()['muitas_tentativas'], 'erro')
                return render_template('login.html', contas_demo=contas_demo()), 429
            usuario = Usuario.query.filter_by(email=email).first()
            if usuario and usuario.ativo and usuario.conferir_senha(request.form.get('senha', '')):
                app.limitador.limpar(chave)
                entrar_na_sessao(usuario)
                return redirect(url_for('agenda'))
            app.limitador.registrar_falha(chave)
            # Mesma mensagem para e-mail inexistente e senha errada: não revela quem tem conta
            flash(textos()['login_invalido'], 'erro')
        return render_template('login.html', contas_demo=contas_demo())

    @app.route('/sair', methods=['POST'])
    @login_required
    def sair():
        logout_user()
        idioma = idioma_atual()
        session.clear()
        session['idioma'] = idioma
        return redirect(url_for('login'))

    @app.route('/conta/senha', methods=['GET', 'POST'])
    @login_required
    def trocar_senha():
        t = textos()
        if request.method == 'POST':
            atual = request.form.get('atual', '')
            nova = request.form.get('nova', '')
            if app.config['DEMO'] and eh_conta_demo(current_user.email):
                flash(t['senha_demo'], 'erro')
            elif not current_user.conferir_senha(atual):
                flash(t['senha_atual_errada'], 'erro')
            elif len(nova) < 8:
                flash(t['senha_curta'], 'erro')
            elif nova != request.form.get('confirmar', ''):
                flash(t['senhas_diferentes'], 'erro')
            else:
                current_user.definir_senha(nova)
                db.session.commit()
                flash(t['senha_trocada'], 'ok')
                return redirect(url_for('agenda'))
        return render_template('senha.html')

    @app.route('/saude')
    def saude():
        """O Render consulta esta página para saber se o site está no ar."""
        db.session.execute(db.text('SELECT 1'))
        return {'status': 'ok'}

    # ---------- Agenda ----------

    @app.route('/')
    @login_required
    def agenda():
        dia = ler_data(request.args.get('dia'), regras.hoje_local())
        aeronaves = Aeronave.query.filter_by(ativa=True).order_by(Aeronave.matricula).all()
        reservas = reservas_do_dia(dia)
        agora = regras.agora_local()
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
            hoje=regras.hoje_local(),
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
            dia = ler_data(form.get('data'), regras.hoje_local())
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
                'data': request.args.get('dia', regras.hoje_local().isoformat()),
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
        erros, vencidos = [], []
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
                # Ninguém voa com CMA ou habilitação vencidos na data do voo
                vencidos = validades.vencidos_no_dia(aluno, dia)
                if instrutor:
                    vencidos += validades.vencidos_no_dia(instrutor, dia, como_instrutor=True)

        if erros or vencidos:
            mensagens = [t[e].format(abertura=regras.HORA_ABERTURA, fechamento=regras.HORA_FECHAMENTO)
                         for e in erros]
            mensagens += [t['doc_vencido'].format(nome=d.dono.nome, doc=nome_documento(d),
                                                   data=mostrar_data(d.vencimento)) for d in vencidos]
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
        agora = regras.agora_local()
        proximas = minhas_proximas().all()
        historico = consulta.filter((Reserva.fim < agora) | Reserva.cancelada.is_(True)) \
            .order_by(Reserva.inicio.desc()).limit(50).all()
        return render_template('minhas.html', proximas=proximas, historico=historico)

    @app.route('/reservas/<int:reserva_id>/voo', methods=['POST'])
    @login_required
    def registrar_voo_da_reserva(reserva_id):
        """Transforma uma reserva realizada em horas de voo do aluno (e do instrutor)."""
        t = textos()
        reserva = db.session.get(Reserva, reserva_id) or abort(404)
        if not regras.pode_registrar_voo(current_user, reserva):
            abort(403)
        minutos = validades.ler_duracao(request.form.get('tempo'))
        try:
            pousos = int(request.form.get('pousos') or 0)
        except ValueError:
            pousos = -1
        if minutos is None:
            flash(t['tempo_invalido'], 'erro')
        elif not 0 <= pousos <= 99:
            flash(t['dados_invalidos'], 'erro')
        else:
            comum = dict(reserva_id=reserva.id, data=reserva.inicio.date(), minutos=minutos,
                         matricula=reserva.aeronave.matricula, observacao=reserva.observacao or '')
            db.session.add(Voo(usuario_id=reserva.aluno_id, pousos=pousos,
                               funcao='instrucao' if reserva.instrutor_id else 'solo', **comum))
            if reserva.instrutor_id:
                db.session.add(Voo(usuario_id=reserva.instrutor_id, pousos=pousos, funcao='instrutor', **comum))
            db.session.commit()
            flash(t['voo_salvo'], 'ok')
        voltar = request.form.get('voltar', '')
        if not voltar.startswith('/') or voltar.startswith('//'):
            voltar = url_for('minhas_reservas')
        return redirect(voltar)

    # ---------- Documentos ----------

    def voltar_para(dono_id):
        if dono_id != current_user.id:
            return url_for('perfil_usuario', usuario_id=dono_id)
        return url_for('documentos')

    @app.route('/documentos', methods=['GET', 'POST'])
    @login_required
    def documentos():
        t = textos()
        if request.method == 'POST':
            # A secretaria pode cadastrar para outra pessoa (vem da página da pessoa)
            try:
                dono_id = int(request.form.get('usuario_id') or current_user.id)
            except ValueError:
                abort(400)
            pode_mexer(dono_id)
            tipo = request.form.get('tipo', '')
            vencimento = ler_data(request.form.get('vencimento'))
            if tipo not in TIPOS_DOCUMENTO or not vencimento or not db.session.get(Usuario, dono_id):
                flash(t['dados_invalidos'], 'erro')
            else:
                db.session.add(Documento(usuario_id=dono_id, tipo=tipo, vencimento=vencimento,
                                         descricao=request.form.get('descricao', '').strip()[:80]))
                db.session.commit()
                flash(t['documento_salvo'], 'ok')
            return redirect(voltar_para(dono_id))
        return render_template('documentos.html', lista=current_user.documentos)

    @app.route('/documentos/<int:documento_id>/renovar', methods=['POST'])
    @login_required
    def renovar_documento(documento_id):
        doc = db.session.get(Documento, documento_id) or abort(404)
        pode_mexer(doc.usuario_id)
        vencimento = ler_data(request.form.get('vencimento'))
        if not vencimento:
            flash(textos()['dados_invalidos'], 'erro')
        else:
            doc.vencimento = vencimento
            db.session.commit()
            flash(textos()['documento_renovado'], 'ok')
        return redirect(voltar_para(doc.usuario_id))

    @app.route('/documentos/<int:documento_id>/excluir', methods=['POST'])
    @login_required
    def excluir_documento(documento_id):
        doc = db.session.get(Documento, documento_id) or abort(404)
        pode_mexer(doc.usuario_id)
        dono_id = doc.usuario_id
        db.session.delete(doc)
        db.session.commit()
        flash(textos()['documento_excluido'], 'ok')
        return redirect(voltar_para(dono_id))

    # ---------- Horas de voo ----------

    @app.route('/voos', methods=['GET', 'POST'])
    @login_required
    def voos():
        """Voos lançados à mão (ex: horas anteriores ao sistema). Os da agenda entram sozinhos."""
        t = textos()
        form = {}
        if request.method == 'POST':
            form = request.form
            dia = ler_data(form.get('data'))
            minutos = validades.ler_duracao(form.get('tempo'))
            matricula = form.get('matricula', '').strip().upper()
            funcao = form.get('funcao', '')
            try:
                pousos = int(form.get('pousos') or 0)
            except ValueError:
                pousos = -1
            erros = []
            if not dia or not matricula or funcao not in FUNCOES or not 0 <= pousos <= 99:
                erros.append(t['dados_invalidos'])
            elif dia > regras.hoje_local():
                erros.append(t['voo_futuro'])
            if minutos is None:
                erros.append(t['tempo_invalido'])
            if not erros:
                db.session.add(Voo(usuario_id=current_user.id, data=dia, matricula=matricula[:10],
                                   funcao=funcao, minutos=minutos, pousos=pousos,
                                   observacao=form.get('observacao', '').strip()[:200]))
                db.session.commit()
                flash(t['voo_salvo'], 'ok')
                return redirect(url_for('voos'))
            for erro in erros:
                flash(erro, 'erro')
        status = 400 if request.method == 'POST' else 200
        return render_template('voos.html', lista=current_user.voos, form=form,
                               resumo=validades.totais(current_user.voos)), status

    @app.route('/voos/<int:voo_id>/excluir', methods=['POST'])
    @login_required
    def excluir_voo(voo_id):
        voo = db.session.get(Voo, voo_id) or abort(404)
        pode_mexer(voo.usuario_id)
        db.session.delete(voo)
        db.session.commit()
        flash(textos()['voo_excluido'], 'ok')
        return redirect(url_for('voos'))

    # ---------- Secretaria ----------

    @app.route('/secretaria')
    @login_required
    def secretaria():
        somente('admin')
        hoje = regras.hoje_local()
        documentos = documentos_ativos()
        desde = hoje - timedelta(days=30)
        voos_30 = Voo.query.filter(Voo.data > desde).all()
        sem_registro = [r for r in Reserva.query.filter(
            Reserva.cancelada.is_(False),
            Reserva.fim <= regras.agora_local(),
            Reserva.inicio >= datetime.combine(desde, datetime.min.time()),
        ).order_by(Reserva.inicio.desc()).all() if not r.voo_registrado]
        return render_template(
            'secretaria.html',
            contagem=validades.contar_situacoes(documentos, hoje),
            atencao=[d for d in documentos if validades.situacao(d.vencimento, hoje) != 'em_dia'],
            pendentes=len(avisos.pendentes(hoje)),
            por_aeronave=validades.horas_por_aeronave(voos_30),
            sem_registro=sem_registro,
        )

    @app.route('/usuarios/<int:usuario_id>')
    @login_required
    def perfil_usuario(usuario_id):
        somente('admin')
        usuario = db.session.get(Usuario, usuario_id) or abort(404)
        return render_template('perfil.html', usuario=usuario, resumo=validades.totais(usuario.voos))

    @app.route('/avisos')
    @login_required
    def lista_avisos():
        somente('admin')
        historico = Aviso.query.order_by(Aviso.enviado_em.desc()).limit(50).all()
        return render_template('avisos.html', pendentes=avisos.pendentes(), historico=historico,
                               smtp=bool(avisos.configuracao_smtp()['host']))

    @app.route('/avisos/enviar', methods=['POST'])
    @login_required
    def enviar_avisos():
        somente('admin')
        try:
            quantos = avisos.enviar_pendentes()
        except OSError:  # Servidor de e-mail fora do ar ou senha errada
            db.session.rollback()
            flash(textos()['email_falhou'], 'erro')
        else:
            flash(textos()['avisos_enviados'].format(n=quantos), 'ok')
        return redirect(url_for('lista_avisos'))

    @app.route('/tarefas/avisos', methods=['POST'])
    def tarefa_avisos():
        """Chamada uma vez por dia pelo GitHub Actions (ver .github/workflows/avisos.yml)."""
        token = app.config['AVISOS_TOKEN']
        enviado = request.headers.get('Authorization', '').removeprefix('Bearer ')
        if not token or not hmac.compare_digest(enviado, token):
            abort(404)  # Sem token configurado, a rota nem "existe"
        return {'enviados': avisos.enviar_pendentes()}

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
            elif len(senha) < 8:
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
