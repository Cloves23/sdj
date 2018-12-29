from django.urls import path
from .views import teste


app_name = 'seguranca'
urlpatterns = [
    path('', teste, name="teste"),
]
