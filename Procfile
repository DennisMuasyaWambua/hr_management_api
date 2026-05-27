release: python manage.py migrate --noinput
web: gunicorn hr_api.wsgi:application --bind 0.0.0.0:$PORT
