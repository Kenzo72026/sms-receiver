#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate

# Créer le compte admin si inexistant
python manage.py shell -c "
from django.contrib.auth import get_user_model
import os
U = get_user_model()
username = os.environ.get('ADMIN_USER', 'admin')
password = os.environ.get('ADMIN_PASSWORD', 'admin123')
email = os.environ.get('ADMIN_EMAIL', 'admin@local.com')
if not U.objects.filter(username=username).exists():
    U.objects.create_superuser(username, email, password)
    print(f'Compte {username} créé')
else:
    print(f'Compte {username} existe déjà')
"
