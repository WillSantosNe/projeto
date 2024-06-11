import time
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
    status = db.Column(db.Integer, default=0)
    tentativas = db.Column(db.Integer, default=0)
    disponivel = db.Column(db.Boolean, default=True)  # Supondo que há um campo indicando disponibilidade
    selecoes_recentes = db.Column(db.Integer, default=0)  # Novo campo
    transacoes_coerentes = db.Column(db.Integer, default=0)  # Contador de transações coerentes
    selecoes_consecutivas = db.Column(db.Integer, default=0)  # Novo campo para rastrear seleções consecutivas
    hold = db.Column(db.Integer, default=0)  # Novo campo para monitorar o estado de HOLD
    retornos = db.Column(db.Integer, default=0)  # Novo campo para rastrear retornos
    saldo_travado = db.Column(db.Integer, default=0)  # Novo campo para saldo travado
    taxa_travada = db.Column(db.Integer, default=0)  # Novo campo para rastrear taxas travadas


    def __repr__(self):
        return f'<Validador {self.nome}>'
    


@app.route('/cadastrar_validador', methods=['GET']) #verificar se é post
def cadastrar_validador():
    data = request.get_json()
    nome = data['nome']
    qtdMoeda = data['qtdMoeda']

    if qtdMoeda < 50:
        return jsonify({"status": "Erro", "mensagem": "Saldo mínimo de 50 NoNameCoins necessário para cadastro"}), 400

    novo_validador = Validador(
        nome=nome,
        qtdMoeda=qtdMoeda,
        saldo_travado=qtdMoeda
    )
    db.session.add(novo_validador)
    db.session.commit()

    return jsonify({"status": "Sucesso", "mensagem": "Validador cadastrado com sucesso"}), 201



@app.route('/selecionar_validadores', methods=['POST'])
def selecionar():
    timeout = 60  # Tempo máximo de espera em segundos
    start_time = time.time()
    qtd_transacionada = request.json.get('qtd_transacionada', 0)

    def calcular_peso(validador):
        peso_base = validador.qtdMoeda
        if validador.flag == 1:
            peso_base *= 0.5  # Reduz 50% se flag = 1
        elif validador.flag == 2:
            peso_base *= 0.25  # Reduz 75% se flag = 2
        
        # Ajuste de peso baseado no número de seleções recentes para limitar a 20%
        peso_ajustado = peso_base * (1 - min(validador.selecoes_recentes / 5, 0.8)) # Supondo que cada seleção reduz a chance em 20%
        return peso_ajustado

    while True:
        validadores_disponiveis = Validador.query.filter_by(disponivel=True).all()
        
        if len(validadores_disponiveis) >= 3:
            pesos = [calcular_peso(v) for v in validadores_disponiveis]
            validadores_selecionados = random.choices(validadores_disponiveis, weights=pesos, k=3)
            break
        elif time.time() - start_time >= timeout:
            return jsonify({"status": "Erro", "mensagem": "Tempo de espera excedido"}), 408
        
        time.sleep(5)  # Pausa de 5 segundos



    # Distribuição das taxas de validação
    taxa_total = qtd_transacionada * 0.015  # 1,5% do total transacionado
    taxa_travada = qtd_transacionada * 0.005  # 0,5% travado para o validador
    taxa_distribuida = (taxa_total - taxa_travada) / len(validadores_disponiveis)  # Distribui igualmente entre todos os validadores

    for v in validadores_selecionados:
        v.selecoes_recentes += 1
        v.transacoes_coerentes += 1
        v.selecoes_consecutivas += 1

        # Se o validador foi escolhido cinco vezes consecutivas, coloca em HOLD
        if v.selecoes_consecutivas >= 5:
            v.hold = 5
            v.selecoes_consecutivas = 0

        # Reduz a flag após 10.000 transações coerentes
        if v.transacoes_coerentes >= 10000:
            if v.flag > 0:
                v.flag = max(v.flag - 1, 0)
            v.transacoes_coerentes = 0


        # Expulsão e lógica de retorno
        if v.flag > 2:
            if v.retornos < 2:
                v.retornos += 1
                v.qtdMoeda *= 2  # Exige o dobro do saldo para retornar
                v.flag = 0
                v.disponivel = False  # Temporariamente indisponível até novo saldo ser confirmado
            else:
                v.disponivel = False  # Elimina definitivamente da rede

    # Atualiza o estado de HOLD de todos os validadores
    todos_validadores = Validador.query.all()
    for validador in todos_validadores:
        if validador.hold > 0:
            validador.hold -= 1
        validador.qtdMoeda += taxa_distribuida  # Distribui a taxa igualmente

    db.session.commit()

    votos_aprovados = sum([1 for v in validadores_selecionados if v.status == 1])
    votos_totais = len(validadores_selecionados)

    if votos_aprovados > votos_totais / 2:
        resultado_consenso = "Aprovada"
    else:
        resultado_consenso = "Não Aprovada"

    return jsonify({
        "status": "Sucesso",
        "mensagem": "Validadores selecionados",
        "consenso": resultado_consenso,
        "votos_aprovados": votos_aprovados,
        "votos_totais": votos_totais
    }), 200



if __name__ == '__main__':
    db.create_all()  # Cria o banco de dados e tabelas
    app.run(debug=True)
