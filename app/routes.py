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
    exams = [
        {
            'id': 'ap',
            'name': '応用情報技術者',
            'level': 'レベル3',
            'desc': 'ITエンジニアとして応用的な知識・技能を証明する試験',
            'color': 'blue',
            'count': Question.query.filter_by(exam='応用情報技術者').count()
        },
        {
            'id': 'fe',
            'name': '基本情報技術者',
            'level': 'レベル2',
            'desc': 'ITエンジニアとしての基礎的な知識・技能を証明する試験',
            'color': 'green',
            'count': Question.query.filter_by(exam='基本情報技術者').count()
        },
        {
            'id': 'ip',
            'name': 'ITパスポート',
            'level': 'レベル1',
            'desc': 'ITを利活用する社会人に必要な基礎知識を証明する試験',
            'color': 'yellow',
            'count': Question.query.filter_by(exam='ITパスポート').count()
        },
        {
            'id': 'sg',
            'name': '情報セキュリティマネジメント',
            'level': 'レベル2',
            'desc': '情報セキュリティマネジメントの知識・技能を証明する試験',
            'color': 'red',
            'count': Question.query.filter_by(exam='情報セキュリティマネジメント').count()
        },
    ]

    total = 0
    correct = 0
    accuracy = 0
    streak = 0
    if current_user.is_authenticated:
        total = UserProgress.query.filter_by(user_id=current_user.id).count()
        correct = UserProgress.query.filter_by(user_id=current_user.id, is_correct=True).count()
        accuracy = round(correct / total * 100) if total > 0 else 0
        streak = current_user.streak

    return render_template('index.html', exams=exams, total=total, accuracy=accuracy, streak=streak)

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
    exam_id_map = {v['exam_key']: k for k, v in EXAM_INFO.items()}
    total = UserProgress.query.filter_by(user_id=current_user.id).count()
    correct = UserProgress.query.filter_by(user_id=current_user.id, is_correct=True).count()
    accuracy = round(correct / total * 100) if total > 0 else 0

    # 試験別統計
    exam_stats_raw = db.session.query(
        Question.exam,
        func.count(UserProgress.id),
        func.sum(func.cast(UserProgress.is_correct, db.Integer))
    ).join(UserProgress, Question.id == UserProgress.question_id)\
     .filter(UserProgress.user_id == current_user.id)\
     .group_by(Question.exam)\
     .order_by(Question.exam)\
     .all()

    exam_stats_map = {
        exam: {
            'total': total_count,
            'correct': correct_count or 0,
            'accuracy': round((correct_count or 0) / total_count * 100) if total_count > 0 else 0
        }
        for exam, total_count, correct_count in exam_stats_raw
    }

    # 試験別・分野別統計
    exam_category_raw = db.session.query(
        Question.exam,
        Question.category,
        func.count(Question.id),
        func.count(UserProgress.id),
        func.sum(func.cast(UserProgress.is_correct, db.Integer))
    ).outerjoin(UserProgress, (Question.id == UserProgress.question_id) & (UserProgress.user_id == current_user.id))\
     .group_by(Question.exam, Question.category)\
     .order_by(Question.exam, Question.category)\
     .all()

    exam_category_map = {}
    for exam, category, q_count, a_count, correct_count in exam_category_raw:
        if exam not in exam_category_map:
            exam_category_map[exam] = []
        exam_category_map[exam].append({
            'category': category,
            'q_count': q_count,
            'total': a_count or 0,
            'correct': correct_count or 0,
            'accuracy': round((correct_count or 0) / a_count * 100) if a_count else None
        })

    return render_template('dashboard.html',
        total=total,
        correct=correct,
        accuracy=accuracy,
        streak=current_user.streak,
        exam_stats_map=exam_stats_map,
        exam_category_map=exam_category_map,
        exam_id_map=exam_id_map
    )

@main.route('/study/exam/<exam_id>')
def study_by_exam(exam_id):
    if exam_id not in EXAM_INFO:
        return redirect(url_for('main.index'))
    exam_key = EXAM_INFO[exam_id]['exam_key']
    question = Question.query.filter_by(exam=exam_key).order_by(func.random()).first()
    choices = json.loads(question.choices) if question and question.choices else []
    random.shuffle(choices)
    return render_template('study.html', question=question, choices=choices, answered=False, exam_id=exam_id)

