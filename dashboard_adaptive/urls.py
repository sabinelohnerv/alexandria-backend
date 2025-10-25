from django.urls import path
from . import views

app_name = 'dashboard_adaptive'

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    
    # Training Dashboard (NEW)
    path('entrenamiento/', views.training_dashboard, name='training_dashboard'),
    path('entrenamiento/nueva-version/', views.train_new_version, name='train_new_version'),
    path('entrenamiento/evaluar/', views.evaluate_versions, name='evaluate_versions'),
    
    # Training & Dataset
    path('train/', views.train_weights, name='train'),
    path('dataset/', views.dataset_info, name='dataset'),
    
    # Weights management
    path('weights/', views.weights_list, name='weights_list'),
    path('weights/promote/', views.promote_weight, name='promote_weight'),
    path('weights/rollback/', views.rollback_weight, name='rollback_weight'),
    path('weights/<str:version>/detail/', views.weight_detail, name='weight_detail'),
    
    # Query explorer
    path('query/', views.query_explorer, name='query_explorer'),
    path('query/<int:message_id>/explain/', views.query_explain, name='query_explain'),
    
    # A/B metrics
    path('ab-metrics/', views.ab_metrics, name='ab_metrics'),
]
