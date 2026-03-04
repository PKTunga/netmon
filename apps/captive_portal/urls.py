from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.captive_login, name='captive_login'),
    path('signup/', views.captive_signup, name='captive_signup'),
]