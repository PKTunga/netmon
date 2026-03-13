from django.urls import path
from . import views

urlpatterns = [
    path('', views.package_list, name='packages'),
    path('login/', views.captive_login, name='captive_login'),
    path('signup/', views.captive_signup, name='captive_signup'),
    path('reset-password/', views.captive_reset_password, name='captive_reset_password'),
    path('pay/<int:package_id>/', views.initiate_payment, name='initiate_payment'),
    path('mpesa-callback/', views.mpesa_callback, name='mpesa_callback'),
]