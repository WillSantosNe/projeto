from time import time
from flask import Flask, request, redirect, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from dataclasses import dataclass
from datetime import date, datetime
import requests

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db' 
db = SQLAlchemy(app)
migrate = Migrate(app, db)

@dataclass
class Cliente(db.Model):
    id: int
    nome: str
    senha: int
    qtdMoeda: int

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), unique=False, nullable=False)
    senha = db.Column(db.String(20), unique=False, nullable=False)
    qtdMoeda = db.Column(db.Integer, unique=False, nullable=False)

@dataclass
class Seletor(db.Model):
    id: int
    nome: str
    ip: str
    
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(20), unique=False, nullable=False)
    ip = db.Column(db.String(15), unique=False, nullable=False)

@dataclass
class Transacao(db.Model):
    id: int
    remetente: int
    recebedor: int
    valor: int
    horario : datetime
    status: int
    
    id = db.Column(db.Integer, primary_key=True)
    remetente = db.Column(db.Integer, unique=False, nullable=False)
    recebedor = db.Column(db.Integer, unique=False, nullable=False)
    valor = db.Column(db.Integer, unique=False, nullable=False)
    horario = db.Column(db.DateTime, unique=False, nullable=False)
    status = db.Column(db.Integer, unique=False, nullable=False)


    def to_dict(self):
        return {
            'id': self.id,
            'remetente': self.remetente,
            'recebedor': self.recebedor,
            'valor': self.valor,
            'horario': self.horario.isoformat(),
            'status': self.status
        }

with app.app_context():
    db.create_all()

@app.route("/")
def index():
    return jsonify(['API sem interface do banco!'])

@app.route('/cliente', methods = ['GET'])
def ListarCliente():
    if(request.method == 'GET'):
        clientes = Cliente.query.all()
        return jsonify(clientes)  

@app.route('/cliente/<string:nome>/<string:senha>/<int:qtdMoeda>', methods = ['POST'])
def InserirCliente(nome, senha, qtdMoeda):
    if request.method=='POST' and nome != '' and senha != '' and qtdMoeda != '':
        objeto = Cliente(nome=nome, senha=senha, qtdMoeda=qtdMoeda)
        db.session.add(objeto)
        db.session.commit()
        return jsonify(objeto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/cliente/<int:id>', methods = ['GET'])
def UmCliente(id):
    if(request.method == 'GET'):
        objeto = Cliente.query.get(id)
        return jsonify(objeto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/cliente/<int:id>/<int:qtdMoedas>', methods=["POST"])
def EditarCliente(id, qtdMoedas):
    if request.method=='POST':
        try:
            cliente = Cliente.query.filter_by(id=id).first()
            cliente.qtdMoedas = qtdMoedas
            db.session.commit()
            return jsonify(['Alteração feita com sucesso'])
        except Exception as e:
            data={
                "message": "Atualização não realizada"
            }
            return jsonify(data)

    else:
        return jsonify(['Method Not Allowed'])

@app.route('/cliente/<int:id>', methods = ['DELETE'])
def ApagarCliente(id):
    if(request.method == 'DELETE'):
        objeto = Cliente.query.get(id)
        db.session.delete(objeto)
        db.session.commit()

        data={
            "message": "Cliente Deletado com Sucesso"
        }

        return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor', methods = ['GET'])
def ListarSeletor():
    if(request.method == 'GET'):
        produtos = Seletor.query.all()
        return jsonify(produtos)  

@app.route('/seletor/<string:nome>/<string:ip>', methods = ['POST'])
def InserirSeletor(nome, ip):
    if request.method=='POST' and nome != '' and ip != '':
        objeto = Seletor(nome=nome, ip=ip)
        db.session.add(objeto)
        db.session.commit()
        return jsonify(objeto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor/<int:id>', methods = ['GET'])
def UmSeletor(id):
    if(request.method == 'GET'):
        produto = Seletor.query.get(id)
        return jsonify(produto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor/<int:id>/<string:nome>/<string:ip>', methods=["POST"])
def EditarSeletor(id, nome, ip):
    if request.method=='POST':
        try:
            varNome = nome
            varIp = ip
            validador = Seletor.query.filter_by(id=id).first()
            db.session.commit()
            validador.nome = varNome
            validador.ip = varIp
            db.session.commit()
            return jsonify(validador)
        except Exception as e:
            data={
                "message": "Atualização não realizada"
            }
            return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/seletor/<int:id>', methods = ['DELETE'])
def ApagarSeletor(id):
    if(request.method == 'DELETE'):
        objeto = Seletor.query.get(id)
        db.session.delete(objeto)
        db.session.commit()

        data={
            "message": "Validador Deletado com Sucesso"
        }

        return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/hora', methods = ['GET'])
def horario():
    if(request.method == 'GET'):
        objeto = datetime.now()
        return jsonify(objeto)
		
@app.route('/transacoes', methods = ['GET'])
def ListarTransacoes():
    if(request.method == 'GET'):
        transacoes = Transacao.query.all()
        return jsonify(transacoes)
    
    
@app.route('/transacoes/<int:rem>/<int:reb>/<int:valor>', methods=['POST'])
def CriaTransacao(rem, reb, valor):
    remetente = db.session.get(Cliente, rem)
    recebedor = db.session.get(Cliente, reb)

    if not remetente or not recebedor:
        return jsonify({'error': 'Remetente ou Recebedor não encontrado.'}), 404

    if remetente.qtdMoeda < valor:
        return jsonify({'error': 'Saldo insuficiente do remetente.'}), 400

    # Atualiza os saldos dos clientes
    remetente.qtdMoeda -= valor
    recebedor.qtdMoeda += valor
    db.session.commit()

    # Cria a transação
    transacao = Transacao(
        remetente=rem,
        recebedor=reb,
        valor=valor,
        horario=datetime.utcnow(),  # Define o horário atual
        status=0  # Define o status inicial
    )
    db.session.add(transacao)
    db.session.commit()

    transacao_dict = transacao.to_dict()

    # Envia a transação para o serviço seletor
    url_seletor = "http://seletor:5001/transacoes"  # Usando o nome do serviço no Docker Compose
    try:
        response = requests.post(url_seletor, json=transacao_dict)
        if response.status_code == 200:
            return jsonify({'message': 'Transação criada e enviada com sucesso!'}), 200
        elif response.status_code == 503:
            return jsonify({'error': 'Serviço seletor indisponível. Tente novamente mais tarde.'}), 503
        else:
            return jsonify({'error': 'Falha ao enviar transação para o seletor.'}), response.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'Erro ao conectar ao serviço seletor: {e}'}), 500




    
@app.route('/transacoes/<int:id>', methods = ['GET'])
def UmaTransacao(id):
    if(request.method == 'GET'):
        objeto = Transacao.query.get(id)
        return jsonify(objeto)
    else:
        return jsonify(['Method Not Allowed'])

@app.route('/transacoes/<int:id>/<int:status>', methods=["POST"])
def EditaTransacao(id, status):
    if request.method=='POST':
        try:
            objeto = Transacao.query.filter_by(id=id).first()
            db.session.commit()
            objeto.id = id
            objeto.status = status
            db.session.commit()
            return jsonify(objeto)
        except Exception as e:
            data={
                "message": "transação não atualizada"
            }
            return jsonify(data)
    else:
        return jsonify(['Method Not Allowed'])

@app.errorhandler(404)
def page_not_found(error):
    return render_template('page_not_found.html'), 404

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)


