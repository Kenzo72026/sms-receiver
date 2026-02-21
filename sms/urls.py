from django.urls import path
from . import views

urlpatterns = [
    # Webhook - URL à mettre dans l'app Transitaire SMS
    path('webhook/sms/', views.webhook_recevoir_sms, name='webhook_sms'),

    # Dashboard
    path('', views.dashboard, name='dashboard'),
    path('message/<int:pk>/', views.detail_message, name='detail_message'),
    path('message/<int:pk>/supprimer/', views.supprimer_message, name='supprimer_message'),

    # API pour le rafraîchissement automatique
    path('api/messages/', views.api_messages, name='api_messages'),
]
