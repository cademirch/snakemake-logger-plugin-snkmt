import os
import pytest
import tempfile
from pathlib import Path
import subprocess
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from snkmt.core.models.workflow import Workflow
from snkmt.core.models.rule import Rule
from snkmt.core.models.job import Job
from snkmt.types.enums import Status


# A checkpoint workflow: `split` writes a variable number of files, the DAG is
# re-evaluated, fanning out into one `process` job per file, and `aggregate`
# combines them. Snakemake only emits the run_info/job-stats event once, before
# `split` runs, so the post-checkpoint jobs are invisible to it. This exercises
# that the plugin still records correct totals via the progress event.
CHECKPOINT_SNAKEFILE = """
import os

rule all:
    input:
        "aggregated.txt"

checkpoint split:
    output:
        directory("splits")
    shell:
        "mkdir -p splits && for i in 1 2 3; do echo content$i > splits/file$i.txt; done"

def aggregate_input(wildcards):
    checkpoint_output = checkpoints.split.get(**wildcards).output[0]
    return expand(
        "processed/{i}.txt",
        i=glob_wildcards(os.path.join(checkpoint_output, "file{i}.txt")).i,
    )

rule process:
    input:
        "splits/file{i}.txt"
    output:
        "processed/{i}.txt"
    shell:
        "cp {input} {output}"

rule aggregate:
    input:
        aggregate_input
    output:
        "aggregated.txt"
    shell:
        "cat {input} > {output}"
"""


@pytest.fixture(scope="module")
def temp_workflow_dir():
    """Create a temporary directory with a checkpoint Snakemake workflow."""
    temp_dir = tempfile.mkdtemp()
    cwd = os.getcwd()

    snakefile = os.path.join(temp_dir, "Snakefile")
    with open(snakefile, "w") as f:
        f.write(CHECKPOINT_SNAKEFILE)

    os.chdir(temp_dir)
    yield temp_dir
    os.chdir(cwd)


@pytest.fixture(scope="module")
def snakemake_session(temp_workflow_dir):
    """Run the checkpoint workflow once and provide a database session."""
    db_path = Path(temp_workflow_dir, ".snakemake", "log", "snakemake.log.db").resolve()
    db_url = f"sqlite:///{db_path}"

    cmd = [
        "snakemake",
        "--logger",
        "snkmt",
        "--logger-snkmt-db",
        str(db_path),
        "-c1",
        "--no-hooks",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"Snakemake failed: {result.stderr}")

    if not os.path.exists(db_path):
        pytest.fail("SQLite database was not created")

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()


def test_workflow_total_reflects_checkpoint_expansion(snakemake_session):
    """The workflow total must include jobs created after the checkpoint."""
    session = snakemake_session

    workflows = session.query(Workflow).all()
    assert len(workflows) == 1, "Expected exactly one workflow"
    workflow = workflows[0]

    # 6 jobs run in total: all, split, aggregate, and 3x process. The initial
    # job-stats event only knows about 3 (all, split, aggregate).
    assert workflow.total_job_count == 6, (
        f"Expected total_job_count 6, got {workflow.total_job_count}"
    )
    assert workflow.jobs_finished == 6, (
        f"Expected 6 finished jobs, got {workflow.jobs_finished}"
    )
    assert workflow.progress == 1.0, f"Expected progress 1.0, got {workflow.progress}"
    assert workflow.status == Status.SUCCESS, f"Expected SUCCESS, got {workflow.status}"


def test_checkpoint_expanded_rule_total(snakemake_session):
    """The `process` rule is created by the checkpoint and must report 3 jobs."""
    session = snakemake_session

    process_rule = session.query(Rule).filter(Rule.name == "process").first()
    assert process_rule is not None, "process rule not found"
    assert process_rule.total_job_count == 3, (
        f"Expected 3 process jobs, got {process_rule.total_job_count}"
    )
    assert process_rule.jobs_finished == 3, (
        f"Expected 3 finished process jobs, got {process_rule.jobs_finished}"
    )
    assert process_rule.progress == 1.0, (
        f"Expected progress 1.0 for process rule, got {process_rule.progress}"
    )


def test_all_checkpoint_jobs_recorded(snakemake_session):
    """Every job, including checkpoint-spawned ones, is recorded as SUCCESS."""
    session = snakemake_session

    jobs = session.query(Job).all()
    assert len(jobs) == 6, f"Expected 6 jobs, found {len(jobs)}"
    assert all(job.status == Status.SUCCESS for job in jobs), (
        "Not all jobs reached SUCCESS"
    )

    rule_names = {job.rule.name for job in jobs}
    assert rule_names == {"all", "split", "aggregate", "process"}, (
        f"Unexpected rule set: {rule_names}"
    )
