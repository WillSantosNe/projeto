from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import main
import random
import requests

app = Flask(__name__)

# Configuração do banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../site.db'  # Caminho relativo ao banco de dados
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Validador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    qtdMoeda = db.Column(db.Integer, nullable=False)
    flag = db.Column(db.Integer, default=0)
    status = db.Column(db.Integer, default=0)  # 0: não validado, 1: validado com sucesso, 2: validado com erro
    tentativas = db.Column(db.Integer, default=0)  # Contador de tentativas de validação

    def __repr__(self):
        return f'<Validador {self.nome}>'



@app.route('/validadores', methods=['GET'])
def listar_validadores():
    validadores = Validador.query.all()
    return jsonify([validador.to_dict() for validador in validadores]), 200

@app.route('/validador', methods=['POST'])
def registrar_validador():
    data = request.get_json()
    novo_validador = Validador(nome=data['nome'], qtdMoeda=data['qtdMoeda'])
    db.session.add(novo_validador)
    db.session.commit()
    return jsonify(novo_validador.to_dict()), 201

@app.route('/selecionar_validadores', methods=['POST'])

def selecionar_validadores_iniciais():
    validadores = Validador.query.filter(Validador.qtdMoeda >= 50, Validador.flag <= 2).all()

    # Eliminar validadores com mais de duas flags da seleção
    validadores = [v for v in validadores if v.flag <= 2]

    # Ajustar a probabilidade de seleção com base nas flags
    candidatos = []
    for validador in validadores:
        probabilidade = 1
        if validador.flag == 1:
            probabilidade *= 0.5  # Redução de 50% para flag 1
        elif validador.flag == 2:
            probabilidade *= 0.25  # Redução de 75% para flag 2

        # Adicionar o validador várias vezes conforme sua probabilidade ajustada
        candidatos.extend([validador] * int(probabilidade * 100))

    # Selecionar aleatoriamente até três validadores
    if len(candidatos) >= 3:
        selecionados = random.sample(candidatos, 3)
    else:
        raise ValueError("Não há validadores suficientes disponíveis")

    return selecionados


@app.route('/processar_transacao/<int:transacao_id>', methods=['POST'])
def processar_transacao(transacao_id):
    try:
        # Inicialmente seleciona três validadores com base nas probabilidades ajustadas por flag
        validadores = selecionar_validadores_iniciais()

        # Processa a validação com os validadores selecionados
        resultados = []
        for validador in validadores:
            resultado = validar_transacao_com_validador(transacao_id, validador)
            resultados.append(resultado)
            if resultado['status'] == 0:
                resultado = tentar_novamente_ou_substituir(transacao_id, validador)
            validador.tentativas += 1  # Atualiza tentativas de validação
            db.session.commit()

        return jsonify([{"validador_id": v.id, "status": v.ultimo_status} for v in validadores])
    except ValueError as e:
        return jsonify({"error": str(e)}), 503

def selecionar_novo_validador(excluido):
    validadores = Validador.query.filter(Validador.id != excluido.id, Validador.qtdMoeda >= 50, Validador.flag <= 2).all()
    if not validadores:
        return None  # Sem validadores disponíveis
    novo_validador = random.choice(validadores)
    excluido.tentativas = 0  # Reset tentativas para o novo validador
    db.session.commit()
    return novo_validador

def tentar_novamente_ou_substituir(transacao_id, validador):
    max_tentativas = 3
    while validador.tentativas < max_tentativas:
        validador.tentativas += 1
        resultado = validar_transacao_com_validador(transacao_id, validador)
        if resultado['status'] != 0:
            return resultado
        db.session.commit()
    
    # Substituir validador se todas as tentativas falharem
    novo_validador = selecionar_novo_validador(validador)
    if novo_validador:
        return validar_transacao_com_validador(transacao_id, novo_validador)
    else:
        return {"status": 0}  # Falha, nenhum substituto encontrado
    
def validar_transacao_com_validador(transacao_id, validador):
    response = requests.post(f'http://{validador.nome}/validar_transacao/{transacao_id}')
    status = response.json().get('status') if response.status_code == 200 else 0
    validador.ultimo_status = status
    db.session.commit()
    return {"status": status}

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
