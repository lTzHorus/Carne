from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from bson.json_util import dumps
from bson.objectid import ObjectId
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuração segura da conexão (use variáveis de ambiente)
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://leoimarques:nT8QO2rCaps1RzwL@cluster0.ji1shyl.mongodb.net/carne_astra?retryWrites=true&w=majority&appName=Cluster0")

try:
    client = MongoClient(MONGO_URI)
    # Testa a conexão
    client.admin.command('ping')
    db = client.get_default_database()  # Pega o banco da URI
    print(f"Conectado ao MongoDB Atlas! Banco: {db.name}")
except Exception as e:
    print(f"Erro ao conectar: {e}")
    db = None

# Rota para listar todos os pagamentos
@app.route('/api/payments', methods=['GET'])
def get_payments():
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        # Ordena por data de vencimento (os mais próximos primeiro)
        payments = list(db.payments.find().sort("dueDate", 1))
        return dumps(payments)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Rota para adicionar um novo pagamento/parcela
@app.route('/api/payments', methods=['POST'])
def add_payment():
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Validação dos campos obrigatórios
        required_fields = ['description', 'value', 'dueDate', 'payer']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        # Converte a string de data para objeto Date
        data['dueDate'] = datetime.strptime(data['dueDate'], "%Y-%m-%d")
        
        # Adiciona status padrão
        data['paid'] = False
        data['paymentDate'] = None
        
        result = db.payments.insert_one(data)
        return jsonify({
            "success": True,
            "id": str(result.inserted_id),
            "message": "Payment added successfully"
        })
    except ValueError as e:
        return jsonify({"error": f"Invalid date format. Use YYYY-MM-DD: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Rota para marcar um pagamento como pago
@app.route('/api/payments/<payment_id>/pay', methods=['PUT'])
def mark_as_paid(payment_id):
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "Invalid payment ID"}), 400
            
        # Atualiza o documento marcando como pago e adiciona a data atual
        result = db.payments.update_one(
            {"_id": ObjectId(payment_id)},
            {
                "$set": {
                    "paid": True,
                    "paymentDate": datetime.now()
                }
            }
        )
        
        if result.modified_count == 0:
            return jsonify({"error": "Payment not found or already paid"}), 404
            
        return jsonify({
            "success": True,
            "message": "Payment marked as paid"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Rota para editar um pagamento
@app.route('/api/payments/<payment_id>', methods=['PUT'])
def update_payment(payment_id):
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "Invalid payment ID"}), 400
            
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Remove campos que não devem ser atualizados
        data.pop('_id', None)
        data.pop('paid', None)
        data.pop('paymentDate', None)
        
        # Se houver dueDate, converte para objeto Date
        if 'dueDate' in data:
            data['dueDate'] = datetime.strptime(data['dueDate'], "%Y-%m-%d")
        
        result = db.payments.update_one(
            {"_id": ObjectId(payment_id)},
            {"$set": data}
        )
        
        if result.modified_count == 0:
            return jsonify({"error": "Payment not found or no changes made"}), 404
            
        return jsonify({
            "success": True,
            "message": "Payment updated successfully"
        })
    except ValueError as e:
        return jsonify({"error": f"Invalid date format. Use YYYY-MM-DD: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Rota para excluir um pagamento
@app.route('/api/payments/<payment_id>', methods=['DELETE'])
def delete_payment(payment_id):
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "Invalid payment ID"}), 400
            
        result = db.payments.delete_one({"_id": ObjectId(payment_id)})
        
        if result.deleted_count == 0:
            return jsonify({"error": "Payment not found"}), 404
            
        return jsonify({
            "success": True,
            "message": "Payment deleted successfully"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000, debug=True)