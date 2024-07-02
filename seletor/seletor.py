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


######################################################################################################
# Inicializa o aplicativo Flask.
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'  # Define a URI do banco de dados SQLite.
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Desabilita o rastreamento de modificações do SQLAlchemy para melhorar a performance.
app.config['DEBUG'] = True  # Habilita o modo debug.

# Inicializa o SQLAlchemy e o Migrate para o gerenciamento do banco de dados.
db = SQLAlchemy(app)  # Conecta o SQLAlchemy ao aplicativo Flask.
migrate = Migrate(app, db)  # Habilita migrações do banco de dados.


######################################################################################################
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

######################################################################################################

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
    trans_corretas = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Validador {self.nome}>"

    # Incrementa o número de flags do validador e bane se necessário.
    def incrementar_flags(self):
        self.flags += 1
        if self.flags > 2:
            self.banir_validador()

    def decrementar_flags(self):
        if self.flags > 0:
            self.flags -= 1
            self.trans_corretas = 0

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
    
######################################################################################################

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

######################################################################################################

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

# Função modificada para garantir que o peso de escolha não ultrapasse 20%.
def selecionar_validadores(valor_transacao):
    try:
        validadores_potenciais = Validador.query.filter(Validador.saldo >= 50, Validador.flags <= 2).all()
        peso_total = sum(v.saldo for v in validadores_potenciais)
        validadores_escolhidos = []
        
        for v in validadores_potenciais:
            peso = v.saldo * (0.5 if v.flags == 1 else 0.25 if v.flags == 2 else 1)

            # Limitando o peso de escolha a no máximo 20% do total.
            peso_ajustado = min(peso, 0.2 * peso_total)
            if random.random() < peso_ajustado / peso_total:
                validadores_escolhidos.append(v)
                if len(validadores_escolhidos) == 3:
                    break
        
        if len(validadores_escolhidos) < 3:
            time.sleep(60)  # Espera e tenta novamente
            return selecionar_validadores(valor_transacao)
        
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
            response = requests.post(url, json=transacao, headers=headers, timeout=5)  # Envia a transação para validação.
            if response.status_code == 200:
                votos.append((response.json()['status'], validador))
            else:
                validador.incrementar_flags()  # Incrementa as flags se houver erro na response.

        aprovacoes = [v for v, _ in votos if v == 1]

        if len(aprovacoes) > len(votos) / 2:
            transacao['status'] = 1
            distribuir_recompensas(validadores, transacao['valor'])
        else:
            transacao['status'] = 2

        for _, validador in votos:
            if validador.escolhas_consecutivas >= 5:            
                validador.escolhas_consecutivas = 0  # Reset após cada votação, independentemente do resultado
            db.session.commit()

        app.logger.info(f'Resultado dos votos: {votos}')
        return transacao
    except Exception as e:
        app.logger.error(f'Erro ao processar consenso: {str(e)}')
        raise


# Implementação da distribuição de recompensas
def distribuir_recompensas(validadores, valor_transacao):
    total_recompensa = 0.015 * valor_transacao
    recompensa_seletor = 0.005 * valor_transacao
    recompensa_validadores = total_recompensa - recompensa_seletor
    recompensa_individual = recompensa_validadores / len(validadores)
    
    for validador in validadores:
        validador.saldo += recompensa_individual
        db.session.commit()

    app.logger.info(f'Recompensas distribuídas. Seletor: {recompensa_seletor}, Validadores: {recompensa_individual} cada')


@app.route('/validador/<nome>/<ip>', methods=['POST'])
def adicionar_validador(nome, ip):
    try:
        chave_unica = str(uuid.uuid4())
        ip_completo = f"{ip}"

        novo_validador = Validador(
            nome=nome,
            ip=ip_completo,
            ip=ip,  # Use the provided IP, no need to append port here
            saldo=10000,
            flags=0,
            escolhas_consecutivas=0,
            vezes_banido=0,
            retorno_pendente=False,
            em_hold=0,
            chave_unica=chave_unica,
            trans_corretas = 0
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

# Inicializa o aplicativo.
if __name__ == '__main__':
    app.run(debug=True)


# a
