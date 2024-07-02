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
import time

# Inicializa o aplicativo Flask.
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'  # Define a URI do banco de dados SQLite.
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Desabilita o rastreamento de modificações do SQLAlchemy para melhorar a performance.
app.config['DEBUG'] = True  # Habilita o modo debug.

# Inicializa o SQLAlchemy e o Migrate para o gerenciamento do banco de dados.
db = SQLAlchemy(app)  # Conecta o SQLAlchemy ao aplicativo Flask.
migrate = Migrate(app, db)  # Habilita migrações do banco de dados.

# Configura o log.
logging.basicConfig(level=logging.DEBUG)
app.logger.setLevel(logging.DEBUG)

# Configura o log de arquivo com um handler rotativo.
if not os.path.exists('logs'):  # Cria o diretório de logs se não existir.
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/seletor.log', maxBytes=10240, backupCount=10)  # Define um log rotativo.
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.info('Seletor startup')

# Define o modelo de dados para o Validador usando SQLAlchemy.
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

    id = db.Column(db.Integer, primary_key=True)  # Chave primária.
    nome = db.Column(db.String(100), nullable=False)  # Nome do validador.
    ip = db.Column(db.String(21), nullable=False)  # IP do validador.
    saldo = db.Column(db.Integer, nullable=False)  # Saldo do validador.
    flags = db.Column(db.Integer, default=0)  # Número de flags do validador.
    escolhas_consecutivas = db.Column(db.Integer, default=0)  # Número de escolhas consecutivas.
    vezes_banido = db.Column(db.Integer, default=0)  # Número de vezes banido.
    retorno_pendente = db.Column(db.Boolean, default=False)  # Indica se o retorno está pendente.
    em_hold = db.Column(db.Integer, default=0)  # Número de ciclos em hold.
    chave_unica = db.Column(db.String(20), nullable=False)  # Chave única do validador.

    def __repr__(self):
        return f"<Validador {self.nome}>"

    # Incrementa o número de flags do validador e bane se necessário.
    def incrementar_flags(self):
        self.flags += 1
        if self.flags > 2:
            self.banir_validador()

    # Bane o validador e atualiza suas informações no banco de dados.
    def banir_validador(self):
        self.vezes_banido += 1
        if self.vezes_banido > 2:
            db.session.delete(self)  # Remove o validador do banco de dados.
        else:
            self.saldo = 0  # Reseta o saldo do validador.
            self.retorno_pendente = True  # Marca o retorno como pendente.
            self.flags = 0  # Reseta as flags.
        db.session.commit()  # Salva as mudanças no banco de dados.

    # Coloca o validador em hold se tiver muitas escolhas consecutivas.
    def colocar_em_hold(self):
        if self.escolhas_consecutivas >= 5:
            self.em_hold = 5
            self.escolhas_consecutivas = 0  # Reseta as escolhas consecutivas.
        db.session.commit()  # Salva as mudanças no banco de dados.

    # Reintegra o validador com um depósito mínimo necessário.
    def reintegrar(self, deposito):
        #Ajuste para se sempre sempre precisar de +50 para entrar novamente
        saldo_necessário = 50 * self.vezes_banido
        if deposito >= saldo_necessário:
            self.saldo = deposito  # Atualiza o saldo.
            self.retorno_pendente = False  # Marca o retorno como não pendente.
            self.flags = 0  # Reseta as flags.
            db.session.commit()  # Salva as mudanças no banco de dados.
            return True
        return False

# Rota para reintegrar um validador com um depósito mínimo.
@app.route('/reintegrar_validador/<int:validador_id>', methods=['POST'])
def reintegrar_validador(validador_id):
    deposito = request.json.get('deposito')  # Obtém o depósito do corpo da requisição.
    validador = db.session.get(Validador, validador_id)
    if validador and validador.retorno_pendente:  # Verifica se o validador está pendente para retorno.
        if validador.reintegrar(deposito):  # Tenta reintegrar o validador.
            return jsonify({'message': 'Validador reintegrado com sucesso.'}), 200
        else:
            return jsonify({'error': 'Depósito insuficiente ou validador não está elegível para retorno.'}), 400
    return jsonify({'error': 'Validador não encontrado.'}), 404

