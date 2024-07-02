from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from dataclasses import dataclass
import random
import time

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

@dataclass
class Validador(db.Model):
    """
    Modelo de validador para a base de dados.
    Armazena informações sobre cada validador, incluindo id, nome, IP, saldo, flags, escolhas, etc.
    """
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), nullable=False)
    ip = db.Column(db.String(15), nullable=False)
    saldo = db.Column(db.Integer, nullable=False)
    flags = db.Column(db.Integer, default=0)
    consecutivas = db.Column(db.Integer, default=0)
    escolhas = db.Column(db.Integer, default=0)
    recompensas = db.Column(db.Float, default=0.0)
    transacoes_coerentes = db.Column(db.Integer, default=0)
    reintegracoes = db.Column(db.Integer, default=0)

@dataclass
class Transacao(db.Model):
    """
    Modelo de transação para a base de dados.
    Armazena informações sobre cada transação, incluindo id, valor, status e relacionamento com validadores.
    """
    id = db.Column(db.Integer, primary_key=True)
    valor = db.Column(db.Integer, nullable=False)
    validadores = db.relationship('Validador', secondary='transacao_validador')
    status = db.Column(db.Integer, default=0)

# Tabela associativa para relacionar transações e validadores
transacao_validador = db.Table('transacao_validador',
    db.Column('transacao_id', db.Integer, db.ForeignKey('transacao.id'), primary_key=True),
    db.Column('validador_id', db.Integer, db.ForeignKey('validador.id'), primary_key=True)
)

@app.route('/validadores', methods=['GET'])  
def listar_validadores():
    validadores = Validador.query.all()
    return jsonify([validador.to_dict() for validador in validadores]), 200



@app.route('/seletor/registrar', methods=['POST'])
def registrar_validador():
    """
    Registra um novo validador no sistema.
    Requer um saldo mínimo para o registro e retorna erro se o saldo não for suficiente.
    """
    data = request.get_json()

    # Não registra o validador caso seu saldo seja menor que 50.
    if data['saldo'] < 50:
        return jsonify({"error": "Saldo insuficiente para registrar validador"}), 400
    
    # Cria validador
    novo_validador = Validador(
        nome=data['nome'],
        ip=data['ip'],
        saldo=data['saldo'],
        flags=0,
        consecutivas=0,
        escolhas=0
    )

    # Adiciona validador no banco de dados.
    db.session.add(novo_validador)
    db.session.commit()

    # Retorna mensagem indicando que o registro foi feito.
    return jsonify({"message": "Validador registrado com sucesso", "validador_id": novo_validador.id}), 201



