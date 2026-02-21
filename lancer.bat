@echo off
echo === SMS Receiver - Demarrage ===
cd /d "%~dp0"

echo Installation des dependances...
pip install -r requirements.txt

echo Creation de la base de donnees...
python manage.py migrate

echo Verification du compte admin...
python manage.py shell -c "from django.contrib.auth import get_user_model; U = get_user_model(); U.objects.filter(username='admin').exists() or U.objects.create_superuser('admin', 'admin@local.com', 'admin123')"

echo.
echo =========================================
echo   Serveur demarre sur : http://0.0.0.0:8000
echo   Dashboard : http://localhost:8000/
echo   Login : admin / admin123
echo   Webhook URL pour l app : http://TON_IP:8000/webhook/sms/
echo =========================================
echo.
python manage.py runserver 0.0.0.0:8000
pause
