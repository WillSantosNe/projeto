from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Configuração do banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///../site.db'  # Caminho relativo ao banco de dados
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Validador(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    ip = db.Column(db.String(15), nullable=False)
    qtdMoeda = db.Column(db.Integer, nullable=False)
    flag = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f'<Validador {self.nome}>'



@app.route('/validadores', methods=['GET'])
def listar_validadores():
    validadores = Validador.query.all()
    return jsonify([validador.to_dict() for validador in validadores]), 200

@app.route('/validador', methods=['POST'])
def registrar_validador():
    data = request.get_json()
    novo_validador = Validador(nome=data['nome'], ip=data['ip'], qtdMoeda=data['qtdMoeda'])
    db.session.add(novo_validador)
    db.session.commit()
    return jsonify(novo_validador.to_dict()), 201

@app.route('/selecionar_validadores', methods=['POST'])
def selecionar_validadores():
    # Lógica para selecionar validadores com base no saldo de NoNameCoins
    pass




if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
