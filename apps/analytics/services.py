"""
Cached aggregation services for executive analytics.
Each method is a @staticmethod that accepts company_id and kwargs,
checks the cache, computes if missed, sets with TTL=300s.
"""
import hashlib
import json
from datetime import date, timedelta

from django.core.cache import cache
from django.db.models import Avg, Count, Sum
from django.utils import timezone

CACHE_TTL = 300


def _cache_key(prefix: str, company_id, **kwargs) -> str:
    suffix = hashlib.md5(
        json.dumps({'cid': str(company_id), **kwargs}, sort_keys=True).encode()
    ).hexdigest()[:12]
    return f'analytics:{prefix}:{suffix}'


def _today():
    return timezone.now().date()


class AnalyticsService:

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------

    @staticmethod
    def overview(company_id):
        key = _cache_key('overview', company_id)
        cached = cache.get(key)
        if cached is not None:
            return cached

        from apps.payroll.models import EmployeeProfile, PayrollRun
        from apps.recruitment.models import Candidate, JobPosting
        from apps.hr.models import LeaveRequest
        from apps.crm.models import Placement, RecruitmentClient

        today = _today()
        thirty_ago = today - timedelta(days=30)

        total_employees = EmployeeProfile.objects.filter(
            company_id=company_id, is_deleted=False,
            employment_status='active').count()

        new_hires_30d = EmployeeProfile.objects.filter(
            company_id=company_id, is_deleted=False,
            start_date__gte=thirty_ago).count()

        open_jobs = JobPosting.objects.filter(
            company_id=company_id, is_deleted=False, status='open').count()

        active_candidates = Candidate.objects.filter(
            company_id=company_id, is_deleted=False).count()

        pending_leave = LeaveRequest.objects.filter(
            company_id=company_id, status='pending').count()

        last_run = PayrollRun.objects.filter(
            company=company_id, status='completed',
        ).order_by('-period_year', '-period_month').first()
        payroll_last_total = float(last_run.total_net) if last_run else None

        placements_30d = Placement.objects.filter(
            company_id=company_id,
            start_date__gte=thirty_ago,
        ).exclude(status='cancelled').count()

        active_clients = RecruitmentClient.objects.filter(
            company_id=company_id, status='active', is_deleted=False).count()

        result = {
            'total_employees': total_employees,
            'new_hires_30d': new_hires_30d,
            'open_job_postings': open_jobs,
            'active_candidates': active_candidates,
            'pending_leave_requests': pending_leave,
            'payroll_last_run_total': payroll_last_total,
            'placements_30d': placements_30d,
            'active_clients': active_clients,
        }
        cache.set(key, result, CACHE_TTL)
        return result

    # ------------------------------------------------------------------
    # Headcount
    # ------------------------------------------------------------------

    @staticmethod
    def headcount(company_id):
        key = _cache_key('headcount', company_id)
        cached = cache.get(key)
        if cached is not None:
            return cached

        from apps.payroll.models import EmployeeProfile
        from apps.hr.models import EmployeeExit

        base_qs = EmployeeProfile.objects.filter(
            company_id=company_id, is_deleted=False)

        by_dept = list(
            base_qs.values('department')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        by_type = list(
            base_qs.values('employment_type')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        by_class = list(
            base_qs.values('worker_class')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        # Monthly hires: last 12 months
        twelve_ago = _today() - timedelta(days=365)
        monthly_hires_qs = (
            base_qs.filter(start_date__gte=twelve_ago)
            .extra(select={'yr': "strftime('%%Y', start_date)",
                           'mo': "strftime('%%m', start_date)"})
            .values('yr', 'mo')
            .annotate(count=Count('id'))
            .order_by('yr', 'mo')
        )
        monthly_hires = [
            {'year': int(r['yr']), 'month': int(r['mo']), 'count': r['count']}
            for r in monthly_hires_qs
        ]

        # Monthly exits: last 12 months
        monthly_exits_qs = (
            EmployeeExit.objects.filter(
                company_id=company_id,
                last_working_day__gte=twelve_ago,
                last_working_day__isnull=False,
            )
            .extra(select={'yr': "strftime('%%Y', last_working_day)",
                           'mo': "strftime('%%m', last_working_day)"})
            .values('yr', 'mo')
            .annotate(count=Count('id'))
            .order_by('yr', 'mo')
        )
        monthly_exits = [
            {'year': int(r['yr']), 'month': int(r['mo']), 'count': r['count']}
            for r in monthly_exits_qs
        ]

        total = base_qs.count()
        exits_12m = sum(r['count'] for r in monthly_exits)
        attrition_rate = round((exits_12m / total * 100), 2) if total else 0.0

        result = {
            'total': total,
            'by_department': by_dept,
            'by_employment_type': by_type,
            'by_worker_class': by_class,
            'monthly_hires': monthly_hires,
            'monthly_exits': monthly_exits,
            'attrition_rate_12m': attrition_rate,
        }
        cache.set(key, result, CACHE_TTL)
        return result

    # ------------------------------------------------------------------
    # Recruitment
    # ------------------------------------------------------------------

    @staticmethod
    def recruitment(company_id, job_posting_id=None):
        key = _cache_key('recruitment', company_id, jp=str(job_posting_id or ''))
        cached = cache.get(key)
        if cached is not None:
            return cached

        from apps.recruitment.models import Candidate, Interview, JobPosting

        cands = Candidate.objects.filter(
            company_id=company_id, is_deleted=False)
        if job_posting_id:
            cands = cands.filter(job_posting_id=job_posting_id)

        by_stage = list(
            cands.values('current_stage')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        by_source = list(
            cands.values('source')
            .annotate(count=Count('id'))
            .order_by('-count')
        )

        total = cands.count()
        hired = cands.filter(current_stage='hired').count()
        conversion_rate = round(hired / total * 100, 2) if total else 0.0
        avg_score_agg = cands.filter(ai_score__isnull=False).aggregate(
            avg=Avg('ai_score'))
        avg_score = round(avg_score_agg['avg'] or 0, 2)

        interviews_qs = Interview.objects.filter(company_id=company_id)
        if job_posting_id:
            interviews_qs = interviews_qs.filter(job_posting_id=job_posting_id)

        top_postings = list(
            Candidate.objects.filter(company_id=company_id, is_deleted=False)
            .values('job_posting__id', 'job_posting__title')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )

        result = {
            'total_applications': total,
            'hired_count': hired,
            'conversion_rate': conversion_rate,
            'avg_ai_score': avg_score,
            'by_stage': by_stage,
            'by_source': by_source,
            'interviews_scheduled': interviews_qs.count(),
            'interviews_completed': interviews_qs.filter(
                status='completed').count(),
            'top_postings': [
                {'job_posting_id': str(r['job_posting__id']),
                 'title': r['job_posting__title'],
                 'count': r['count']}
                for r in top_postings
            ],
        }
        cache.set(key, result, CACHE_TTL)
        return result

    # ------------------------------------------------------------------
    # Payroll
    # ------------------------------------------------------------------

    @staticmethod
    def payroll(company_id, months=12):
        months = min(int(months), 24)
        key = _cache_key('payroll', company_id, months=months)
        cached = cache.get(key)
        if cached is not None:
            return cached

        from apps.payroll.models import EmployeeProfile, PayrollRun

        current_year = _today().year
        runs = list(
            PayrollRun.objects.filter(
                company_id=company_id, status='completed',
            ).order_by('-period_year', '-period_month')[:months]
        )

        monthly_trend = [
            {
                'year': r.period_year,
                'month': r.period_month,
                'total_gross': float(r.total_gross or 0),
                'total_net': float(r.total_net or 0),
                'total_deductions': float(r.total_deductions or 0),
            }
            for r in reversed(runs)
        ]

        ytd_agg = PayrollRun.objects.filter(
            company_id=company_id, status='completed',
            period_year=current_year,
        ).aggregate(ytd=Sum('total_net'))
        total_ytd = float(ytd_agg['ytd'] or 0)

        avg_salary_agg = EmployeeProfile.objects.filter(
            company_id=company_id, is_deleted=False,
        ).aggregate(avg=Avg('salary'))
        avg_salary = float(avg_salary_agg['avg'] or 0)

        result = {
            'monthly_trend': monthly_trend,
            'total_spend_ytd': total_ytd,
            'avg_salary': round(avg_salary, 2),
            'run_count': len(runs),
        }
        cache.set(key, result, CACHE_TTL)
        return result

    # ------------------------------------------------------------------
    # Leave
    # ------------------------------------------------------------------

    @staticmethod
    def leave(company_id, year=None):
        if year is None:
            year = _today().year
        year = int(year)
        key = _cache_key('leave', company_id, year=year)
        cached = cache.get(key)
        if cached is not None:
            return cached

        from apps.hr.models import LeaveBalance, LeaveRequest
        from apps.payroll.models import EmployeeProfile

        requests = LeaveRequest.objects.filter(
            company_id=company_id,
            start_date__year=year,
        )

        by_type = list(
            requests.values('leave_type')
            .annotate(count=Count('id'), total_days=Sum('days_requested'))
            .order_by('-total_days')
        )

        by_status = list(
            requests.values('status')
            .annotate(count=Count('id'))
        )

        approved_days_agg = requests.filter(status='approved').aggregate(
            total=Sum('days_requested'))
        total_approved_days = float(approved_days_agg['total'] or 0)

        headcount = EmployeeProfile.objects.filter(
            company_id=company_id, is_deleted=False).count()
        avg_days = round(total_approved_days / headcount, 2) if headcount else 0

        balances = LeaveBalance.objects.filter(
            company_id=company_id, year=year)
        bal_agg = balances.aggregate(
            total=Sum('total_days'), used=Sum('used_days'))
        total_bal = bal_agg['total'] or 0
        used_bal = bal_agg['used'] or 0
        utilization = round(used_bal / total_bal * 100, 2) if total_bal else 0.0

        result = {
            'year': year,
            'by_type': by_type,
            'by_status': by_status,
            'total_approved_days': total_approved_days,
            'avg_days_per_employee': avg_days,
            'leave_utilization_rate': utilization,
        }
        cache.set(key, result, CACHE_TTL)
        return result

    # ------------------------------------------------------------------
    # Placements
    # ------------------------------------------------------------------

    @staticmethod
    def placements(company_id, months=12):
        months = min(int(months), 24)
        key = _cache_key('placements', company_id, months=months)
        cached = cache.get(key)
        if cached is not None:
            return cached

        from apps.crm.models import Placement, RecruitmentClient

        current_year = _today().year
        cutoff = _today() - timedelta(days=months * 31)

        base = Placement.objects.filter(company_id=company_id)

        monthly_qs = (
            base.filter(start_date__gte=cutoff)
            .exclude(status='cancelled')
            .extra(select={'yr': "strftime('%%Y', start_date)",
                           'mo': "strftime('%%m', start_date)"})
            .values('yr', 'mo')
            .annotate(count=Count('id'), fee_total=Sum('placement_fee'))
            .order_by('yr', 'mo')
        )
        monthly_placements = [
            {
                'year': int(r['yr']), 'month': int(r['mo']),
                'count': r['count'],
                'fee_total': float(r['fee_total'] or 0),
            }
            for r in monthly_qs
        ]

        ytd_agg = base.filter(
            start_date__year=current_year,
        ).exclude(status='cancelled').aggregate(
            total=Sum('placement_fee'), count=Count('id'))
        fee_ytd = float(ytd_agg['total'] or 0)

        by_status = list(
            base.values('status').annotate(count=Count('id')))

        top_clients = list(
            base.exclude(status='cancelled')
            .values('client__id', 'client__name')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )

        result = {
            'monthly_placements': monthly_placements,
            'total_fee_ytd': fee_ytd,
            'total_placements': base.exclude(status='cancelled').count(),
            'placements_ytd': ytd_agg['count'] or 0,
            'by_status': by_status,
            'top_clients': [
                {'client_id': str(r['client__id']),
                 'client_name': r['client__name'],
                 'count': r['count']}
                for r in top_clients
            ],
        }
        cache.set(key, result, CACHE_TTL)
        return result
