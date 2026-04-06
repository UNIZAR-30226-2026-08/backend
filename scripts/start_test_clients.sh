#!/bin/sh

. venv/bin/activate

sh scripts/reset_db.sh

redis-server --port 26379 &
python manage.py init_boards
python manage.py get_test_sessions
python manage.py runserver

pkill redis-server
