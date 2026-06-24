WORKFLOW_TEMPLATES = [
    {
        'id': 'candidate-welcome-email',
        'name': 'Candidate Welcome Email',
        'description': 'Send a confirmation email to the candidate when they apply.',
        'trigger_type': 'candidate_applied',
        'condition_logic': 'AND',
        'conditions': [],
        'actions': [
            {
                'type': 'send_email',
                'params': {
                    'recipient': '{{candidate_email}}',
                    'subject': 'Your application for {{job_posting_title}} has been received',
                    'body': (
                        'Hi {{candidate_name}},\n\n'
                        'Thank you for applying for the {{job_posting_title}} position. '
                        'We have received your application and will review it shortly.\n\n'
                        'Best regards,\nThe Recruitment Team'
                    ),
                },
            }
        ],
    },
    {
        'id': 'interview-followup-task',
        'name': 'Interview Follow-up Task',
        'description': 'Create a task for HR to follow up after an interview is completed.',
        'trigger_type': 'interview_completed',
        'condition_logic': 'AND',
        'conditions': [],
        'actions': [
            {
                'type': 'create_task',
                'params': {
                    'title': 'Follow up with {{candidate_name}} after {{interview_type}} interview',
                    'description': 'Review feedback and advance or reject the candidate.',
                    'priority': 'high',
                    'source_module': 'recruitment',
                },
            }
        ],
    },
    {
        'id': 'leave-submission-notify',
        'name': 'Leave Submission Task',
        'description': 'Create a task for HR when an employee submits a leave request.',
        'trigger_type': 'leave_submitted',
        'condition_logic': 'AND',
        'conditions': [],
        'actions': [
            {
                'type': 'create_task',
                'params': {
                    'title': 'Review leave request: {{leave_type}} ({{start_date}} to {{end_date}})',
                    'description': 'Employee {{employee_id}} has requested {{days_requested}} days of {{leave_type}} leave.',
                    'priority': 'normal',
                    'source_module': 'leave',
                },
            }
        ],
    },
    {
        'id': 'exit-process-checklist',
        'name': 'Exit Process Action Item',
        'description': 'Create an action item when an employee exit process is started.',
        'trigger_type': 'exit_process_started',
        'condition_logic': 'AND',
        'conditions': [],
        'actions': [
            {
                'type': 'create_action_item',
                'params': {
                    'title': 'Exit process started for employee {{employee_id}}',
                    'description': 'Kind: {{exit_kind}}. Reason: {{exit_reason}}. Last working day: {{last_working_day}}.',
                    'priority': 'high',
                    'source_module': 'exits',
                },
            }
        ],
    },
    {
        'id': 'high-score-candidate-fast-track',
        'name': 'Fast-track High-Score Candidates',
        'description': 'Create an urgent task when a candidate\'s AI score is 80 or higher.',
        'trigger_type': 'candidate_applied',
        'condition_logic': 'AND',
        'conditions': [
            {'field': 'candidate_ai_score', 'operator': 'gte', 'value': '80'},
        ],
        'actions': [
            {
                'type': 'create_task',
                'params': {
                    'title': 'Fast-track: {{candidate_name}} scored {{candidate_ai_score}} for {{job_posting_title}}',
                    'description': 'This candidate scored above the fast-track threshold. Review immediately.',
                    'priority': 'urgent',
                    'source_module': 'recruitment',
                },
            }
        ],
    },
]