# Rota para processar uma transação.
@app.route('/transacoes', methods=['POST'])
def processar_transacao():
    try:
        transacao = request.json  # Obtém a transação do corpo da requisição.
        app.logger.info(f'Recebendo transação: {transacao}')
        validadores_selecionados = selecionar_validadores(transacao['valor'])  # Seleciona validadores para a transação.

        if len(validadores_selecionados) < 3:
            app.logger.warning('Validadores insuficientes para processar a transação.')
            return jsonify({'error': 'Não há validadores suficientes. Tente novamente mais tarde.'}), 503

        resultado_consenso = processar_consenso(validadores_selecionados, transacao)  # Processa o consenso.
        app.logger.info(f'Resultado do consenso: {resultado_consenso}')
        return jsonify(resultado_consenso)
    except Exception as e:
        app.logger.error(f'Erro ao processar transação: {str(e)}')
        return jsonify({'error': 'Erro interno do servidor'}), 500

# Função para selecionar validadores para uma transação.
def selecionar_validadores(valor_transacao):
    try:
        validadores_potenciais = Validador.query.filter(Validador.saldo >= 50).all()  # Obtém validadores com saldo >= 50.
        validadores_filtrados = []
        for v in validadores_potenciais:
            if v.flags > 2:
                continue  # Pula validadores com mais de 2 flags.
            peso = v.saldo
            if v.flags == 1:
                peso *= 0.5  # Reduz o peso se o validador tiver 1 flag.
            elif v.flags == 2:
                peso *= 0.25  # Reduz mais ainda o peso se o validador tiver 2 flags.
            validadores_filtrados.append((v, peso))

        total_peso = sum(peso for _, peso in validadores_filtrados)  # Calcula o peso total.
        max_peso = 0.2 * total_peso  # Define o peso máximo permitido.
        validadores_filtrados = [(v, min(peso, max_peso)) for v, peso in validadores_filtrados]

        validadores_escolhidos = []
        if len(validadores_filtrados) >= 3:
            validadores_escolhidos = random.choices(
                [v for v, _ in validadores_filtrados],
                weights=[peso for _, peso in validadores_filtrados],
                k=3
            )  # Seleciona 3 validadores aleatoriamente com base no peso.
        else:
            time.sleep(60)
            return selecionar_validadores(valor_transacao)

        for validator in validadores_escolhidos:
            validator.escolhas_consecutivas += 1  # Incrementa as escolhas consecutivas.
            validator.colocar_em_hold()  # Coloca o validador em hold se necessário.
            db.session.commit()  # Salva as mudanças no banco de dados.

        app.logger.info(f'Validadores selecionados: {[v.nome for v in validadores_escolhidos]}')
        return validadores_escolhidos
    except Exception as e:
        app.logger.error(f'Erro ao selecionar validadores: {str(e)}')
        raise

# Função para processar o consenso entre os validadores.
def processar_consenso(validadores, transacao):
    try:
        votos = []
        for validador in validadores:
            url = f"http://{validador.ip}/validar_transacao"  # URL do endpoint de validação do validador.
            headers = {'Content-Type': 'application/json'}
            resposta = requests.post(url, json=transacao, headers=headers, timeout=5)  # Envia a transação para validação.
            if resposta.status_code == 200:
                votos.append(resposta.json())  # Adiciona o voto à lista de votos.
            else:
                validador.incrementar_flags()  # Incrementa as flags se houver erro na resposta.

        votos_sim = sum(1 for voto in votos if voto['decisao'] == 'sim')
        votos_nao = sum(1 for voto in votos if voto['decisao'] == 'nao')

        resultado = 'sim' if votos_sim > votos_nao else 'nao'  # Determina o resultado do consenso.
        if resultado == 'nao':
            for validador in validadores:
                validador.incrementar_flags()  # Incrementa as flags se a decisão for "não".
        return {'resultado': resultado}
    except Exception as e:
        app.logger.error(f'Erro ao processar consenso: {str(e)}')
        raise

# Inicializa o aplicativo.
if __name__ == '__main__':
    app.run(debug=True)

"""
Implementar funcionalidades de inserção e remoção de validadores.
Sincronizar o tempo entre o sistema seletor e os validadores.
Melhorar o armazenamento de logs para incluir mais detalhes sobre cada eleição de validadores.
Implementar mecanismos explícitos de tolerância a falhas, como tratamento de exceções e recuperação.

"""
