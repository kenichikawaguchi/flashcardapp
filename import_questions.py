import json
import sys
from app import create_app, db
from app.models import Question

def import_questions(filename):
    app = create_app()
    with app.app_context():
        with open(filename, encoding='utf-8') as f:
            questions = json.load(f)

        success = 0
        errors = []
        for i, q in enumerate(questions):
            # 検証
            if q['answer_text'] not in q['choices']:
                errors.append(f'問題{i+1}: answer_textがchoicesに含まれていません')
                continue
            if len(q['choices']) != 4:
                errors.append(f'問題{i+1}: choicesが4つではありません')
                continue

            question = Question(
                exam=q.get('exam'),
                category=q['category'],
                question_text=q['question_text'],
                answer_text=q['answer_text'],
                explanation=q.get('explanation', ''),
                choices=json.dumps(q['choices'], ensure_ascii=False)
            )
            db.session.add(question)
            success += 1

        db.session.commit()

        print(f'✅ {success}問登録完了！')
        if errors:
            print(f'⚠️  スキップした問題:')
            for e in errors:
                print(f'  {e}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('使い方: python import_questions.py <JSONファイル名>')
        sys.exit(1)
    import_questions(sys.argv[1])
