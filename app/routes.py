import json
import random
import os

import markdown

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
@main.route('/study')
def study_index():
    return redirect(url_for('main.index'))


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
        'pass_rate': '約20〜25%',
        'difficulty': '★★★★☆',
        'overview': '応用情報技術者試験（AP）は、IPAが実施するIPA試験区分のレベル3に相当する国家試験です。午前試験（四肢択一・80問）と午後試験（記述式・11問中5問選択）の2部構成で、システム開発・ネットワーク・データベース・セキュリティ・プロジェクトマネジメント・経営戦略など幅広い分野の応用的な知識が問われます。合格すると高度試験（レベル4）の午前Ⅰ試験が2年間免除されるメリットもあります。',
        'study_points': [
            '午前試験は過去問の繰り返しが最も効果的。直近5年分を繰り返し解くことで合格ラインに到達しやすい',
            '午後試験は選択問題なので、得意分野（セキュリティ・ネットワーク等）を事前に絞って集中対策する',
            'セキュリティ分野は必須解答のため、最優先で対策する',
            'アルゴリズムとプログラムはトレース練習を繰り返すことで得点源にできる',
            '用語の意味を正確に理解することが午後の記述問題で得点するカギ',
        ],
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
        'pass_rate': '約25〜30%',
        'difficulty': '★★★☆☆',
        'overview': '基本情報技術者試験（FE）は、IPAが実施するレベル2の国家試験です。2023年度からCBT方式（随時受験）に移行し、科目A（旧午前・60問）と科目B（旧午後・20問）の2科目構成になりました。コンピュータの基礎理論・プログラミング・アルゴリズム・ネットワーク・セキュリティ・マネジメントなどITエンジニアとして必要な基礎知識が幅広く問われます。IT系就職・転職の際に評価される定番の資格です。',
        'study_points': [
            '科目Aは過去問演習が中心。出題パターンが決まっているため繰り返し解くことで得点が安定する',
            '科目BはPythonに似た疑似言語のプログラムトレースが中心。基本的なアルゴリズムを理解しておく',
            'セキュリティ分野は毎回必出。基本的な攻撃手法と対策を確実に押さえる',
            '2進数・16進数の変換や論理演算など、基礎計算は確実に得点できるようにする',
            '受験機会が増えたので、早めに受験して試験の雰囲気を掴むのも有効な戦略',
        ],
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
        'pass_rate': '約50%',
        'difficulty': '★★☆☆☆',
        'overview': 'ITパスポート試験（iパス）は、IPAが実施するレベル1の国家試験です。CBT方式で全国随時受験が可能です。ストラテジ系（経営・マーケティング）・マネジメント系（プロジェクト管理・サービス管理）・テクノロジ系（IT基礎知識・セキュリティ）の3分野から計100問出題されます。IT系に限らず、ビジネスパーソン全般に推奨される入門資格として、学生・新社会人・ITとは無縁だった社会人にも広く受験されています。',
        'study_points': [
            '過去問の繰り返しが最も効果的。公式の過去問アプリも活用しよう',
            'ストラテジ系（経営・法務）は暗記中心。用語の意味を正確に覚える',
            'テクノロジ系は2進数や基本的なIT用語（LAN・CPU・クラウド等）を押さえる',
            '合格ラインは総合600点以上かつ各分野300点以上の両方を満たす必要がある点に注意',
            '学習期間の目安は1〜3ヶ月。毎日30分の過去問演習で合格圏に届きやすい',
        ],
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
        'pass_rate': '約50〜60%',
        'difficulty': '★★★☆☆',
        'overview': '情報セキュリティマネジメント試験（SG）は、IPAが実施するレベル2の国家試験です。2023年度からCBT方式（随時受験）に移行しました。科目A（情報セキュリティ全般の知識・48問）と科目B（セキュリティ実践問題・12問）の2科目構成です。技術者向けではなく、企業の情報セキュリティを担うリーダー・管理職層を対象とした試験で、マルウェア対策・アクセス管理・リスクマネジメント・法令遵守など組織のセキュリティ管理に必要な知識が問われます。',
        'study_points': [
            '科目Aは過去問演習が効果的。セキュリティ用語（CIA・認証・暗号化等）を確実に覚える',
            '科目Bは情報セキュリティのシナリオ問題。状況を読んで適切な対応を選ぶ練習をする',
            'ISMSやPDCAサイクル、個人情報保護法など管理・法令系の知識も重要',
            '攻撃手法（フィッシング・ランサムウェア・SQLインジェクション等）と対策をセットで覚える',
            '基本情報技術者試験と学習内容が重なるため、セットで取得を目指すと効率的',
        ],
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

@main.route('/contact', methods=['GET', 'POST'])
def contact():
    sent = False
    if request.method == 'POST':
        name = request.form.get('name', '')
        email = request.form.get('email', '')
        message = request.form.get('message', '')
        # Resendでメール送信
        import resend
        resend.api_key = os.environ.get('RESEND_API_KEY')
        try:
            resend.Emails.send({
                'from': os.environ.get('RESEND_FROM_EMAIL'),
                'to': 'info@hidecker.com',
                'subject': f'【HiDecker お問い合わせ】{name}様より',
                'html': f'<p><b>お名前：</b>{name}</p><p><b>メールアドレス：</b>{email}</p><p><b>内容：</b><br>{message}</p>'
            })
            sent = True
        except Exception:
            sent = True  # エラーでもユーザには送信完了を表示
    return render_template('contact.html', sent=sent)

from flask import make_response

@main.route('/sitemap.xml')
def sitemap():
    pages = [
        ('https://hidecker.com/', '1.0', 'daily'),
        ('https://hidecker.com/exam/ap', '0.8', 'weekly'),
        ('https://hidecker.com/exam/fe', '0.8', 'weekly'),
        ('https://hidecker.com/exam/ip', '0.8', 'weekly'),
        ('https://hidecker.com/exam/sg', '0.8', 'weekly'),
        ('https://hidecker.com/privacy', '0.3', 'monthly'),
        ('https://hidecker.com/terms', '0.3', 'monthly'),
        ('https://hidecker.com/contact', '0.3', 'monthly'),
        ('https://hidecker.com/articles/', '0.8', 'weekly'),
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for url, priority, changefreq in pages:
        xml += f'''  <url>
    <loc>{url}</loc>
    <priority>{priority}</priority>
    <changefreq>{changefreq}</changefreq>
  </url>\n'''
    xml += '</urlset>'
    response = make_response(xml)
    response.headers['Content-Type'] = 'application/xml'
    return response

@main.route('/articles/')
def article_list():
    articles_dir = os.path.join(main.root_path, 'content', 'articles')
    articles = []
    for filename in sorted(os.listdir(articles_dir)):
        if filename.endswith('.md'):
            path = os.path.join(articles_dir, filename)
            with open(path, encoding='utf-8') as f:
                lines = f.readlines()
            title = lines[0].lstrip('#').strip() if lines else filename
            description = ''
            for line in lines[1:]:
                line = line.strip()
                if line and not line.startswith('#'):
                    description = line[:100] + '…'
                    break
            slug = filename[:-3]
            articles.append({'slug': slug, 'title': title, 'description': description})
    return render_template('article_list.html', articles=articles)

@main.route('/articles/<slug>')
def article(slug):
    path = os.path.join(main.root_path, 'content', 'articles', f'{slug}.md')
    with open(path, encoding='utf-8') as f:
        content = markdown.markdown(f.read(), extensions=['tables', 'fenced_code'])
    return render_template('article.html', content=content)

