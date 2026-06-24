from django.urls import path

from .views import ProvidersView, RankView, ResultsView, ScoreBulkView, ScoreView

urlpatterns = [
    path('matching/score/', ScoreView.as_view(), name='matching-score'),
    path('matching/score-bulk/', ScoreBulkView.as_view(), name='matching-score-bulk'),
    path('matching/rank/<uuid:job_posting_id>/', RankView.as_view(), name='matching-rank'),
    path('matching/results/', ResultsView.as_view(), name='matching-results'),
    path('matching/providers/', ProvidersView.as_view(), name='matching-providers'),
]
