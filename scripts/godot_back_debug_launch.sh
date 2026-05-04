echo "Activating venv:"
source venv/bin/activate

export REDIS_PORT=26379
echo "Starting redis server..."
redis-server --port $REDIS_PORT &
sleep 1

if [[ "$1" == "--reset" ]]; then
  echo "Resetting DB"
  ./scripts/reset_db.sh
  DEBUG=True SECRET_KEY=test ALLOWED_HOSTS='127.0.0.1' python manage.py init_boards
  DEBUG=True SECRET_KEY=test ALLOWED_HOSTS='127.0.0.1' python manage.py init_mock_database
fi

clear
echo "Running server"
DEBUG=True SECRET_KEY=test ALLOWED_HOSTS='127.0.0.1' celery -A magnate purge -f
DEBUG=True SECRET_KEY=test ALLOWED_HOSTS='127.0.0.1' celery -A magnate worker -l INFO &
DEBUG=True SECRET_KEY=test ALLOWED_HOSTS='127.0.0.1' python manage.py runserver

# Limpieza al detener con Ctrl+C
pkill -f "celery -A magnate"
pkill celery
pkill redis-server
