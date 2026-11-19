from django.urls import path
from . import views

urlpatterns = [
    path('', views.PostListView.as_view(), name='post_list'),
    path('signup/', views.SignUpView.as_view(), name='signup'),
    path('login/', views.CustomLoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('post/create/', views.PostCreateView.as_view(), name='post_create'),
    path('post/<str:slug>/', views.PostDetailView.as_view(), name='post_detail'),
    path('post/<str:slug>/edit/', views.PostUpdateView.as_view(), name='post_update'),
    path('post/<str:slug>/delete/', views.PostDeleteView.as_view(), name='post_delete'),
    path('category/<str:slug>/', views.CategoryDetailView.as_view(), name='category_detail'),
    path('tag/<str:slug>/', views.TagDetailView.as_view(), name='tag_detail'),
]
