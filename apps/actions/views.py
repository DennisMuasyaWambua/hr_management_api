import logging
from uuid import UUID

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ServiceAuditLog
from apps.core.permissions import HasModulePermission, request_company_id, request_user_id

from .models import ActionRecord
from .serializers import ActionItemSerializer, ActionSummarySerializer
from .services import ActionCenterService

logger = logging.getLogger(__name__)
_MODULE = 'actions'


def _service(request) -> ActionCenterService:
    company_id = request_company_id(request)
    return ActionCenterService(company_id=UUID(str(company_id)))


class ActionListView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        service = _service(request)
        items = service.get_actions(
            category=request.query_params.get('category'),
            priority=request.query_params.get('priority'),
            status_filter=request.query_params.get('status', 'active'),
            overdue_only=request.query_params.get('overdue', '').lower() == 'true',
        )
        ServiceAuditLog.log(
            'actions.viewed', request=request,
            metadata={'count': len(items), 'filters': dict(request.query_params)},
            company_id=request_company_id(request),
        )
        page, per_page = _pagination(request)
        chunk = items[(page - 1) * per_page: page * per_page]
        return Response({
            'count': len(items),
            'next': _next_url(request, page, per_page, len(items)),
            'previous': _prev_url(request, page),
            'results': ActionItemSerializer(chunk, many=True).data,
        })


class ActionSummaryView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        return Response(ActionSummarySerializer(_service(request).get_summary()).data)


class ActionHighPriorityView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        items = _service(request).get_high_priority()
        return Response({'count': len(items), 'results': ActionItemSerializer(items, many=True).data})


class ActionOverdueView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        service = _service(request)
        items = service.get_overdue(category=request.query_params.get('category'))
        page, per_page = _pagination(request)
        chunk = items[(page - 1) * per_page: page * per_page]
        return Response({
            'count': len(items),
            'next': _next_url(request, page, per_page, len(items)),
            'previous': _prev_url(request, page),
            'results': ActionItemSerializer(chunk, many=True).data,
        })


class ActionUpcomingView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        try:
            days = max(1, min(90, int(request.query_params.get('days', 7))))
        except (TypeError, ValueError):
            days = 7
        service = _service(request)
        items = service.get_upcoming(days=days, category=request.query_params.get('category'))
        page, per_page = _pagination(request)
        chunk = items[(page - 1) * per_page: page * per_page]
        return Response({
            'count': len(items),
            'next': _next_url(request, page, per_page, len(items)),
            'previous': _prev_url(request, page),
            'results': ActionItemSerializer(chunk, many=True).data,
        })


class ActionDismissView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def post(self, request, action_id):
        company_id = request_company_id(request)
        user_id = request_user_id(request)
        service = ActionCenterService(company_id=UUID(str(company_id)))
        record = service.dismiss(
            action_id=action_id,
            user_id=user_id,
            reason=request.data.get('reason', ''),
        )
        if str(record.company_id) != str(company_id):
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        ServiceAuditLog.log(
            'actions.dismissed', request=request,
            object_type='ActionRecord', object_id=action_id,
            company_id=company_id,
            metadata={'reason': request.data.get('reason', '')},
        )
        return Response({'id': action_id, 'dismissed_at': record.dismissed_at.isoformat()})


class ActionEscalateView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def post(self, request, action_id):
        company_id = request_company_id(request)
        user_id = request_user_id(request)
        service = ActionCenterService(company_id=UUID(str(company_id)))
        record = service.escalate(
            action_id=action_id,
            user_id=user_id,
            note=request.data.get('note', ''),
        )
        if str(record.company_id) != str(company_id):
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        ServiceAuditLog.log(
            'actions.escalated', request=request,
            object_type='ActionRecord', object_id=action_id,
            company_id=company_id,
            metadata={'note': request.data.get('note', '')},
        )
        return Response({'id': action_id, 'escalated_at': record.escalated_at.isoformat()})


# ── Pagination helpers ───────────────────────────────────────────────────────

def _pagination(request):
    try:
        page = max(1, int(request.query_params.get('page', 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(100, max(1, int(request.query_params.get('per_page', 25))))
    except (TypeError, ValueError):
        per_page = 25
    return page, per_page


def _next_url(request, page, per_page, total):
    if page * per_page >= total:
        return None
    params = request.query_params.copy()
    params['page'] = page + 1
    return request.build_absolute_uri(f'?{params.urlencode()}')


def _prev_url(request, page):
    if page <= 1:
        return None
    params = request.query_params.copy()
    params['page'] = page - 1
    return request.build_absolute_uri(f'?{params.urlencode()}')
