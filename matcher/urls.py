from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='dashboard'),
    path('download/fd/', views.download_fd, name='download_fd'),
    path('download/gl/', views.download_gl, name='download_gl'),
    path('download/third/', views.download_third, name='download_third'),
    path('download/reconciled-statement/', views.download_reconciled_statement, name='download_reconciled_statement'),
    path('download/matched-fd/', views.download_matched_fd, name='download_matched_fd'),
    path('download/matched-gl/', views.download_matched_gl, name='download_matched_gl'),
    path('download/matched-fd-gl/', views.download_matched_fd_gl, name='download_matched_fd_gl'),
    path('download/matched-gl-third/', views.download_matched_gl_third, name='download_matched_gl_third'),
    path('download/all-results/', views.download_all_results, name='download_all_results'),
]
