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
    # escolhas_consecutivas = db.Column(db.Integer, default=0)
    em_hold = db.Column(db.Boolean, default=False)
    expulsoes = db.Column(db.Integer, default=0)
    transacoes_hold_restantes = db.Column(db.Integer, default=0)  # Novo campo para transações restantes em hold

    def __repr__(self):
        return f'<Validador {self.nome}>'

    



def verificar_hold(validador):
    if validador.escolhas_consecutivas >= 5:
        validador.em_hold = True
        validador.transacoes_hold_restantes = 5  # Inicia o contador de transações em hold
        validador.escolhas_consecutivas = 0  # Reseta as escolhas consecutivas
    elif validador.em_hold:
        if validador.transacoes_hold_restantes > 0:
            validador.transacoes_hold_restantes -= 1  # Decrementa o contador de hold
        if validador.transacoes_hold_restantes == 0:
            validador.em_hold = False  # Remove o validador do estado de hold
    db.session.commit()



def readmitir_validador(validador_id, saldo_inicial):
    validador = Validador.query.get(validador_id)
    if validador and validador.expulsoes < 2:
        validador.qtdMoeda = max(100, saldo_inicial * 2)  # Dobro do saldo anteriormente travado
        validador.expulsoes += 1
        validador.flag = 0  # Reseta flags
        db.session.commit()



def distribuir_compensacao(transacao_id, valor_transacao):
    validadores = Validador.query.all()
    valor_total = valor_transacao * 0.015  # 1.5% do valor transacionado
    valor_por_validador = valor_total / len(validadores)
    for validador in validadores:
        validador.qtdMoeda += valor_por_validador  # Adiciona a compensação
        validador.transacoes_coerentes += 1  # Incrementa o contador de transações coerentes
    db.session.commit()




@app.route('/validadores', methods=['GET'])  
def listar_validadores():
    # Consulta todos os registros de validadores no banco de dados.
    validadores = Validador.query.all()
    
    # Converte cada objeto de validador em um dicionário e os serializa em formato JSON,
    # retornando a lista de validadores e o status HTTP 200 indicando sucesso.
    return jsonify([validador.to_dict() for validador in validadores]), 200




@app.route('/validador', methods=['POST'])
def registrar_validador():
    # Obtém os dados em formato JSON enviados no corpo da requisição.
    data = request.get_json()

    # Cria uma nova instância do modelo Validador, utilizando os dados recebidos.
    novo_validador = Validador(nome=data['nome'], qtdMoeda=data['qtdMoeda'])
    
    # Adiciona o novo objeto validador à sessão do banco de dados.
    db.session.add(novo_validador)
    
    # Efetua o commit da sessão para salvar as alterações no banco de dados.
    db.session.commit()

    # Retorna uma resposta JSON com os dados do validador criado e o status HTTP 201 indicando que o recurso foi criado.
    return jsonify(novo_validador.to_dict()), 201



def gerenciar_flags_validadores():
    # Seleciona todos os validadores para verificar suas flags e transações coerentes.
    todos_validadores = Validador.query.all()

    for validador in todos_validadores:
        # Verifica se o validador precisa ter sua flag reduzida.
        if validador.transacoes_coerentes >= 10000:
            validador.flag -= 1  # Reduz uma flag.
            validador.transacoes_coerentes = 0  # Reinicia a contagem de transações coerentes após o decremento da flag.

        # Remove validadores com mais de duas flags.
        if validador.flag > 2:
            validador.qtdMoeda = 0  # Zera o saldo de moedas do validador.
            db.session.delete(validador)  # Remove o validador do banco de dados.
        else:
            db.session.commit()  # Salva as alterações para validadores que não foram removidos.





import time

@app.route('/selecionar_validadores', methods=['POST'])
def selecionar_validadores_iniciais():

    # Gerencia as flags e eliminação de validadores antes de iniciar a seleção.
    gerenciar_flags_validadores()

    # Armazena o tempo inicial para controle do tempo de espera.
    start_time = time.time()  

    # Loop de tentativa de seleção de validadores.
    while True:
        # Consulta validadores que têm quantidade de moeda maior ou igual a 50 e flag menor ou igual a 2.
        validadores = Validador.query.filter(Validador.qtdMoeda >= 50, Validador.flag <= 2, Validador.em_hold == False).all()
        
        if not validadores:
            if time.time() - start_time > 60:
                raise ValueError("Tempo de espera excedido, não há validadores suficientes disponíveis")
            time.sleep(5)  # Espera 5 segundos antes de tentar novamente.
            continue

        # Calcular o total de moedas disponíveis entre os validadores elegíveis.
        total_moedas = sum(validador.qtdMoeda for validador in validadores)

        # Ajusta a probabilidade de seleção com base no número de moedas e flags de cada validador.
        candidatos = []
        for validador in validadores:
            # Base da probabilidade é a proporção de moedas que o validador detém em relação ao total.
            base_probabilidade = validador.qtdMoeda / total_moedas

            # Ajuste de probabilidade conforme a flag.
            if validador.flag == 1:
                base_probabilidade *= 0.5
            elif validador.flag == 2:
                base_probabilidade *= 0.25

            # Aplicar limites de probabilidade de escolha: 0% mínimo e 20% máximo.
            base_probabilidade = max(min(base_probabilidade, 0.20), 0)

            # Converter a probabilidade em um número inteiro ajustado para escala, por exemplo, 10000 para precisão.
            probabilidade_ajustada = int(base_probabilidade * 10000)
            candidatos.extend([validador] * probabilidade_ajustada)

        # Verifica se há pelo menos três validadores disponíveis.
        if len(candidatos) >= 3:
            selecionados = random.sample(candidatos, 3)  # Seleciona aleatoriamente até três validadores.
            return selecionados  # Retorna os validadores selecionados.

        # Verifica se o tempo de espera excedeu um minuto.
        if time.time() - start_time > 60:
            raise ValueError("Tempo de espera excedido, não há validadores suficientes disponíveis")  # Levanta uma exceção após 60 segundos de espera.

        time.sleep(5)  # Espera 5 segundos antes de tentar novamente.





