from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, Question, UserProgress
from sqlalchemy import func
from functools import wraps

admin = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('管理者権限が必要です。')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function

@admin.route('/')
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    verified_users = User.query.filter_by(is_verified=True).count()
    total_questions = Question.query.count()
    total_answers = UserProgress.query.count()
    category_counts = db.session.query(
        Question.category,
        func.count(Question.id)
    ).group_by(Question.category).order_by(Question.category).all()
    return render_template('admin_dashboard.html',
        total_users=total_users,
        verified_users=verified_users,
        total_questions=total_questions,
        total_answers=total_answers,
        category_counts=category_counts
    )

@admin.route('/questions')
@login_required
@admin_required
def questions():
    questions = Question.query.order_by(Question.category, Question.id).all()
    return render_template('admin_questions.html', questions=questions)

@admin.route('/questions/new', methods=['GET', 'POST'])
@login_required
@admin_required
def question_new():
    if request.method == 'POST':
        import json
        choices = [
            request.form['choice1'],
            request.form['choice2'],
            request.form['choice3'],
            request.form['choice4'],
        ]
        question = Question(
            category=request.form['category'],
            question_text=request.form['question_text'],
            answer_text=request.form['answer_text'],
            explanation=request.form['explanation'],
            choices=json.dumps(choices, ensure_ascii=False)
        )
        db.session.add(question)
        db.session.commit()
        flash('問題を追加しました！')
        return redirect(url_for('admin.questions'))
    categories = db.session.query(Question.category).distinct().order_by(Question.category).all()
    categories = [c[0] for c in categories]
    return render_template('admin_question_form.html', question=None, categories=categories)

@admin.route('/questions/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def question_edit(id):
    import json
    question = Question.query.get_or_404(id)
    if request.method == 'POST':
        choices = [
            request.form['choice1'],
            request.form['choice2'],
            request.form['choice3'],
            request.form['choice4'],
        ]
        question.category = request.form['category']
        question.question_text = request.form['question_text']
        question.answer_text = request.form['answer_text']
        question.explanation = request.form['explanation']
        question.choices = json.dumps(choices, ensure_ascii=False)
        db.session.commit()
        flash('問題を更新しました！')
        return redirect(url_for('admin.questions'))
    categories = db.session.query(Question.category).distinct().order_by(Question.category).all()
    categories = [c[0] for c in categories]
    choices = json.loads(question.choices) if question.choices else ['', '', '', '']
    return render_template('admin_question_form.html', question=question, categories=categories, choices=choices)

@admin.route('/questions/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def question_delete(id):
    question = Question.query.get_or_404(id)
    UserProgress.query.filter_by(question_id=id).delete()
    db.session.delete(question)
    db.session.commit()
    flash('問題を削除しました。')
    return redirect(url_for('admin.questions'))

@admin.route('/users')
@login_required
@admin_required
def users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@admin.route('/users/<int:id>/toggle_verified', methods=['POST'])
@login_required
@admin_required
def toggle_verified(id):
    user = User.query.get_or_404(id)
    user.is_verified = not user.is_verified
    db.session.commit()
    flash(f'{user.username} の認証状態を変更しました。')
    return redirect(url_for('admin.users'))

@admin.route('/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def user_delete(id):
    if id == current_user.id:
        flash('自分自身は削除できません。')
        return redirect(url_for('admin.users'))
    user = User.query.get_or_404(id)
    UserProgress.query.filter_by(user_id=id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'{user.username} を削除しました。')
    return redirect(url_for('admin.users'))

