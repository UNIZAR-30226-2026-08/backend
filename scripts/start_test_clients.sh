#!/bin/sh

export DEBUG="True"
export REDIS_PORT=26379

. venv/bin/activate

sh scripts/reset_db.sh

redis-server --port $REDIS_PORT &
sleep 1

celery -A magnate purge -f
celery -A magnate worker -l INFO &
python manage.py init_boards
python manage.py get_test_sessions
python manage.py runserver

pkill -f "celery -A magnate"
pkill celery
pkill redis-server
