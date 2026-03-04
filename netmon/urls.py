from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('openwisp_users.accounts.urls')),
    path('radius/', include('openwisp_radius.urls')),
    path('', include('apps.captive_portal.urls')),

]