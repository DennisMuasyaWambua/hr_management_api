release: python manage.py migrate --noinput && python manage.py create_admin && python manage.py seed_rbac
web: gunicorn hr_api.wsgi:application --bind 0.0.0.0:$PORT
