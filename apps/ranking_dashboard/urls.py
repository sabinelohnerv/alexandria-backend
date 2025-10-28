from django.urls import path
from . import views

app_name = 'ranking_dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),
    path('train/', views.train_weights, name='train'),
    path('versions/', views.list_versions, name='versions'),
    path('versions/<str:version>/activate/', views.activate_version, name='activate'),
    path('versions/<str:version>/evaluate/', views.evaluate_version, name='evaluate'),
    path('cycle/', views.run_full_cycle, name='cycle'),
    path('export/', views.export_data, name='export'),
    path('rollback/', views.rollback_version, name='rollback'),
    path('explainability/', views.explainability_list, name='explainability_list'),
    path('explainability/<int:message_id>/', views.explainability_detail, name='explainability_detail'),
]
