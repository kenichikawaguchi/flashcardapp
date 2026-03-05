import json
import random

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models import User, Question, UserProgress
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer
import resend
from datetime import date, timedelta


main = Blueprint('main', __name__)

def get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])

def send_verification_email(email, token):
    resend.api_key = current_app.config['RESEND_API_KEY']
    verify_url = url_for('main.verify_email', token=token, _external=True)
    try:
        resend.Emails.send({
            'from': current_app.config['RESEND_FROM_EMAIL'],
            'to': email,
            'subject': '【応用情報フラッシュカード】メールアドレスの確認',
            'html': f'''
            <p>ご登録ありがとうございます！</p>
            <p>以下のリンクをクリックしてメールアドレスを確認してください。</p>
            <a href="{verify_url}">メールアドレスを確認する</a>
            <p>このリンクは24時間有効です。</p>
            '''
        })
        print('メール送信成功！')
    except Exception as e:
        print(f'メール送信エラー: {e}')

@main.route('/')
def index():
    return render_template('index.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        if User.query.filter_by(email=email).first():
            flash('このメールアドレスはすでに登録されています。')
            return redirect(url_for('main.register'))

        user = User(username=username, email=email, password=password)
        db.session.add(user)
        db.session.commit()

        token = get_serializer().dumps(email, salt='email-verify')
        send_verification_email(email, token)

        flash('確認メールを送信しました。メールをご確認ください。')
        return redirect(url_for('main.login'))
    return render_template('register.html')

@main.route('/verify/<token>')
def verify_email(token):
    try:
        s = get_serializer()
        email = s.loads(token, salt='email-verify', max_age=86400)
    except Exception:
        flash('認証リンクが無効または期限切れです。')
        return redirect(url_for('main.login'))

    user = User.query.filter_by(email=email).first()
    if user:
        user.is_verified = True
        db.session.commit()
        flash('メールアドレスの確認が完了しました！ログインしてください。')
    return redirect(url_for('main.login'))

@main.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password, request.form['password']):
            if not user.is_verified:
                flash('メールアドレスの確認が完了していません。確認メールをご確認ください。')
                return redirect(url_for('main.login'))
            login_user(user)
            return redirect(url_for('main.dashboard'))
        flash('メールアドレスまたはパスワードが間違っています。')
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@main.route('/dashboard')
@login_required
def dashboard():
    total = UserProgress.query.filter_by(user_id=current_user.id).count()
    correct = UserProgress.query.filter_by(user_id=current_user.id, is_correct=True).count()
    accuracy = round(correct / total * 100) if total > 0 else 0
    # 分野別問題数
    category_counts = db.session.query(
        Question.category,
        func.count(Question.id)
    ).group_by(Question.category).order_by(Question.category).all()

    return render_template('dashboard.html',
        total=total,
        correct=correct,
        accuracy=accuracy,
        streak=current_user.streak,
        category_counts=category_counts
    )

@main.route('/study')

@login_required
def study():
    question = Question.query.order_by(func.random()).first()
    choices = json.loads(question.choices) if question and question.choices else []
    random.shuffle(choices)
    return render_template('study.html', question=question, choices=choices, answered=False)

@main.route('/answer', methods=['POST'])
@login_required
def answer():
    question_id = request.form['question_id']
    selected = request.form['selected']
    choices = request.form.getlist('choices_order')
    print('choices_order:', choices)
    question = Question.query.get(int(question_id))
    is_correct = selected == question.answer_text

    progress = UserProgress(user_id=current_user.id, question_id=question_id, is_correct=is_correct)
    db.session.add(progress)

    # ストリーク更新
    today = date.today()
    if current_user.last_study_date != today:
        if current_user.last_study_date == today - timedelta(days=1):
            current_user.streak += 1
        else:
            current_user.streak = 1
        current_user.last_study_date = today

    db.session.commit()

    return render_template('study.html', question=question, choices=choices, answered=True, selected=selected)