@app.route('/seletor/selecionar', methods=['POST'])
def selecionar_validadores():
    """
    Seleciona validadores para uma transação com base no valor da transação e critérios como saldo e flags.
    Implementa um mecanismo de espera caso menos de três validadores estejam disponíveis.
    """
    data = request.get_json()

    # Procura transação pelo seu ID.
    transacao_id = data['transacao_id']
    transacao = Transacao.query.get(transacao_id)
    if not transacao:
        return jsonify({"error": "Transação não encontrada"}), 404

    try:
        # Faz a escolha dos validadores.
        validadores = escolher_validadores(transacao.valor)

        # Se houver menos de 3 validadores, entra em espera de 60 segundos e tenta novamente.
        if len(validadores) < 3:
            time.sleep(60)
            return selecionar_validadores()

        for validador in validadores:
            transacao.validadores.append(validador) #Adiciona na lista de validadores da transação
            validador.escolhas += 1

            # Atualiza as vezes consecutivas ou reseta.
            validador.consecutivas = (validador.consecutivas + 1) if validador.consecutivas >= 0 else -5

            # Distribui a recomensa proporcional ao valor da transação entre os validadores.
            recompensa = 0.015 * transacao.valor
            validador.recompensas += recompensa / len(validadores)

        db.session.commit()
        return jsonify({"message": "Validadores selecionados com sucesso", "validadores": [v.id for v in validadores]}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500



def escolher_validadores(valor_transacao):
    """
    Auxiliar para selecionar validadores com base em critérios como saldo e número de flags.
    Retorna uma lista de validadores selecionados.
    """
    # Seleciona candidatos que tenham saldo maior ou igual a 50 e tenham no máximo 2 flags.
    candidatos = Validador.query.filter(Validador.saldo >= 50, Validador.flags <= 2).all()

    # Lista que irá armazenar os validadores selecionados.
    selecionados = []

    for validador in candidatos:
        # Ignora validadores em Hold.
        if validador.consecutivas < 0:
            continue
        
        # Faz o cálculo da chance (metade da razão entre o saldo do validador e o valor da transação, mas limitada a um máximo de 20%)
        chance = min(validador.saldo / valor_transacao / 2, 0.20)

        # Se houver uma flag, a chance é reduzida pela metade.
        if validador.flags == 1:
            chance *= 0.5
        # Se houver duas flags, a chance é reduzida a um quarto.
        elif validador.flags == 2:
            chance *= 0.25

        # Gera um número aleatório, e se ele for menor que a chance o validador é adicionado à lista. 
        if random.random() < chance:
            selecionados.append(validador)
            if len(selecionados) >= 3:
                break

    # Retorna lista de validadores selecionados.
    return selecionados


@app.route('/seletor/consenso', methods=['POST'])
def calcular_consenso():
    """
    Calcula o consenso para uma transação com base nos resultados fornecidos pelos validadores.
    Atualiza o status da transação de acordo com o consenso alcançado.
    """
    data = request.get_json()
    transacao_id = data['transacao_id']
    resultados = data['resultados']

    aprovacoes = resultados.count(1)
    total_validacoes = len(resultados)

    transacao = Transacao.query.get(transacao_id)
    if not transacao:
        return jsonify({"error": "Transação não encontrada"}), 404

    if aprovacoes > total_validacoes / 2:
        transacao.status = 1
        for validador in transacao.validadores:
            validador.transacoes_coerentes += 1
            verificar_e_atualizar_flags(validador)
    else:
        transacao.status = 2

    db.session.commit()
    return jsonify({"status": transacao.status}), 200

def verificar_e_atualizar_flags(validador):
    """
    Verifica e atualiza as flags de um validador com base no número de transações coerentes.
    """
    if validador.transacoes_coerentes >= 10000:
        validador.flags = max(validador.flags - 1, 0)
        validador.transacoes_coerentes = 0
        db.session.commit()

@app.route('/validador/penalizar/<int:validador_id>', methods=['POST'])
def penalizar_validador(validador_id):
    """
    Penaliza um validador adicionando uma flag ao seu registro.
    Remove o validador da base de dados se o número de flags exceder dois.
    """
    validador = Validador.query.get(validador_id)
    if not validador:
        return jsonify({"error": "Validador não encontrado"}), 404
    
    validador.flags += 1
    if validador.flags > 2:
        db.session.delete(validador)
        db.session.commit()
        return jsonify({"message": "Validador removido devido a excesso de flags"}), 200
    
    db.session.commit()
    return jsonify({"message": "Flag adicionada ao validador"}), 200

@app.route('/validador/reintegrar', methods=['POST'])
def reintegrar_validador():
    """
    Reintegra um validador ao sistema, exigindo um saldo aumentado para reintegrações subsequentes.
    """
    data = request.get_json()
    saldo_requerido = 100 if data['reintegracoes'] == 1 else 50
    if data['saldo'] < saldo_requerido:
        return jsonify({"error": "Saldo insuficiente para reintegrar validador"}), 400
    
    validador_reintegrado = Validador(
        nome=data['nome'],
        ip=data['ip'],
        saldo=data['saldo'],
        flags=0,
        consecutivas=0,
        escolhas=0,
        reintegracoes=data['reintegracoes'] + 1
    )
    db.session.add(validador_reintegrado)
    db.session.commit()
    return jsonify({"message": "Validador reintegrado com sucesso", "validador_id": validador_reintegrado.id}), 201

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)


