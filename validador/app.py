from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../site.db'  # Caminho relativo ao banco de dados
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

#cria a transação copiando do banco de dados

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    remetente = db.Column(db.Integer, nullable=False)
    recebedor = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Integer, nullable=False)
    status = db.Column(db.Integer, default=0)  # 0 = Não executada, 1 = Sucesso, 2 = Erro
    horario = db.Column(db.DateTime, nullable=False)

@app.route('/validar_transacao', methods=['POST'])
def validar_transacao():
    data = request.get_json()
    transacao = Transacao.query.get(data['id'])
    
    if not transacao:
        return jsonify({"error": "Transação não encontrada"}), 404

    # Regras de validação conforme as especificadas anteriormente
    if transacao.valor > data['saldo_remetente']:
        transacao.status = 2  # Erro por saldo insuficiente
    else:
        transacao.status = 1  # Sucesso

    db.session.commit()
    return jsonify({"status": transacao.status}), 200



from datetime import datetime, timedelta

@app.route('/validar_transacao/<int:transacao_id>', methods=['POST'])
def validar_transacao(transacao_id):
    # Buscar a transação pelo ID
    transacao = Transacao.query.get(transacao_id)
    if not transacao:
        return jsonify({"error": "Transação não encontrada"}), 404

    # Buscar o cliente remetente para verificar o saldo
    remetente = Cliente.query.get(transacao.remetente)
    if not remetente:
        return jsonify({"error": "Remetente não encontrado"}), 404

    # Verificar se o saldo do remetente cobre o valor da transação + taxas (supondo uma taxa fixa de 5 NoNameCoins)
    taxa = 5
    if remetente.qtdMoeda < transacao.valor + taxa:
        transacao.status = 2  # Erro por saldo insuficiente
        db.session.commit()
        return jsonify({"status": transacao.status}), 200

    # Verificar o horário da transação
    now = datetime.utcnow()
    if transacao.horario > now:
        transacao.status = 2  # Erro por horário futuro
        db.session.commit()
        return jsonify({"status": transacao.status}), 200

    # Verificar o número de transações do remetente no último minuto
    um_minuto_atras = now - timedelta(minutes=1)
    transacoes_recentes = Transacao.query.filter(
        Transacao.remetente == remetente.id,
        Transacao.horario > um_minuto_atras
    ).count()

    if transacoes_recentes > 100:
        transacao.status = 2  # Erro por limite de transações excedido
        db.session.commit()
        return jsonify({"status": transacao.status}), 200

    # Verificação da chave única (supondo que a chave está armazenada em algum lugar acessível)
    chave_seletor = "chave_armazenada"  # Esta deve ser a chave real recuperada do seletor
    if not request.json.get('chave') == chave_seletor:
        transacao.status = 2  # Erro por chave incorreta
        db.session.commit()
        return jsonify({"status": transacao.status}), 200

    # Se todas as verificações passarem, a transação é aprovada
    transacao.status = 1
    db.session.commit()
    return jsonify({"status": transacao.status}), 200





if __name__ == '__main__':
    db.create_all()
    app.run(host='0.0.0.0', port=5001, debug=True)