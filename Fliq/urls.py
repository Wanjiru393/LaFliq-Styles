from django.urls import path
from . import views

urlpatterns = [
    path('', views.product_list, name='home'), 
    path('register/', views.register, name='register'), 
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('category/slug:category_slug/', views.product_list, name='product_list_by_category'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
]
