from datetime import datetime
import sys
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import logging
from logging.handlers import RotatingFileHandler

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Setup logging
if not os.path.exists('logs'):
    os.makedirs('logs')

file_handler = RotatingFileHandler('logs/validador.log', maxBytes=10240, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.info('Validador startup')

class Transacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    remetente_id = db.Column(db.Integer, nullable=False)
    recebedor_id = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Float, nullable=False)
    horario = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Integer, default=0)  # 0=Não executada, 1=Sucesso, 2=Erro
    chave_unica = db.Column(db.String(128), nullable=False)

    def __repr__(self):
        return f"<Transacao {self.id}>"

class Validador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), primary_key=False)
    ip = db.Column(db.String(21), nullable=False)
    chave_unica = db.Column(db.String(128), unique=True, nullable=False)
    saldo = db.Column(db.Integer, nullable=False)
    transacoes_no_minuto = db.Column(db.Integer, default=0)
    ultimo_horario = db.Column(db.DateTime, default=datetime.utcnow)
    saldo = db.Column(db.Integer, nullable=False)
    flags = db.Column(db.Integer, default=0)
    escolhas_consecutivas = db.Column(db.Integer, default=0)
    vezes_banido = db.Column(db.Integer, default=0)
    retorno_pendente = db.Column(db.Boolean, default=False)
    em_hold = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<Validador {self.id}>"
    

@app.route('/validar_transacao', methods=['POST'])
def validar_transacao():
    try:
        data = request.json
        app.logger.info(f'Recebendo transação para validação: {data}')
        
        # Ajustar a formatação da data para lidar com microssegundos
        transacao = Transacao(
            remetente_id=data['remetente'],
            recebedor_id=data['recebedor'],
            valor=data['valor'],
            horario=datetime.strptime(data['horario'], "%Y-%m-%dT%H:%M:%S.%f"),
            chave_unica=data['chave_unica']
        )

        validador = Validador.query.filter_by(chave_unica=transacao.chave_unica).first()
        if not validador:
            app.logger.warning(f'Chave única inválida: {transacao.chave_unica}')
            return jsonify({'status': 2}), 400  # Chave única inválida

        # Regra de saldo e taxa
        if validador.saldo < transacao.valor:
            app.logger.warning(f'Saldo insuficiente do validador: {validador.saldo}')
            return jsonify({'status': 2}), 400

        # Regra de horário da transação
        if transacao.horario > datetime.utcnow() or transacao.horario <= validador.ultimo_horario:
            app.logger.warning(f'Horário inválido para a transação: {transacao.horario}')
            return jsonify({'status': 2}), 400

        # Regra de limite de transações
        if validador.transacoes_no_minuto > 100:
            app.logger.warning(f'Limite de transações por minuto excedido')
            return jsonify({'status': 2}), 400

        # Se passar por todas as validações
        validador.ultimo_horario = transacao.horario
        validador.transacoes_no_minuto += 1
        transacao.status = 1  # Aprovada
        db.session.add(transacao)
        db.session.commit()
        return jsonify({'status': 1}), 200
    except Exception as e:
        app.logger.error(f'Erro ao validar transação: {str(e)}')
        return jsonify({'status': 2}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=int(sys.argv[1]), debug=True)


