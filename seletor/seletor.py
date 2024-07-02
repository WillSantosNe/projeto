import os
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dataclasses import dataclass
import random
import uuid
import requests
import logging
from logging.handlers import RotatingFileHandler

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['DEBUG'] = True

# Initialize SQLAlchemy
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# Setup logging
if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/seletor.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.info('Seletor startup')

@dataclass
class Validador(db.Model):
    id: int
    nome: str
    ip: str
    saldo: int
    flags: int
    escolhas_consecutivas: int
    vezes_banido: int
    retorno_pendente: bool
    em_hold: int
    chave_unica: str

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    ip = db.Column(db.String(21), nullable=False)
    saldo = db.Column(db.Integer, nullable=False)
    flags = db.Column(db.Integer, default=0)
    escolhas_consecutivas = db.Column(db.Integer, default=0)
    vezes_banido = db.Column(db.Integer, default=0)
    retorno_pendente = db.Column(db.Boolean, default=False)
    em_hold = db.Column(db.Integer, default=0)
    chave_unica = db.Column(db.String(20), nullable=False)

    def __repr__(self):
        return f"<Validador {self.nome}>"


    def incrementar_flags(self):
        self.flags += 1
        if self.flags > 2:
            self.banir_validador()

    def banir_validador(self):
        self.vezes_banido += 1
        if self.vezes_banido > 2:
            db.session.delete(self)
        else:
            self.saldo = 0
            self.retorno_pendente = True
            self.flags = 0
        db.session.commit()

    def colocar_em_hold(self):
        if self.escolhas_consecutivas >= 5:
            self.em_hold = 5
            self.escolhas_consecutivas = 0
        db.session.commit()

    def reintegrar(self, deposito):
        saldo_necessário = 100
        if deposito >= saldo_necessário:
            self.saldo = deposito
            self.retorno_pendente = False
            self.flags = 0
            db.session.commit()
            return True
        return False

@app.route('/reintegrar_validador/<int:validador_id>', methods=['POST'])
def reintegrar_validador(validador_id):
    deposito = request.json.get('deposito')
    validador = db.session.get(Validador, validador_id)
    if validador and validador.retorno_pendente:
        if validador.reintegrar(deposito):
            return jsonify({'message': 'Validador reintegrado com sucesso.'}), 200
        else:
            return jsonify({'error': 'Depósito insuficiente ou validador não está elegível para retorno.'}), 400
    return jsonify({'error': 'Validador não encontrado.'}), 404

@app.route('/transacoes', methods=['POST'])
def processar_transacao():
    try:
        transacao = request.json
        app.logger.info(f'Recebendo transação: {transacao}')
        validadores_selecionados = selecionar_validadores(transacao['valor'])

        if len(validadores_selecionados) < 3:
            # colocar para esperar 1 minuto
            app.logger.warning('Validadores insuficientes para processar a transação.')
            return jsonify({'error': 'Não há validadores suficientes. Tente novamente mais tarde.'}), 503

        resultado_consenso = processar_consenso(validadores_selecionados, transacao)
        app.logger.info(f'Resultado do consenso: {resultado_consenso}')
        return jsonify(resultado_consenso)
    except Exception as e:
        app.logger.error(f'Erro ao processar transação: {str(e)}')
        return jsonify({'error': 'Erro interno do servidor'}), 500

def selecionar_validadores(valor_transacao):
    # colocar para nao selecionar o mesmo validador
    try:
        validadores_potenciais = Validador.query.filter(Validador.saldo >= 50).all()
        validadores_filtrados = []
        for v in validadores_potenciais:
            if v.flags > 2:
                continue
            peso = v.saldo
            if v.flags == 1:
                peso *= 0.5
            elif v.flags == 2:
                peso *= 0.25
            validadores_filtrados.append((v, peso))

        total_peso = sum(peso for _, peso in validadores_filtrados)
        max_peso = 0.2 * total_peso
        validadores_filtrados = [(v, min(peso, max_peso)) for v, peso in validadores_filtrados]

        validadores_escolhidos = []
        if len(validadores_filtrados) >= 3:
            validadores_escolhidos = random.choices([v for v, _ in validadores_filtrados], weights=[peso for _, peso in validadores_filtrados], k=3)

        for validator in validadores_escolhidos:
            validator.escolhas_consecutivas += 1
            validator.colocar_em_hold()
            db.session.commit()

        app.logger.info(f'Validadores selecionados: {[v.nome for v in validadores_escolhidos]}')
        return validadores_escolhidos
    except Exception as e:
        app.logger.error(f'Erro ao selecionar validadores: {str(e)}')
        raise

