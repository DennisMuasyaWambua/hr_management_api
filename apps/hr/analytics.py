"""
HR Analytics endpoints — read-only aggregations over existing tables.

No new models. No migrations. All queries run against what already exists.
Responses are intentionally flat so the frontend can feed them directly
into chart libraries (recharts, chart.js, etc.).
"""
import datetime

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import request_company_id


class WorkforceAnalyticsView(APIView):
    """
    GET /api/analytics/workforce/

    Returns:
      headcount_trend    — active employee count for each of the last 12 months
      department_breakdown — current headcount per department
      employment_type_breakdown — full_time / part_time / contract / intern
      status_breakdown   — active / on_leave / suspended / terminated
      new_hires_trend    — new hires per month (last 12 months, using start_date)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.payroll.models import EmployeeProfile

        company_id = request_company_id(request)
        today = timezone.localdate()

        base_qs = EmployeeProfile.objects.filter(
            is_deleted=False, company_id=company_id
        )

        # Department breakdown (current active employees)
        dept_breakdown = list(
            base_qs.filter(employment_status='active')
            .values('department')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        for row in dept_breakdown:
            if not row['department']:
                row['department'] = 'Unassigned'

        # Employment type breakdown
        type_breakdown = list(
            base_qs.filter(employment_status='active')
            .values('employment_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Status breakdown
        status_breakdown = list(
            base_qs.values('employment_status')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Monthly headcount + new hires for last 12 months
        headcount_trend = []
        new_hires_trend = []
        for months_back in range(11, -1, -1):
            month_date = today.replace(day=1) - datetime.timedelta(days=months_back * 28)
            # Normalise to 1st of month
            month_date = month_date.replace(day=1)
            month_end = (month_date.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
            label = month_date.strftime('%b %Y')

            active_at_month_end = base_qs.filter(
                start_date__lte=month_end
            ).exclude(
                Q(employment_status='terminated') & Q(end_date__lt=month_date) |
                Q(employment_status='resigned') & Q(end_date__lt=month_date)
            ).count()

            new_in_month = base_qs.filter(
                start_date__year=month_date.year,
                start_date__month=month_date.month,
            ).count()

            headcount_trend.append({'month': label, 'count': active_at_month_end})
            new_hires_trend.append({'month': label, 'count': new_in_month})

        return Response({
            'department_breakdown': dept_breakdown,
            'employment_type_breakdown': type_breakdown,
            'status_breakdown': status_breakdown,
            'headcount_trend': headcount_trend,
            'new_hires_trend': new_hires_trend,
        })


class RecruitmentPipelineView(APIView):
    """
    GET /api/analytics/recruitment/

    Query params:
      job_posting_id  — filter to a specific posting (optional)

    Returns:
      pipeline_funnel   — candidate count per stage across all open jobs
      by_posting        — per-job breakdown: title, stage counts, avg AI score
      source_breakdown  — where candidates are coming from
      ai_score_dist     — distribution of AI scores in 10-point buckets
      time_to_stage     — avg days to reach each stage (from screened)
      hired_last_30d    — count of hires in last 30 days
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.recruitment.models import Candidate, JobPosting

        company_id = request_company_id(request)
        job_posting_id = request.query_params.get('job_posting_id')

        candidate_qs = Candidate.objects.filter(
            company_id=company_id, is_deleted=False
        )
        if job_posting_id:
            candidate_qs = candidate_qs.filter(job_posting_id=job_posting_id)

        # Overall pipeline funnel
        stage_order = [
            'screened', 'interview_l1', 'interview_l2',
            'offer_sent', 'hired', 'rejected',
        ]
        stage_counts = dict(
            candidate_qs.values('current_stage')
            .annotate(count=Count('id'))
            .values_list('current_stage', 'count')
        )
        pipeline_funnel = [
            {'stage': s, 'count': stage_counts.get(s, 0)}
            for s in stage_order
        ]

        # Per-posting breakdown
        postings = JobPosting.objects.filter(
            company_id=company_id, is_deleted=False
        )
        if job_posting_id:
            postings = postings.filter(id=job_posting_id)

        by_posting = []
        for posting in postings.order_by('-created_at')[:20]:
            posting_candidates = candidate_qs.filter(job_posting=posting)
            stage_dist = dict(
                posting_candidates.values('current_stage')
                .annotate(count=Count('id'))
                .values_list('current_stage', 'count')
            )
            avg_score = posting_candidates.aggregate(
                avg=Avg('ai_score')
            )['avg']
            by_posting.append({
                'job_posting_id': str(posting.id),
                'title': posting.title,
                'department': posting.department,
                'status': posting.status,
                'total_candidates': posting_candidates.count(),
                'stage_distribution': stage_dist,
                'avg_ai_score': round(avg_score, 1) if avg_score else None,
            })

        # Source breakdown
        source_breakdown = list(
            candidate_qs.values('source')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # AI score distribution (10-point buckets: 0-9, 10-19, ..., 90-100)
        score_dist = []
        for bucket_start in range(0, 100, 10):
            bucket_end = bucket_start + 9 if bucket_start < 90 else 100
            count = candidate_qs.filter(
                ai_score__gte=bucket_start,
                ai_score__lte=bucket_end,
            ).count()
            score_dist.append({
                'bucket': f'{bucket_start}-{bucket_end}',
                'count': count,
            })

        # Hired last 30 days
        thirty_days_ago = timezone.localdate() - datetime.timedelta(days=30)
        hired_30d = candidate_qs.filter(
            current_stage='hired',
            updated_at__date__gte=thirty_days_ago,
        ).count()

        return Response({
            'pipeline_funnel': pipeline_funnel,
            'by_posting': by_posting,
            'source_breakdown': source_breakdown,
            'ai_score_distribution': score_dist,
            'hired_last_30d': hired_30d,
        })


class PayrollAnalyticsView(APIView):
    """
    GET /api/analytics/payroll/

    Returns:
      cost_trend         — total net payroll per month (last 12 completed runs)
      department_cost    — net salary sum per department for last completed run
      payment_method_split — bank / mpesa / airtel headcount and total
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.payroll.models import PayrollRecord, PayrollRun

        company_id = request_company_id(request)

        # Monthly cost trend — last 12 paid/completed runs
        runs = (
            PayrollRun.objects.filter(
                company_id=company_id,
                is_deleted=False,
                status__in=['completed', 'paid'],
            )
            .order_by('-period_year', '-period_month')[:12]
        )

        cost_trend = []
        for run in reversed(list(runs)):
            import calendar
            month_label = f"{calendar.month_abbr[run.period_month]} {run.period_year}"
            cost_trend.append({
                'month': month_label,
                'total_gross': float(run.total_gross or 0),
                'total_deductions': float(run.total_deductions or 0),
                'total_net': float(run.total_net or 0),
            })

        # Department cost from most recent completed run
        latest_run = runs.first()
        department_cost = []
        if latest_run:
            records = (
                PayrollRecord.objects.filter(
                    payroll_run=latest_run, is_deleted=False
                )
                .select_related('employee')
            )
            dept_agg = {}
            for rec in records:
                dept = rec.employee.department or 'Unassigned'
                if dept not in dept_agg:
                    dept_agg[dept] = {'gross': 0, 'net': 0, 'count': 0}
                dept_agg[dept]['gross'] += float(rec.gross_salary or 0)
                dept_agg[dept]['net'] += float(rec.net_salary or 0)
                dept_agg[dept]['count'] += 1
            department_cost = [
                {'department': d, **v}
                for d, v in sorted(dept_agg.items(), key=lambda x: -x[1]['net'])
            ]

        # Payment method split from most recent run
        payment_split = []
        if latest_run:
            for method in ['bank', 'mpesa', 'airtel']:
                method_records = PayrollRecord.objects.filter(
                    payroll_run=latest_run,
                    is_deleted=False,
                    payment_method=method,
                )
                agg = method_records.aggregate(total=Sum('net_salary'))
                payment_split.append({
                    'method': method,
                    'count': method_records.count(),
                    'total_net': float(agg['total'] or 0),
                })

        return Response({
            'cost_trend': cost_trend,
            'department_cost': department_cost,
            'payment_method_split': payment_split,
            'latest_run_period': latest_run.period_display if latest_run else None,
        })
