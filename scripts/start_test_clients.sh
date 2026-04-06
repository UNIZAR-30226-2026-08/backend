#!/bin/sh

. venv/bin/activate

sh scripts/reset_db.sh

redis-server --port 26379 &
sleep 1

celery -A magnate purge -f
celery -A magnate worker -l INFO &
python manage.py init_boards
python manage.py get_test_sessions
python manage.py runserver

pkill -f "celery -A magnate"
pkill redis-server
