from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from pybreaker import CircuitBreaker, CircuitBreakerError

# Configuração inicial da aplicação Flask
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicialização do SQLAlchemy para interação com o banco de dados
db = SQLAlchemy(app)

# Configuração do Circuit Breaker para controle de falhas em operações críticas
breaker = CircuitBreaker(fail_max=3, reset_timeout=60)

# Definição dos modelos de dados utilizando SQLAlchemy ORM

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    saldo = db.Column(db.Float, nullable=False)
    ultima_transacao = db.Column(db.DateTime, nullable=True)

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    remetente = db.Column(db.Integer, nullable=False)
    recebedor = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.Integer, default=0)
    horario = db.Column(db.DateTime, nullable=False)
    chave_unica = db.Column(db.String(64), nullable=False)

class Validador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), nullable=False)
    ip = db.Column(db.String(15), nullable=False)
    chave_unica = db.Column(db.String(64), nullable=False)

# Rota para validação de transações por parte do validador
@app.route('/validador/validar', methods=['POST'])
def validar_transacao():
    data = request.get_json()
    transacao_id = data.get('transacao_id')
    validador_id = data.get('validador_id')

    # Verificação da existência dos IDs de transação e validador na requisição
    if not transacao_id or not validador_id:
        return jsonify({"error": "IDs de transação ou validador não fornecidos"}), 400

    # Busca da transação e do validador no banco de dados
    transacao = Transacao.query.get(transacao_id)
    validador = Validador.query.get(validador_id)

    # Verificação da existência da transação e do validador no banco de dados
    if not transacao or not validador:
        return jsonify({"error": "Transação ou validador não encontrados"}), 404

    try:
        # Bloco protegido pelo Circuit Breaker para operações críticas
        with breaker.context():
            # Validação da transação com base nas regras estabelecidas
            if not validar_transacao_saldo(transacao) or \
               not validar_horario_transacao(transacao) or \
               not validar_limite_transacoes(transacao) or \
               not validar_chave_unica(transacao, validador):
                transacao.status = 2  # Transação não aprovada
            else:
                transacao.status = 1  # Transação aprovada
                atualizar_saldo_e_ultima_transacao(transacao)

            # Confirmação das alterações no banco de dados
            db.session.commit()
            return jsonify({"status": transacao.status}), 200

    except CircuitBreakerError:
        # Tratamento de erro caso o Circuit Breaker registre falhas nas operações
        return jsonify({"error": "Erro ao processar a transação. Tente novamente mais tarde."}), 503

# Função para validar se o remetente possui saldo suficiente para a transação
def validar_transacao_saldo(transacao):
    remetente = Cliente.query.get(transacao.remetente)
    taxa = transacao.valor * 0.05  # Taxa de 5% sobre o valor da transação

    return remetente.saldo >= transacao.valor + taxa

# Função para validar se o horário da transação está dentro dos limites permitidos
def validar_horario_transacao(transacao):
    now = datetime.utcnow()
    remetente = Cliente.query.get(transacao.remetente)
    return transacao.horario <= now and (remetente.ultima_transacao is None or transacao.horario > remetente.ultima_transacao)

# Função para validar se o remetente não ultrapassou o limite de transações por minuto
def validar_limite_transacoes(transacao):
    um_minuto_atras = datetime.utcnow() - timedelta(minutes=1)
    transacoes_recentes = Transacao.query.filter(
        Transacao.remetente == transacao.remetente,
        Transacao.horario > um_minuto_atras
    ).count()
    return transacoes_recentes <= 100

# Função para validar se a chave única do validador corresponde à da transação
def validar_chave_unica(transacao, validador):
    return transacao.chave_unica == validador.chave_unica

# Função para atualizar o saldo do remetente e registrar a última transação
def atualizar_saldo_e_ultima_transacao(transacao):
    remetente = Cliente.query.get(transacao.remetente)
    taxa = transacao.valor * 0.05  # Taxa de 5% sobre o valor da transação
    remetente.saldo -= (transacao.valor + taxa)
    remetente.ultima_transacao = transacao.horario
    db.session.commit()

# Inicialização do banco de dados e execução da aplicação Flask
if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
