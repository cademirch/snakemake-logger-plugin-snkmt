import os
import pytest
import tempfile
from pathlib import Path
import subprocess
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from snkmt.db.models.workflow import Workflow
from snkmt.db.models.rule import Rule
from snkmt.db.models.job import Job
from snkmt.db.models.file import File
from snkmt.db.models.enums import Status, FileType


@pytest.fixture(scope="module")
def temp_workflow_dir():
    """Create a temporary directory with a simple Snakemake workflow."""
    temp_dir = tempfile.mkdtemp()
    cwd = os.getcwd()

    # Create a simple Snakefile
    snakefile = os.path.join(temp_dir, "Snakefile")
    with open(snakefile, "w") as f:
        f.write("""
rule all:
    input:
        "output1.txt",
        "output2.txt",
        "combined.txt"

rule create_file1:
    output:
        "output1.txt"
    shell:
        "echo 'Content from file 1' > {output}"

rule create_file2:
    output:
        "output2.txt"
    shell:
        "echo 'Content from file 2' > {output}"

rule combine_files:
    input:
        "output1.txt",
        "output2.txt"
    output:
        "combined.txt"
    shell:
        "cat {input} > {output}"
""")

    os.chdir(temp_dir)
    yield temp_dir
    os.chdir(cwd)


@pytest.fixture(scope="module")
def snakemake_session(temp_workflow_dir):
    """Create a session fixture that runs Snakemake once and provides a database session."""
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

    # Ensure the database exists
    if not os.path.exists(db_path):
        pytest.fail("SQLite database was not created")

    # Connect to the database using SQLAlchemy
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    # Clean up
    session.close()


def test_workflow_model(snakemake_session):
    """Test the Workflow model and its attributes."""
    session = snakemake_session

    # Test Workflow model
    workflows = session.query(Workflow).all()
    assert len(workflows) > 0, "No workflow entries found"
    workflow = workflows[0]

    # Basic workflow attributes
    assert workflow.status in [Status.SUCCESS, Status.RUNNING], (
        f"Unexpected workflow status: {workflow.status}"
    )
    assert workflow.started_at is not None, "Workflow started_at is None"
    assert workflow.total_job_count == 4, (
        f"Expected 4 jobs, got {workflow.total_job_count}"
    )
    assert workflow.jobs_finished == 4, (
        f"Expected 4 finished jobs, got {workflow.jobs_finished}"
    )

    # Test progress calculation
    assert workflow.progress == 1.0, f"Expected progress 1.0, got {workflow.progress}"


def test_rule_model(snakemake_session):
    """Test the Rule model and its attributes."""
    session = snakemake_session

    # Test Rule model
    rules = session.query(Rule).all()
    assert len(rules) == 4, f"Expected 4 rules, found {len(rules)}"

    # Test rule names
    rule_names = {rule.name for rule in rules}
    expected_rule_names = {"all", "create_file1", "create_file2", "combine_files"}
    assert rule_names == expected_rule_names, f"Unexpected rule names: {rule_names}"

    # Test rule job counts
    for rule in rules:
        assert rule.total_job_count == 1, (
            f"Expected 1 job for rule {rule.name}, got {rule.total_job_count}"
        )
        assert rule.jobs_finished == 1, (
            f"Expected 1 finished job for rule {rule.name}, got {rule.jobs_finished}"
        )
        assert rule.progress == 1.0, (
            f"Expected progress 1.0 for rule {rule.name}, got {rule.progress}"
        )


def test_job_model(snakemake_session):
    """Test the Job model and its attributes."""
    session = snakemake_session

    # Test Job model
    jobs = session.query(Job).all()
    assert len(jobs) == 4, f"Expected 4 jobs, found {len(jobs)}"

    # Test job statuses
    job_statuses = {job.status for job in jobs}
    assert Status.SUCCESS in job_statuses, "No successful jobs found"

    # Test specific job attributes
    for job in jobs:
        assert job.started_at is not None, f"Job {job.id} has no start time"
        assert job.end_time is not None, f"Job {job.id} has no end time"
        assert job.status == Status.SUCCESS, f"Job {job.id} status is not SUCCESS"


def test_file_model(snakemake_session):
    """Test the File model and its attributes."""
    session = snakemake_session

    # Test File model
    files = session.query(File).all()
    assert len(files) >= 3, f"Expected at least 3 files, found {len(files)}"

    # Test file paths
    file_paths = {os.path.basename(file.path) for file in files}
    expected_files = {"output1.txt", "output2.txt", "combined.txt"}
    assert expected_files.issubset(file_paths), (
        f"Missing expected files: {expected_files - file_paths}"
    )

    # Test file types
    file_types = {file.file_type for file in files}
    assert FileType.INPUT in file_types, "No input files found"
    assert FileType.OUTPUT in file_types, "No output files found"


def test_rule_job_relationship(snakemake_session):
    """Test the relationships between rules and jobs."""
    session = snakemake_session

    # Test rule-job relationships
    jobs = session.query(Job).all()
    expected_rule_names = {"all", "create_file1", "create_file2", "combine_files"}

    for job in jobs:
        assert job.rule is not None, f"Job {job.id} has no associated rule"
        assert job.rule.name in expected_rule_names, (
            f"Job has unexpected rule: {job.rule.name}"
        )

        # Check bidirectional relationship
        assert job in job.rule.jobs, (
            f"Job {job.id} not found in rule.jobs for rule {job.rule.name}"
        )


def test_job_file_relationship(snakemake_session):
    """Test the relationships between jobs and files."""
    session = snakemake_session

    # Find the combine_files job
    combine_job = (
        session.query(Job).join(Rule).filter(Rule.name == "combine_files").first()
    )
    assert combine_job is not None, "Combine files job not found"

    # Test input files
    combine_job_input_files = [
        f for f in combine_job.files if f.file_type == FileType.INPUT
    ]
    input_files = {os.path.basename(f.path) for f in combine_job_input_files}
    expected_inputs = {"output1.txt", "output2.txt"}
    assert expected_inputs.issubset(input_files), (
        "Missing input files for combine_files job"
    )

    # Test output files
    combine_job_output_files = [
        f for f in combine_job.files if f.file_type == FileType.OUTPUT
    ]
    output_files = {os.path.basename(f.path) for f in combine_job_output_files}
    assert "combined.txt" in output_files, "Missing output file for combine_files job"
