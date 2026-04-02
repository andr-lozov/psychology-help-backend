import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from flask import Flask, request, jsonify
from flask_cors import CORS
from database import db, init_db
from models import User, Message
from dotenv import load_dotenv
from openai import OpenAI
import os, re, hashlib, time
from datetime import datetime

load_dotenv()
app = Flask(__name__)
CORS(app)
#init_db(app)

# Безопасное создание таблиц (не роняет Passenger, если БД занята)
try:
    with app.app_context():
        db.create_all()
except Exception as e:
    print(f"[DB Warning] Tables creation skipped: {e}")

SYSTEM_PROMPT = """Ты — Игорь Ильин, психолог с чувством юмора.
Стиль: тёплый, мужской взгляд, лёгкая ирония без сарказма.
Структура ответа:
1. Выслушать и валидировать чувства
2. Поделиться метафорой или историей
3. Дать 2-3 конкретных простых шага
4. Вселить надежду
5. Предложить продолжение диалога
ВАЖНО: Не ставь диагнозы. При кризисных словах — дай контакты доверия.
ДИСКЛЕЙМЕР в конце: «Это не замена профессиональной терапии. В кризисной ситуации: 8-800-2000-122»"""

CRISIS_KEYWORDS = ['суицид','смерть','убить','умереть','не хочу жить','ненавижу себя','повеситься','порезать']

def check_crisis(text):
    t = text.lower()
    return any(k in t for k in CRISIS_KEYWORDS)

def anonymize(text):
    text = re.sub(r'[\w\.-]+@[\w\.-]+\.\w+', '[email]', text)
    text = re.sub(r'\+?[\d\s\-\(\)]{10,}', '[phone]', text)
    return text

def detect_complexity(question):
    q = question.lower()
    if check_crisis(q): return 'crisis'
    complex_topics = ['психическое расстройство','клиническая депрессия','биполярное','ОКР','ПТСР','шизофрения']
    if any(t in q for t in complex_topics): return 'complex'
    return 'simple'

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status':'ok','message':'Igor Ilyin AI is running'})

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        user = User(
            name=data['name'], contact=data['contact'], contact_type=data['contact_type'],
            age=data['age'], occupation=data['occupation']
        )
        db.session.add(user); db.session.commit()
        return jsonify({'success':True,'user_id':user.id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success':False,'error':str(e)}), 400

@app.route('/api/ask', methods=['POST'])
def ask():
    try:
        data = request.get_json()
        user_id, question = data.get('user_id'), data.get('question')
        if not user_id or not question:
            return jsonify({'success':False,'error':'user_id и question обязательны'}), 400
        
        user = User.query.get(user_id)
        if not user or not user.is_active:
            return jsonify({'success':False,'error':'Пользователь не найден'}), 404
        
        history = Message.query.filter_by(user_id=user_id).order_by(Message.created_at.desc()).limit(20).all()
        history.reverse()
        history_text = "\n".join([f"{'Пользователь' if m.role=='user' else 'Игорь Ильин'}: {m.content}" for m in history])
        
        complexity = detect_complexity(question)
        if complexity == 'crisis':
            answer = "Я слышу, что тебе очень тяжело. Пожалуйста, обратись за профессиональной помощью прямо сейчас. Телефон доверия: 8-800-2000-122 (бесплатно, анонимно, круглосуточно). Ты не один."
        else:
            user_ctx = f"Пол: {user.gender if hasattr(user,'gender') else 'не указан'}, Возраст: {user.age}, Занятие: {user.occupation}"
            full_prompt = f"{SYSTEM_PROMPT}\n\nДАННЫЕ ПОЛЬЗОВАТЕЛЯ:\n{user_ctx}\n\nИСТОРИЯ ДИАЛОГА:\n{history_text}\n\nВОПРОС: {anonymize(question)}"
            
            response = client.chat.completions.create(
                model="qwen/qwen3.5-plus",
                messages=[{"role":"user","content":full_prompt}],
                temperature=0.7, max_tokens=1000, timeout=30
            )
            answer = response.choices[0].message.content.strip()
            if check_crisis(answer):
                answer += "\n\n⚠️ Если ситуация критическая: 8-800-2000-122"
        
        db.session.add_all([
            Message(user_id=user_id, role='user', content=question, is_crisis=(complexity=='crisis')),
            Message(user_id=user_id, role='assistant', content=answer)
        ])
        db.session.commit()
        return jsonify({'success':True,'answer':answer,'complexity':complexity})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Ask error: {e}")
        return jsonify({'success':False,'error':'Ошибка обработки запроса'}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    user_id = request.args.get('user_id')
    if not user_id: return jsonify({'success':False,'error':'user_id обязателен'}), 400
    messages = Message.query.filter_by(user_id=user_id).order_by(Message.created_at.desc()).limit(20).all()
    messages.reverse()
    return jsonify({'success':True,'messages':[m.to_dict() for m in messages]})

if __name__ == '__main__':
    app.run(debug=False)
APPEOF