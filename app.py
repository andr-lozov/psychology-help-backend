import os
import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev')

db = SQLAlchemy(app)
CORS(app)

# ===== МОДЕЛИ =====
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(255), nullable=False)
    contact_type = db.Column(db.String(20), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    occupation = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    messages = db.relationship('Message', backref='user', lazy=True)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    def to_dict(self):
        return {'id': self.id, 'user_id': self.user_id, 'role': self.role, 'content': self.content, 'created_at': self.created_at.isoformat() if self.created_at else None}

# Создание таблиц
with app.app_context():
    db.create_all()

client = OpenAI(api_key=os.getenv('VSELLM_API_KEY'))

# ===== РОУТЫ =====
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'message': 'Igor Ilyin AI is running', 'status': 'ok'})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Нет данных'}), 400
    required = ['name', 'contact', 'contact_type', 'age', 'occupation']
    if not all(k in data and str(data[k]).strip() for k in required):
        return jsonify({'success': False, 'error': 'Заполните все поля'}), 400
    try:
        user = User(
            name=str(data['name']).strip(),
            contact=str(data['contact']).strip(),
            contact_type=str(data['contact_type']).strip(),
            age=int(data['age']),
            occupation=str(data['occupation']).strip()
        )
        db.session.add(user)
        db.session.commit()
        return jsonify({'success': True, 'user_id': user.id}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': 'Ошибка БД'}), 500

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json()
    user_id = data.get('user_id')
    message = data.get('message')
    if not user_id or not message:
        return jsonify({'success': False, 'error': 'user_id и message обязательны'}), 400
    try:
        user_msg = Message(user_id=user_id, role='user', content=str(message).strip())
        db.session.add(user_msg)
        db.session.commit()
        
        history = Message.query.filter_by(user_id=user_id).order_by(Message.created_at.desc()).limit(10).all()
        history.reverse()
        context = [{'role': m.role, 'content': m.content} for m in history]
        
        response = client.chat.completions.create(
            model='gpt-3.5-turbo',
            messages=[{'role': 'system', 'content': 'Ты - эмпатичный психолог. Отвечай на русском, поддерживай, не ставь диагнозы.'}, *context],
            temperature=0.7,
            max_tokens=500
        )
        ai_reply = response.choices[0].message.content.strip()
    except Exception as e:
        ai_reply = 'Извините, техническая ошибка. Попробуйте позже.'
    
    try:
        ai_msg = Message(user_id=user_id, role='assistant', content=ai_reply)
        db.session.add(ai_msg)
        db.session.commit()
    except:
        db.session.rollback()
    
    return jsonify({'success': True, 'response': ai_reply})

@app.route('/api/history', methods=['GET'])
def history():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'user_id обязателен'}), 400
    messages = Message.query.filter_by(user_id=user_id).order_by(Message.created_at.desc()).limit(20).all()
    messages.reverse()
    return jsonify({'success': True, 'messages': [m.to_dict() for m in messages]})

# ⚠️ НЕТ app.run() — gunicorn запустит сам