@main.route('/study/exam/<exam_id>/category/<category>')
def study_by_exam_category(exam_id, category):
    if exam_id not in EXAM_INFO:
        return redirect(url_for('main.index'))
    exam_key = EXAM_INFO[exam_id]['exam_key']
    question = Question.query.filter_by(exam=exam_key, category=category).order_by(func.random()).first()
    choices = json.loads(question.choices) if question and question.choices else []
    random.shuffle(choices)
    return render_template('study.html', question=question, choices=choices, answered=False, exam_id=exam_id, category=category)

@main.route('/answer', methods=['POST'])
def answer():
    question_id = request.form['question_id']
    selected = request.form['selected']
    choices = request.form.getlist('choices_order')
    category = request.form.get('category', '')
    exam_id = request.form.get('exam_id', '')
    question = Question.query.get(int(question_id))
    is_correct = selected == question.answer_text

    if current_user.is_authenticated:
        progress = UserProgress(user_id=current_user.id, question_id=question_id, is_correct=is_correct)
        db.session.add(progress)
        today = date.today()
        if current_user.last_study_date != today:
            if current_user.last_study_date == today - timedelta(days=1):
                current_user.streak += 1
            else:
                current_user.streak = 1
            current_user.last_study_date = today
        db.session.commit()

    return render_template('study.html', question=question, choices=choices, answered=True, selected=selected, category=category, exam_id=exam_id)

@main.route('/privacy')
def privacy():
    return render_template('privacy.html')

@main.route('/terms')
def terms():
    return render_template('terms.html')

EXAM_INFO = {
    'ap': {
        'name': '応用情報技術者',
        'level': 'レベル3',
        'exam_key': '応用情報技術者',
        'color': 'blue',
        'desc': 'ITエンジニアとして応用的な知識・技能を証明する国家試験です。システム開発・運用・管理など幅広い分野の知識が問われます。',
        'target': 'ITエンジニアとして3年以上の経験を持つ方、またはそれに相当する知識を持つ方',
        'schedule': '年2回（春：4月・秋：10月）',
        'fee': '7,500円',
    },
    'fe': {
        'name': '基本情報技術者',
        'level': 'レベル2',
        'exam_key': '基本情報技術者',
        'color': 'green',
        'desc': 'ITエンジニアとしての基礎的な知識・技能を証明する国家試験です。プログラミングやアルゴリズムの基礎が問われます。',
        'target': 'ITエンジニアを目指す学生・社会人、IT系職種への転職を考えている方',
        'schedule': '通年（随時）',
        'fee': '7,500円',
    },
    'ip': {
        'name': 'ITパスポート',
        'level': 'レベル1',
        'exam_key': 'ITパスポート',
        'color': 'yellow',
        'desc': 'ITを利活用するすべての社会人に必要な基礎知識を証明する国家試験です。ITの基礎知識から経営・マネジメントまで幅広く問われます。',
        'target': 'IT系・非IT系を問わず、すべての社会人・学生',
        'schedule': '通年（随時）',
        'fee': '7,500円',
    },
    'sg': {
        'name': '情報セキュリティマネジメント',
        'level': 'レベル2',
        'exam_key': '情報セキュリティマネジメント',
        'color': 'red',
        'desc': '情報セキュリティマネジメントの知識・技能を証明する国家試験です。セキュリティリスクの管理や対策の知識が問われます。',
        'target': '情報セキュリティに関わる業務担当者、セキュリティ管理職を目指す方',
        'schedule': '通年（随時）',
        'fee': '7,500円',
    },
}

@main.route('/exam/<exam_id>')
def exam_detail(exam_id):
    if exam_id not in EXAM_INFO:
        return redirect(url_for('main.index'))
    info = EXAM_INFO[exam_id]
    categories = db.session.query(
        Question.category,
        func.count(Question.id)
    ).filter_by(exam=info['exam_key'])\
     .group_by(Question.category)\
     .order_by(Question.category).all()
    total = Question.query.filter_by(exam=info['exam_key']).count()
    return render_template('exam_detail.html', info=info, exam_id=exam_id, categories=categories, total=total)
