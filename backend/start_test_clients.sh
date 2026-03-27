#!/bin/sh

. ../venv/bin/activate

sh reset_db.sh

redis-server --port 26379 &
python manage.py get_test_sessions
python manage.py runserver

pkill redis-server
