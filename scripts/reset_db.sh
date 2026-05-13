#!/bin/sh

export DEBUG="True"

. venv/bin/activate

rm -rf db.sqlite3
for f in magnate; do
  rm -rf $f/migrations
done

for f in magnate; do
  python manage.py makemigrations $f
done

python manage.py migrate
python manage.py loaddata items.json bonus_categories.json  # load items after migrations
#python manage.py runserver
