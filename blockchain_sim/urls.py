from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("start/", views.start_simulation, name="start_simulation"),
    path("stop/", views.stop_simulation, name="stop_simulation"),
    path("status/", views.get_status, name="get_status"),
    path("node/<str:node_id>/", views.node_detail, name="node_detail"),
    path(
        "api/node/<str:node_id>/",
        views.get_node_details_api,
        name="get_node_details_api",
    ),
    path("metrics/", views.get_metrics, name="get_metrics"),
]
