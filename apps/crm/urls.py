from rest_framework.routers import DefaultRouter

from .views import (ClientContactViewSet, ClientContractViewSet,
                    ClientMeetingNoteViewSet, ClientSLAViewSet,
                    PlacementViewSet, RecruitmentClientViewSet)

router = DefaultRouter()
router.register('clients', RecruitmentClientViewSet, basename='clients')
router.register('client-contacts', ClientContactViewSet, basename='client-contacts')
router.register('client-contracts', ClientContractViewSet, basename='client-contracts')
router.register('client-slas', ClientSLAViewSet, basename='client-slas')
router.register('client-meeting-notes', ClientMeetingNoteViewSet,
                basename='client-meeting-notes')
router.register('placements', PlacementViewSet, basename='placements')

urlpatterns = router.urls
