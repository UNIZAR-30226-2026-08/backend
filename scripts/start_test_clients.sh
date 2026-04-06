#!/bin/sh

. venv/bin/activate

<<<<<<< Updated upstream
sh reset_db.sh
=======
sh scripts/reset_db.sh
>>>>>>> Stashed changes

redis-server --port 26379 &
python manage.py init_boards
python manage.py get_test_sessions
python manage.py runserver

pkill redis-server