def processar_consenso(validadores, transacao):
    try:
        votos = []
        for validador in validadores:
            # Usando o nome do serviço para a URL
            url = f"http://{validador.ip}/validar_transacao"
            app.logger.info(f'Enviando transação para validador: {validador.nome} em {url}')
            response = requests.post(url, json=transacao)
            if response.status_code == 200:
                votos.append((response.json()['status'], validador))

        aprovacoes = [v for v, _ in votos if v == 1]
        if len(aprovacoes) > len(votos) / 2:
            transacao['status'] = 1
            distribuir_recompensas(validadores, transacao['valor'])
        else:
            transacao['status'] = 2

        for _, validador in votos:
            validador.escolhas_consecutivas = 0  # Reset após cada votação, independentemente do resultado
            db.session.commit()

        app.logger.info(f'Resultado dos votos: {votos}')
        return transacao
    except Exception as e:
        app.logger.error(f'Erro ao processar consenso: {str(e)}')
        raise


def distribuir_recompensas(validadores, valor_transacao):
    try:
        total_recompensa = 0.015 * valor_transacao
        recompensa_seletor = 0.005 * total_recompensa
        recompensa_validadores = total_recompensa - recompensa_seletor
        recompensa_individual = recompensa_validadores / len(validadores)

        for validador in validadores:
            app.logger.info(f'Atualizando saldo do validador {validador.nome} de {validador.saldo} para {validador.saldo + recompensa_individual}')
            validador.saldo += recompensa_individual
            db.session.commit()
    except Exception as e:
        app.logger.error(f'Erro ao distribuir recompensas: {str(e)}')
        raise

@app.route('/validador/<nome>/<ip>', methods=['POST'])
def adicionar_validador(nome, ip):
    try:
        chave_unica = str(uuid.uuid4())
        novo_validador = Validador(
            nome=nome,
            ip=ip,  # Use the provided IP, no need to append port here
            saldo=10000,
            flags=0,
            escolhas_consecutivas=0,
            vezes_banido=0,
            retorno_pendente=False,
            em_hold=0,
            chave_unica=chave_unica
        )
        db.session.add(novo_validador)
        db.session.commit()

        return jsonify({
            'id': novo_validador.id,
            'nome': novo_validador.nome,
            'ip': novo_validador.ip,
            'saldo': novo_validador.saldo,
            'chave_unica': chave_unica
        }), 201
    except Exception as e:
        app.logger.error(f'Erro ao adicionar validador: {str(e)}')
        return jsonify({'error': 'Erro ao adicionar validador'}), 500


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # validador1 = Validador(nome="validador1", ip="validador1:5002", chave_unica="a",saldo=10000,flags=0,escolhas_consecutivas=0,vezes_banido=0,retorno_pendente=False,em_hold=0)
        # validador2 = Validador(nome="validador2", ip="validador2:5003", chave_unica="a",saldo=10000,flags=0,escolhas_consecutivas=0,vezes_banido=0,retorno_pendente=False,em_hold=0)
        # validador3 = Validador(nome="validador3", ip="validador3:5004", chave_unica="a",saldo=10000,flags=0,escolhas_consecutivas=0,vezes_banido=0,retorno_pendente=False,em_hold=0)
        # validador4 = Validador(nome="validador4", ip="validador4:5005", chave_unica="a",saldo=10000,flags=0,escolhas_consecutivas=0,vezes_banido=0,retorno_pendente=False,em_hold=0)


        # db.session.add(validador1)
        # db.session.add(validador2)
        # db.session.add(validador3)
        # db.session.add(validador4)
        # db.session.commit()
    app.run(host='0.0.0.0', port=5001, debug=True)





