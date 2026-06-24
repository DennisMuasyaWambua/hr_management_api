from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import HasModulePermission, request_company_id
from apps.hr.views import CompanyScopedViewSet

from .models import (Competency, CompetencyRating, DevelopmentPlan,
                     DevelopmentPlanItem, FeedbackRequest, FeedbackResponse,
                     GoalUpdate, PerformanceGoal)
from .serializers import (CompetencyRatingSerializer, CompetencySerializer,
                           DevelopmentPlanItemSerializer,
                           DevelopmentPlanListSerializer,
                           DevelopmentPlanSerializer,
                           FeedbackRequestSerializer,
                           FeedbackResponseAnonSerializer,
                           FeedbackResponseSerializer, GoalUpdateSerializer,
                           PerformanceGoalListSerializer,
                           PerformanceGoalSerializer)


def _company(request):
    return request_company_id(request)


class PerformanceGoalViewSet(CompanyScopedViewSet):
    rbac_module = 'performance'
    queryset = PerformanceGoal.objects.filter(is_deleted=False)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PerformanceGoalSerializer
        return PerformanceGoalListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('employee_id'):
            qs = qs.filter(employee_id=params['employee_id'])
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('year'):
            qs = qs.filter(period_year=params['year'])
        return qs

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['get', 'post'], url_path='updates')
    def updates(self, request, pk=None):
        goal = self.get_object()
        if request.method == 'GET':
            return Response(
                GoalUpdateSerializer(goal.updates.all(), many=True).data)

        serializer = GoalUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = _company(request)
        update = serializer.save(
            goal=goal, company_id=company_id, tenant_id=goal.tenant_id)

        # Sync current_value back to goal if provided
        if update.current_value is not None:
            goal.current_value = update.current_value
            goal.save(update_fields=['current_value', 'updated_at'])

        return Response(GoalUpdateSerializer(update).data,
                        status=status.HTTP_201_CREATED)


class CompetencyViewSet(CompanyScopedViewSet):
    rbac_module = 'performance'
    queryset = Competency.objects.filter(is_deleted=False)
    serializer_class = CompetencySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('active_only'):
            qs = qs.filter(is_active=True)
        return qs

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])


class CompetencyRatingViewSet(CompanyScopedViewSet):
    rbac_module = 'performance'
    queryset = CompetencyRating.objects.all()
    serializer_class = CompetencyRatingSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('employee_id'):
            qs = qs.filter(employee_id=params['employee_id'])
        if params.get('cycle'):
            qs = qs.filter(review_cycle=params['cycle'])
        if params.get('competency_id'):
            qs = qs.filter(competency_id=params['competency_id'])
        return qs


class DevelopmentPlanViewSet(CompanyScopedViewSet):
    rbac_module = 'performance'
    queryset = DevelopmentPlan.objects.filter(is_deleted=False)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return DevelopmentPlanSerializer
        return DevelopmentPlanListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('employee_id'):
            qs = qs.filter(employee_id=self.request.query_params['employee_id'])
        return qs

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['get', 'post'], url_path='items')
    def items(self, request, pk=None):
        plan = self.get_object()
        if request.method == 'GET':
            return Response(
                DevelopmentPlanItemSerializer(plan.items.all(), many=True).data)

        serializer = DevelopmentPlanItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = _company(request)
        item = serializer.save(
            plan=plan, company_id=company_id, tenant_id=plan.tenant_id)
        return Response(DevelopmentPlanItemSerializer(item).data,
                        status=status.HTTP_201_CREATED)


class DevelopmentPlanItemViewSet(CompanyScopedViewSet):
    rbac_module = 'performance'
    queryset = DevelopmentPlanItem.objects.all()
    serializer_class = DevelopmentPlanItemSerializer


class FeedbackRequestViewSet(CompanyScopedViewSet):
    rbac_module = 'performance'
    queryset = FeedbackRequest.objects.filter(is_deleted=False)
    serializer_class = FeedbackRequestSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('subject_id'):
            qs = qs.filter(subject_id=self.request.query_params['subject_id'])
        return qs

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save(update_fields=['is_deleted', 'updated_at'])

    @action(detail=True, methods=['post'], url_path='respond')
    def respond(self, request, pk=None):
        feedback_req = self.get_object()
        if feedback_req.status != 'open':
            return Response({'detail': 'Feedback request is not open'},
                            status=status.HTTP_409_CONFLICT)

        serializer = FeedbackResponseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_id = _company(request)
        try:
            response = serializer.save(
                request=feedback_req,
                submitted_at=timezone.now(),
                company_id=company_id,
                tenant_id=feedback_req.tenant_id,
            )
        except IntegrityError:
            return Response({'detail': 'You have already submitted a response'},
                            status=status.HTTP_409_CONFLICT)
        return Response(FeedbackResponseSerializer(response).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='responses')
    def responses(self, request, pk=None):
        feedback_req = self.get_object()
        qs = feedback_req.responses.all()
        if feedback_req.is_anonymous:
            return Response(
                FeedbackResponseAnonSerializer(qs, many=True).data)
        return Response(FeedbackResponseSerializer(qs, many=True).data)

    @action(detail=True, methods=['post'], url_path='close')
    def close(self, request, pk=None):
        feedback_req = self.get_object()
        feedback_req.status = 'closed'
        feedback_req.save(update_fields=['status', 'updated_at'])
        return Response(FeedbackRequestSerializer(feedback_req).data)
