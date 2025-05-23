from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient
from bson.json_util import dumps
from bson.objectid import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv

# Carrega variáveis do arquivo .env
load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')

# Configuração do CORS para produção
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "http://localhost:*",
            "https://*.onrender.com"
        ]
    }
})

# Configuração segura da conexão MongoDB
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("No MONGO_URI set for MongoDB connection")

try:
    client = MongoClient(MONGO_URI)
    # Testa a conexão
    client.admin.command('ping')
    db = client.get_default_database()
    print(f"Conectado ao MongoDB Atlas! Banco: {db.name}")
except Exception as e:
    print(f"Erro ao conectar: {e}")
    db = None

# Rotas da API
@app.route('/api/payments', methods=['GET'])
def get_payments():
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500
    
    try:
        payments = list(db.payments.find().sort("dueDate", 1))
        return dumps(payments)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/payments', methods=['POST'])
def add_payment():
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        required_fields = ['description', 'value', 'dueDate', 'payer']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400
        
        data['dueDate'] = datetime.strptime(data['dueDate'], "%Y-%m-%d")
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

@app.route('/api/payments/<payment_id>/pay', methods=['PUT'])
def mark_as_paid(payment_id):
    if db is None:
        return jsonify({"error": "Database connection failed"}), 500
        
    try:
        if not ObjectId.is_valid(payment_id):
            return jsonify({"error": "Invalid payment ID"}), 400
            
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
            
        data.pop('_id', None)
        data.pop('paid', None)
        data.pop('paymentDate', None)
        
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

# Rotas para servir o frontend
@app.route('/')
def serve_frontend():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('.', path)

# Configuração do servidor para produção
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
