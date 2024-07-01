from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from pybreaker import CircuitBreaker, CircuitBreakerError

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Configuração do Circuit Breaker
breaker = CircuitBreaker(fail_max=3, reset_timeout=60)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    saldo = db.Column(db.Integer, nullable=False)
    ultima_transacao = db.Column(db.DateTime, nullable=True)

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    remetente = db.Column(db.Integer, nullable=False)
    recebedor = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Integer, default=0)
    horario = db.Column(db.DateTime, nullable=False)
    chave_unica = db.Column(db.String(64), nullable=False)

class Validador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), nullable=False)
    ip = db.Column(db.String(15), nullable=False)
    chave_unica = db.Column(db.String(64), nullable=False)

@app.route('/validador/validar', methods=['POST'])
def validar_transacao():
    data = request.get_json()
    transacao_id = data['transacao_id']
    validador_id = data['validador_id']

    transacao = Transacao.query.get(transacao_id)
    validador = Validador.query.get(validador_id)

    if not transacao or not validador:
        return jsonify({"error": "Transação ou validador não encontrado"}), 404

    try:
        # Tentar executar a validação com o circuit breaker
        with breaker.context():
            # Verificações de validação
            if not validar_transacao_saldo(transacao) or \
               not validar_horario_transacao(transacao) or \
               not validar_limite_transacoes(transacao) or \
               not validar_chave_unica(transacao, validador):
                transacao.status = 2  # Não aprovada
            else:
                transacao.status = 1  # Concluída com sucesso
                atualizar_saldo_e_ultima_transacao(transacao)  # Atualiza saldo e última transação

            db.session.commit()
            return jsonify({"status": transacao.status}), 200

    except CircuitBreakerError as e:
        return jsonify({"error": "Erro ao processar a transação. Tente novamente mais tarde."}), 503

def validar_transacao_saldo(transacao):
    remetente = Cliente.query.get(transacao.remetente)
    taxa = transacao.valor * 0.05  # Taxa de 5%
    return remetente.saldo >= transacao.valor + taxa

def validar_horario_transacao(transacao):
    now = datetime.utcnow()
    remetente = Cliente.query.get(transacao.remetente)
    return transacao.horario <= now and (remetente.ultima_transacao is None or transacao.horario > remetente.ultima_transacao)

def validar_limite_transacoes(transacao):
    um_minuto_atras = datetime.utcnow() - timedelta(minutes=1)
    transacoes_recentes = Transacao.query.filter(
        Transacao.remetente == transacao.remetente,
        Transacao.horario > um_minuto_atras
    ).count()
    return transacoes_recentes <= 100

def validar_chave_unica(transacao, validador):
    return transacao.chave_unica == validador.chave_unica

def atualizar_saldo_e_ultima_transacao(transacao):
    remetente = Cliente.query.get(transacao.remetente)
    taxa = transacao.valor * 0.05  # Taxa de 5%
    remetente.saldo -= (transacao.valor + taxa)
    remetente.ultima_transacao = transacao.horario
    db.session.commit()

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