@app.route('/processar_transacao/<int:transacao_id>', methods=['POST'])
def processar_transacao(transacao_id):
    try:
        # Inicialmente seleciona três validadores com base nas probabilidades ajustadas por flag.
        validadores = selecionar_validadores_iniciais()

        # Processa a validação da transação usando os validadores selecionados.
        resultados = []
        for validador in validadores:
            # Valida a transação com cada validador e armazena os resultados.
            resultado = validar_transacao_com_validador(transacao_id, validador)
            resultados.append(resultado)

            # Verifica o status do resultado; se for 0, tenta novamente ou substitui o validador.
            if resultado['status'] == 0:
                resultado = tentar_novamente_ou_substituir(transacao_id, validador)
                # Atualiza o resultado no array após a tentativa ou substituição.
                resultados[-1] = resultado

            # Incrementa o número de tentativas de validação para o validador.
            validador.tentativas += 1
            # Salva as alterações na base de dados.
            db.session.commit()

        # Verifica o consenso entre os resultados de validação.
        status_final = verificar_consenso(resultados)

        # Retorna o status final da transação com base no consenso dos validadores.
        return jsonify({"status_final": status_final}), 200
    except ValueError as e:
        # Retorna um erro 503 (Service Unavailable) se ocorrer um problema, como a falta de validadores suficientes.
        return jsonify({"error": str(e)}), 503
    


def verificar_consenso(resultados):
    # Conta o total de validações realizadas.
    total_validacoes = len(resultados)  

    # Conta quantas validações resultaram em 'aprovado'.
    aprovadas = sum(resultado['status'] == 1 for resultado in resultados)

    # Calcula o número de 'não aprovadas'.
    # nao_aprovadas = total_validacoes - aprovadas  

    # Determina o consenso com base na comparação entre aprovadas e não aprovadas.
    if aprovadas > total_validacoes / 2:
        return 'Aprovada'
    else:
        return 'Não Aprovada'




def selecionar_novo_validador(excluido):
    # Busca validadores com critérios de quantidade de moeda e flag, excluindo o validador atual.
    validadores = Validador.query.filter(Validador.id != excluido.id, Validador.qtdMoeda >= 50, Validador.flag <= 2).all()

    # Verifica se há validadores disponíveis após o filtro.
    if not validadores:
        # Retorna None se não houver validadores disponíveis.
        return None  

    # Seleciona aleatoriamente um novo validador da lista filtrada.
    novo_validador = random.choice(validadores)

    # Reseta as tentativas do validador excluído (assumindo que deveria ser para o novo).
    excluido.tentativas = 0
    db.session.commit()  # Salva as alterações no banco de dados.

    return novo_validador  # Retorna o novo validador selecionado.



def tentar_novamente_ou_substituir(transacao_id, validador):
    max_tentativas = 3  # Número máximo de tentativas permitidas.

    # Repete a validação até alcançar o máximo de tentativas.
    while validador.tentativas < max_tentativas:
        validador.tentativas += 1  # Incrementa o contador de tentativas.
        resultado = validar_transacao_com_validador(transacao_id, validador)  # Tenta validar a transação.

        # Se a validação for bem-sucedida (status != 0), retorna o resultado.
        if resultado['status'] != 0:
            return resultado
        db.session.commit()  # Salva a atualização de tentativas no banco de dados.

    # Se todas as tentativas falharem, tenta substituir o validador.
    novo_validador = selecionar_novo_validador(validador)
    if novo_validador:
        return validar_transacao_com_validador(transacao_id, novo_validador)  # Valida usando o novo validador.
    else:
        return {"status": 0}  # Retorna status de falha se nenhum substituto for encontrado.


  
def validar_transacao_com_validador(transacao_id, validador):
    # Realiza uma requisição POST para o serviço do validador para validar a transação.
    response = requests.post(f'http://{validador.nome}/validar_transacao/{transacao_id}')

    # Extrai o status da resposta JSON ou atribui 0 se a resposta não for 200.
    status = response.json().get('status') if response.status_code == 200 else 0

    # Atualiza o último status do validador no banco de dados.
    validador.ultimo_status = status
    db.session.commit()  # Salva a atualização no banco de dados.

    return {"status": status}  # Retorna o status da validação.


if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
