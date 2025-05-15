# Snakemake Logger Plugin: snkmt

**This plugin is still under development and thus may not be fully stable or feature-complete. Use it at your own discretion and report any issues or suggestions to the repository's issue tracker.**

## Introduction

The **Snakemake Logger Plugin: snkmt** is a custom logger plugin for Snakemake that writes workflow execution logs to a SQLite database. This plugin enables detailed tracking of workflows, rules, jobs, and associated files, providing a structured and queryable format for analyzing workflow execution.

## Usage
1. Install via pip: `pip install snakemake-logger-plugin-snkmt`
2. Run Snakemake with the `--logger snkmt` option to enable the snkmt logger. 

## Options
TODO

## Design

The plugin integrates with Snakemake's logging system and processes log events using SQLAlchemy models. It uses event handlers to parse and store log records in the database. The database schema is designed to capture key entities such as workflows, rules, jobs, and files, along with their relationships.


1. **Log Handler**:
   - The `sqliteLogHandler` class processes log records and delegates them to event handlers.
   - Manages database sessions and ensures transactional consistency.

2. **Event Handlers**:
   - Specialized handlers process specific log events (e.g., workflow start, job info, errors).
   - Handlers parse log records and update the database models accordingly.

3. **Database Models**:
   - SQLAlchemy models represent key entities such as workflows, rules, jobs, files, and errors.
   - Models capture attributes and relationships for comprehensive logging.

4. **Parsers**:
   - Parsers extract structured data from log records for storage in the database.

### Database Schema

The database schema is designed to capture the following entities:

- **Workflow**: Tracks workflow metadata (e.g., `id`, `snakefile`, `status`, `started_at`, `end_time`) and relationships to rules, jobs, and errors.
- **Rule**: Represents Snakemake rules with attributes like `id`, `name`, and relationships to jobs and errors.
- **Job**: Captures job execution details (e.g., `id`, `status`, `started_at`, `end_time`) and relationships to files.
- **File**: Represents input/output files with attributes like `path` and `file_type`.
- **Error**: Logs errors with details such as `exception`, `traceback`, and relationships to workflows and rules.

### Database Versions and Migrations

TODO

## Development

TODO

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository and create a new branch.
2. Make your changes and ensure all tests pass.
3. Submit a pull request with a detailed description of your changes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
