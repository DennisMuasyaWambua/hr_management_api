import logging
from uuid import UUID

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import ServiceAuditLog
from apps.core.permissions import HasModulePermission, request_company_id, request_user_id

from .models import WorkflowDefinition, WorkflowExecution, WorkflowTask
from .serializers import (
    WorkflowDefinitionSerializer,
    WorkflowExecutionSerializer,
    WorkflowTaskSerializer,
)
from .templates import WORKFLOW_TEMPLATES

logger = logging.getLogger(__name__)
_MODULE = 'workflows'


def _company(request) -> UUID:
    return UUID(str(request_company_id(request)))


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


def _paginate(request, qs):
    page, per_page = _pagination(request)
    total = qs.count()
    items = list(qs[(page - 1) * per_page: page * per_page])
    return items, total, page, per_page


class WorkflowDefinitionListView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        company_id = _company(request)
        qs = WorkflowDefinition.objects.filter(company_id=company_id).order_by('-created_at')
        trigger = request.query_params.get('trigger_type')
        if trigger:
            qs = qs.filter(trigger_type=trigger)
        active = request.query_params.get('is_active')
        if active is not None:
            qs = qs.filter(is_active=active.lower() == 'true')
        items, total, page, per_page = _paginate(request, qs)
        return Response({
            'count': total,
            'results': WorkflowDefinitionSerializer(items, many=True).data,
        })

    def post(self, request):
        company_id = _company(request)
        data = {**request.data, 'company_id': str(company_id)}
        serializer = WorkflowDefinitionSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        workflow = serializer.save()
        ServiceAuditLog.log(
            'workflow.created', request=request,
            object_type='WorkflowDefinition', object_id=str(workflow.id),
            company_id=str(company_id),
            metadata={'name': workflow.name, 'trigger_type': workflow.trigger_type},
        )
        return Response(WorkflowDefinitionSerializer(workflow).data, status=status.HTTP_201_CREATED)


class WorkflowDefinitionDetailView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def _get(self, request, pk):
        company_id = _company(request)
        try:
            return WorkflowDefinition.objects.get(id=pk, company_id=company_id)
        except WorkflowDefinition.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get(request, pk)
        if obj is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(WorkflowDefinitionSerializer(obj).data)

    def put(self, request, pk):
        obj = self._get(request, pk)
        if obj is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = WorkflowDefinitionSerializer(obj, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        ServiceAuditLog.log('workflow.updated', request=request,
                            object_type='WorkflowDefinition', object_id=str(pk),
                            company_id=str(_company(request)))
        return Response(serializer.data)

    def patch(self, request, pk):
        obj = self._get(request, pk)
        if obj is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = WorkflowDefinitionSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self._get(request, pk)
        if obj is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        ServiceAuditLog.log('workflow.deleted', request=request,
                            object_type='WorkflowDefinition', object_id=str(pk),
                            company_id=str(_company(request)))
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkflowActivateView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def post(self, request, pk):
        company_id = _company(request)
        try:
            obj = WorkflowDefinition.objects.get(id=pk, company_id=company_id)
        except WorkflowDefinition.DoesNotExist:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        obj.is_active = True
        obj.save(update_fields=['is_active', 'updated_at'])
        return Response({'id': str(obj.id), 'is_active': True})


class WorkflowDeactivateView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def post(self, request, pk):
        company_id = _company(request)
        try:
            obj = WorkflowDefinition.objects.get(id=pk, company_id=company_id)
        except WorkflowDefinition.DoesNotExist:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        obj.is_active = False
        obj.save(update_fields=['is_active', 'updated_at'])
        return Response({'id': str(obj.id), 'is_active': False})


class WorkflowExecutionListView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        company_id = _company(request)
        qs = WorkflowExecution.objects.filter(company_id=company_id).order_by('-created_at')
        workflow_id = request.query_params.get('workflow')
        if workflow_id:
            qs = qs.filter(workflow_id=workflow_id)
        exec_status = request.query_params.get('status')
        if exec_status:
            qs = qs.filter(status=exec_status)
        items, total, page, per_page = _paginate(request, qs)
        return Response({
            'count': total,
            'results': WorkflowExecutionSerializer(items, many=True).data,
        })


class WorkflowExecutionDetailView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request, pk):
        company_id = _company(request)
        try:
            obj = WorkflowExecution.objects.prefetch_related('logs').get(
                id=pk, company_id=company_id
            )
        except WorkflowExecution.DoesNotExist:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(WorkflowExecutionSerializer(obj).data)


class WorkflowTemplateListView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        return Response({'count': len(WORKFLOW_TEMPLATES), 'results': WORKFLOW_TEMPLATES})


class WorkflowTaskListView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def get(self, request):
        company_id = _company(request)
        qs = WorkflowTask.objects.filter(company_id=company_id).order_by('-created_at')
        task_status = request.query_params.get('status')
        if task_status:
            qs = qs.filter(status=task_status)
        assigned_to = request.query_params.get('assigned_to')
        if assigned_to:
            qs = qs.filter(assigned_to=assigned_to)
        items, total, page, per_page = _paginate(request, qs)
        return Response({
            'count': total,
            'results': WorkflowTaskSerializer(items, many=True).data,
        })

    def post(self, request):
        company_id = _company(request)
        data = {**request.data, 'company_id': str(company_id)}
        serializer = WorkflowTaskSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        task = serializer.save()
        return Response(WorkflowTaskSerializer(task).data, status=status.HTTP_201_CREATED)


class WorkflowTaskDetailView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def _get(self, request, pk):
        company_id = _company(request)
        try:
            return WorkflowTask.objects.get(id=pk, company_id=company_id)
        except WorkflowTask.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self._get(request, pk)
        if obj is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(WorkflowTaskSerializer(obj).data)

    def put(self, request, pk):
        obj = self._get(request, pk)
        if obj is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = WorkflowTaskSerializer(obj, data=request.data, partial=False)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, pk):
        obj = self._get(request, pk)
        if obj is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = WorkflowTaskSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk):
        obj = self._get(request, pk)
        if obj is None:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkflowTaskCompleteView(APIView):
    permission_classes = [HasModulePermission]
    rbac_module = _MODULE

    def post(self, request, pk):
        company_id = _company(request)
        try:
            task = WorkflowTask.objects.get(id=pk, company_id=company_id)
        except WorkflowTask.DoesNotExist:
            return Response({'error': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'completed_at', 'updated_at'])
        ServiceAuditLog.log(
            'workflow_task.completed', request=request,
            object_type='WorkflowTask', object_id=str(pk),
            company_id=str(company_id),
        )
        return Response(WorkflowTaskSerializer(task).data)
