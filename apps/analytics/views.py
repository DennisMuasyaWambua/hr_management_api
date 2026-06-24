from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import HasModulePermission, request_company_id

from .services import AnalyticsService


def _company(request):
    return request_company_id(request)


class OverviewView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'analytics'

    def get(self, request):
        return Response(AnalyticsService.overview(_company(request)))


class HeadcountView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'analytics'

    def get(self, request):
        return Response(AnalyticsService.headcount(_company(request)))


class RecruitmentView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'analytics'

    def get(self, request):
        job_posting_id = request.query_params.get('job_posting_id')
        return Response(
            AnalyticsService.recruitment(_company(request),
                                         job_posting_id=job_posting_id))


class PayrollAnalyticsView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'analytics'

    def get(self, request):
        months = request.query_params.get('months', 12)
        return Response(
            AnalyticsService.payroll(_company(request), months=months))


class LeaveAnalyticsView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'analytics'

    def get(self, request):
        year = request.query_params.get('year')
        return Response(
            AnalyticsService.leave(_company(request), year=year))


class PlacementAnalyticsView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = 'analytics'

    def get(self, request):
        months = request.query_params.get('months', 12)
        return Response(
            AnalyticsService.placements(_company(request), months=months))
