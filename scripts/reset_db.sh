#!/bin/sh

. venv/bin/activate

rm -rf db.sqlite3
<<<<<<< Updated upstream
for f in magnate
do
    rm -rf $f/migrations
=======
for f in magnate; do
  rm -rf $f/migrations
>>>>>>> Stashed changes
done

for f in magnate
do
    python manage.py makemigrations $f
done

python manage.py migrate
#python manage.py runserver


