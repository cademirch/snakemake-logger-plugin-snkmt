from datetime import datetime
from logging import LogRecord
from pathlib import Path
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session
from snakemake_interface_logger_plugins.common import LogEvent

import snakemake_logger_plugin_snkmt.parsers as parsers
from snkmt.db.models.enums import FileType, Status
from snkmt.db.models import File, Job, Rule, Error, Workflow


class EventHandler:
    """
    Unified event handler for processing Snakemake log events.
    - current_workflow_id: UUID of the active workflow
    - jobs: Mapping of Snakemake job IDs to database job IDs
    - dryrun: Whether this is a dry run
    """

    def __init__(self, dryrun: bool = False):
        self.current_workflow_id: Optional[UUID] = None
        self.jobs: Dict[int, int] = {}  # Snakemake job ID -> database job ID
        self.dryrun: bool = dryrun

    def handle(self, event_type: LogEvent, record: LogRecord, session: Session) -> None:
        """Route events to appropriate handler methods"""
        handler_map = {
            LogEvent.WORKFLOW_STARTED: self.handle_workflow_started,
            LogEvent.RUN_INFO: self.handle_run_info,
            LogEvent.JOB_INFO: self.handle_job_info,
            LogEvent.JOB_STARTED: self.handle_job_started,
            LogEvent.JOB_FINISHED: self.handle_job_finished,
            LogEvent.JOB_ERROR: self.handle_job_error,
            LogEvent.RULEGRAPH: self.handle_rule_graph,
            LogEvent.GROUP_INFO: self.handle_group_info,
            LogEvent.GROUP_ERROR: self.handle_group_error,
            LogEvent.ERROR: self.handle_error,
        }

        handler = handler_map.get(event_type)
        if handler:
            handler(record, session)

    def _get_or_create_rule(self, rule_name: str, session: Session) -> Rule:
        """Helper to get or create a rule"""
        if not self.current_workflow_id:
            raise ValueError("No current workflow ID")

        rule = (
            session.query(Rule)
            .filter_by(name=rule_name, workflow_id=self.current_workflow_id)
            .first()
        )

        if not rule:
            rule = Rule(name=rule_name, workflow_id=self.current_workflow_id)
            session.add(rule)
            session.flush()

        return rule

    def _add_files(
        self,
        job: Job,
        file_paths: Optional[list[str]],
        file_type: FileType,
        session: Session,
    ) -> None:
        """Helper method to add files of a specific type to a job"""
        if not file_paths:
            return

        for path in file_paths:
            abs_path = Path(path).resolve()
            file = File(path=str(abs_path), file_type=file_type, job_id=job.id)
            session.add(file)

    def handle_workflow_started(self, record: LogRecord, session: Session) -> None:
        """Handle workflow started event"""
        workflow_data = parsers.WorkflowStarted.from_record(record)
        workflow = Workflow(
            id=workflow_data.workflow_id,
            snakefile=workflow_data.snakefile,
            dryrun=self.dryrun,
            status=Status.RUNNING,
        )

        session.add(workflow)
        self.current_workflow_id = workflow_data.workflow_id

    def handle_run_info(self, record: LogRecord, session: Session) -> None:
        """Handle run info event"""
        if not self.current_workflow_id:
            return

        run_info = parsers.RunInfo.from_record(record)
        workflow = (
            session.query(Workflow).filter_by(id=self.current_workflow_id).first()
        )

        if workflow:
            workflow.total_job_count = run_info.total_job_count

            for rule_name, count in run_info.per_rule_job_counts.items():
                rule = (
                    session.query(Rule)
                    .filter_by(name=rule_name, workflow_id=workflow.id)
                    .first()
                )
                if rule:
                    rule.total_job_count = count
                else:
                    session.add(
                        Rule(
                            name=rule_name,
                            workflow_id=workflow.id,
                            total_job_count=count,
                        )
                    )

    def handle_job_info(self, record: LogRecord, session: Session) -> None:
        """Handle job info event"""
        if not self.current_workflow_id:
            return

        job_data = parsers.JobInfo.from_record(record)
        rule = self._get_or_create_rule(job_data.rule_name, session)

        job = Job(
            snakemake_id=job_data.jobid,
            workflow_id=self.current_workflow_id,
            rule_id=rule.id,
            message=job_data.rule_msg,
            wildcards=job_data.wildcards,
            reason=job_data.reason,
            resources=job_data.resources,
            shellcmd=job_data.shellcmd,
            threads=job_data.threads,
            priority=job_data.priority,
            status=Status.RUNNING,
        )
        session.add(job)
        session.flush()

        self._add_files(job, job_data.input, FileType.INPUT, session)
        self._add_files(job, job_data.output, FileType.OUTPUT, session)
        self._add_files(job, job_data.log, FileType.LOG, session)
        self._add_files(job, job_data.benchmark, FileType.BENCHMARK, session)

        self.jobs[job_data.jobid] = job.id

    def handle_job_started(self, record: LogRecord, session: Session) -> None:
        """Handle job started event"""
        if not self.current_workflow_id:
            return

        job_data = parsers.JobStarted.from_record(record)

        for snakemake_job_id in job_data.job_ids:
            if snakemake_job_id in self.jobs:
                db_job_id = self.jobs[snakemake_job_id]
                job = session.query(Job).get(db_job_id)
                if job:
                    job.status = Status.RUNNING
                    job.started_at = datetime.utcnow()

    def handle_job_finished(self, record: LogRecord, session: Session) -> None:
        """Handle job finished event"""
        if not self.current_workflow_id:
            return

        job_data = parsers.JobFinished.from_record(record)
        snakemake_job_id = job_data.job_id

        if snakemake_job_id in self.jobs:
            db_job_id = self.jobs[snakemake_job_id]
            job = session.query(Job).get(db_job_id)
            if job:
                job.finish(session=session)

    def handle_job_error(self, record: LogRecord, session: Session) -> None:
        """Handle job error event"""
        if not self.current_workflow_id:
            return

        job_data = parsers.JobError.from_record(record)
        snakemake_job_id = job_data.jobid

        if snakemake_job_id in self.jobs:
            db_job_id = self.jobs[snakemake_job_id]
            job = session.query(Job).get(db_job_id)
            if job:
                job.status = Status.ERROR
                job.end_time = datetime.utcnow()

    def handle_rule_graph(self, record: LogRecord, session: Session) -> None:
        """Handle rule graph event"""
        if not self.current_workflow_id:
            return

        graph_data = parsers.RuleGraph.from_record(record)
        workflow = session.query(Workflow).get(self.current_workflow_id)

        if workflow:
            workflow.rulegraph_data = graph_data.rulegraph

    def handle_group_info(self, record: LogRecord, session: Session) -> None:
        """Handle group info event"""
        if not self.current_workflow_id:
            return

        group_data = parsers.GroupInfo.from_record(record)

        for job_ref in group_data.jobs:
            job_id = getattr(job_ref, "jobid", job_ref)
            if isinstance(job_id, int) and job_id in self.jobs:
                db_job_id = self.jobs[job_id]
                job = session.query(Job).get(db_job_id)
                if job:
                    job.group_id = group_data.group_id

    def handle_group_error(self, record: LogRecord, session: Session) -> None:
        """Handle group error event"""
        if not self.current_workflow_id:
            return

        group_error = parsers.GroupError.from_record(record)

        if hasattr(group_error.job_error_info, "jobid"):
            snakemake_job_id = group_error.job_error_info.jobid  # type: ignore
            if snakemake_job_id in self.jobs:
                db_job_id = self.jobs[snakemake_job_id]
                job = session.query(Job).get(db_job_id)
                if job:
                    job.status = Status.ERROR
                    job.end_time = datetime.utcnow()

    def handle_error(self, record: LogRecord, session: Session) -> None:
        """Handle general error event"""
        if not self.current_workflow_id:
            return

        error_data = parsers.Error.from_record(record)

        rule_id = None
        if error_data.rule:
            rule = self._get_or_create_rule(error_data.rule, session)
            rule_id = rule.id

        error = Error(
            exception=error_data.exception,
            location=error_data.location,
            traceback=error_data.traceback,
            file=error_data.file,
            line=error_data.line,
            workflow_id=self.current_workflow_id,
            rule_id=rule_id,
        )

        session.add(error)

        workflow = (
            session.query(Workflow)
            .filter(Workflow.id == self.current_workflow_id)
            .first()
        )
        if workflow and workflow.status == "RUNNING":
            workflow.status = "ERROR"  # type: ignore

    def reset(self) -> None:
        """Reset the handler state (useful for new workflow runs)"""
        self.current_workflow_id = None
        self.jobs.clear()
