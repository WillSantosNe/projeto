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
    novo_validador = Validador(nome=data['nome'], qtdMoeda=data['qtdMoeda'])
    db.session.add(novo_validador)
    db.session.commit()
    return jsonify(novo_validador.to_dict()), 201

@app.route('/selecionar_validadores', methods=['POST'])
def selecionar_validadores():
    try:
        # Obter todos os validadores que podem ser selecionados (saldo mínimo e número de flags aceitável)
        validadores = Validador.query.filter(Validador.qtdMoeda >= 50, Validador.flag <= 2).all()

        # Eliminar validadores com mais de duas flags da seleção e possível rede
        for validador in validadores:
            if validador.flag > 2:
                db.session.delete(validador)

        # Ajustar a probabilidade de seleção com base nas flags
        candidatos = []
        for validador in validadores:
            probabilidade = 1
            if validador.flag == 1:
                probabilidade *= 0.5  # Redução de 50% para flag 1
            elif validador.flag == 2:
                probabilidade *= 0.25  # Redução de 75% para flag 2

            candidatos.extend([validador] * int(probabilidade * 100))  # Aumentar a chance de seleção baseada em probabilidade

        # Selecionar aleatoriamente até três validadores
        import random
        if len(candidatos) >= 3:
            selecionados = random.sample(candidatos, 3)
        else:
            return jsonify({"error": "Não há validadores suficientes disponíveis"}), 503  # Serviço indisponível

        # Responder com os validadores escolhidos
        return jsonify([{"id": v.id, "nome": v.nome, "qtdMoeda": v.qtdMoeda} for v in selecionados]), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500



if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)
